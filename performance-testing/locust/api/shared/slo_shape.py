import os
from collections import Counter

from locust import LoadTestShape
from locust.stats import calculate_response_time_percentile

# Endpoint classes -- must match the *_ENDPOINTS / SLO_P95_*_MS section names
# in env.sh exactly (documentation/staff-api/test-scenarios.md §5).
SLO_CLASSES = [
    "METADATA_READ",
    "REGISTER_READ",
    "CHANGE_REQUEST_READ",
    "INTAKE_SUBMISSION_READ",
    "REGISTER_SEARCH",
    "CHANGE_REQUEST_WRITE",
    "INTAKE_SUBMISSION_WRITE",
    "WORKFLOW_READ",
    "WORKFLOW_WRITE",
    "DOCUMENT_FETCH",
    "DOCUMENT_UPLOAD",
]


def _load_endpoint_slo_ms() -> tuple[dict[str, int], dict[str, int]]:
    """Two endpoint -> SLO-ms maps (p95, p99), built from env.sh's per-class
    sections. A single shared pair of maps works for every scenario: each
    scenario's Locust run only ever produces stats.entries for the endpoints
    it actually fires, so SLOStepRampShape naturally only checks the subset
    relevant to whichever scenario is running -- no per-scenario map needed.
    """
    p95_mapping: dict[str, int] = {}
    p99_mapping: dict[str, int] = {}
    for cls in SLO_CLASSES:
        p95_env = os.environ.get(f"SLO_P95_{cls}_MS")
        p99_env = os.environ.get(f"SLO_P99_{cls}_MS")
        endpoints_env = os.environ.get(f"{cls}_ENDPOINTS", "")
        if not p95_env or not endpoints_env:
            continue
        p95 = int(p95_env)
        p99 = int(p99_env) if p99_env else None
        for name in endpoints_env.split(","):
            name = name.strip()
            if not name:
                continue
            p95_mapping[name] = p95
            if p99 is not None:
                p99_mapping[name] = p99
    return p95_mapping, p99_mapping


ENDPOINT_SLO_P95_MS, ENDPOINT_SLO_P99_MS = _load_endpoint_slo_ms()


class SLOStepRampShape(LoadTestShape):
    """
    Step-1 (isolated) ramp-to-breach-then-soak shape, driven by
    ENDPOINT_SLO_P95_MS / ENDPOINT_SLO_P99_MS (loaded from env.sh, not
    hardcoded -- see documentation/staff-api/test-scenarios.md §4/§5). A
    scenario fires endpoints from several different SLO classes in one run
    (e.g. register_read touches Metadata-Read and Register-Search), so this
    checks each endpoint against its own class's SLOs, not the whole run
    against one number.

    Ramps +step_users every step_seconds. Once any tracked endpoint (with
    enough samples this step) breaches its own p95 OR p99 SLO, the ramp
    freezes at that user count and holds steady there for sustain_seconds
    (a soak at the highest reached load), then stops. If max_users is
    reached with no breach, it stops immediately without a soak.

    503s/other failures are logged but do NOT stop or freeze the ramp, and
    do NOT feed the p95/p99 calculation used to decide a breach either --
    only successful requests' response times count toward SLO checks (a
    failed request's "response time" -- e.g. a near-instant connection
    reset -- isn't a real latency sample, and Locust's own
    get_current_response_time_percentile() would otherwise silently mix
    failed and successful requests together). This shape tracks its own
    per-step, success-only response-time samples via a `request` event
    listener rather than relying on that built-in.

    NOTE: -u/-r/-t are ignored by Locust once a custom shape is active (see
    COMMON_OPTIONS in locust/main.py) -- this class owns its entire stop
    condition, including the max_users safety net.

    NOTE: register_read's get_record_history has a known upstream bug
    (SYS-ERR-001 -- see documentation/seeding-design.md) causing 100%
    failures. It's deliberately excluded from REGISTER_READ_ENDPOINTS in
    env.sh (commented-out toggle to re-add it once fixed) -- since failures
    no longer freeze/stop the ramp on their own, this is now a labeling
    concern rather than a ramp-killer, but it's still excluded to keep
    register_read's failure log free of a known, unrelated noise source.
    """

    # Base class, not meant to be run directly -- must NOT be auto-detected
    # by Locust as a runnable shape (only its per-scenario subclasses, e.g.
    # RegisterReadRampShape, should be). Locust's load_locustfile treats any
    # LoadTestShape subclass as runnable unless abstract=True is set
    # explicitly in that class's own body (see
    # locust/util/load_locustfile.py's is_shape_class) -- without this, a
    # locustfile that merely imports SLOStepRampShape (to subclass it) would
    # have Locust pick up two candidate shapes: this base class AND the
    # subclass, arbitrarily choosing one.
    abstract = True

    endpoint_slo_p95_ms: dict[str, int] = ENDPOINT_SLO_P95_MS
    endpoint_slo_p99_ms: dict[str, int] = ENDPOINT_SLO_P99_MS
    step_seconds = 60
    step_users = 1
    max_users = 30
    min_requests_for_check = 5
    sustain_seconds = 15 * 60

    def __init__(self):
        super().__init__()
        self._step = -1
        self._step_start: dict[tuple[str, str], tuple[int, int]] = {}
        self._step_success_times: dict[tuple[str, str], list[int]] = {}
        self._breach_user_count: int | None = None
        self._breach_run_time: float | None = None
        self._listener_registered = False
        self._tracked_names = set(self.endpoint_slo_p95_ms) | set(self.endpoint_slo_p99_ms)

    def _on_request(self, request_type, name, response_time, response_length, exception=None, **_kwargs):
        # Only successful requests' latencies feed the SLO percentile check
        # -- a failed request's response_time isn't a real latency sample
        # (e.g. a connection reset returns almost instantly), and mixing it
        # in would let failures indirectly trigger/avoid a breach.
        if exception is not None:
            return
        if name not in self._tracked_names:
            return
        self._step_success_times.setdefault((name, request_type), []).append(response_time)

    def _percentile(self, name: str, method: str, percent: float) -> int | None:
        times = self._step_success_times.get((name, method))
        if not times:
            return None
        histogram = Counter(times)
        return calculate_response_time_percentile(histogram, len(times), percent)

    def tick(self):
        if not self._listener_registered:
            # self.runner is only attached after __init__ (see
            # Environment._create_runner), so the listener is registered
            # lazily on first tick instead.
            self.runner.environment.events.request.add_listener(self._on_request)
            self._listener_registered = True

        run_time = self.get_run_time()
        entries = self.runner.stats.entries

        if self._breach_user_count is not None:
            # Already breached -- hold at that user count for the soak
            # window, then stop. No further stepping, no further SLO checks.
            if run_time - self._breach_run_time >= self.sustain_seconds:
                print(
                    f"[shape] stop: {self.sustain_seconds}s soak at "
                    f"{self._breach_user_count} users complete"
                )
                return None
            return (self._breach_user_count, self.step_users)

        step = int(run_time // self.step_seconds)
        user_count = self.step_users * (step + 1)

        if step != self._step:
            # New step: snapshot every endpoint's cumulative failure counter
            # (for logging only) and clear the success-only response-time
            # samples so the SLO check below is scoped to this step's
            # traffic only.
            self._step = step
            self._step_start = {key: (e.num_requests, e.num_failures) for key, e in entries.items()}
            self._step_success_times = {}
        else:
            for (name, method), entry in entries.items():
                if name not in self._tracked_names:
                    continue  # not one of this scenario's tracked endpoints
                start_requests, start_failures = self._step_start.get((name, method), (0, 0))
                requests_this_step = entry.num_requests - start_requests
                failures_this_step = entry.num_failures - start_failures
                success_times = self._step_success_times.get((name, method), [])
                if requests_this_step < self.min_requests_for_check:
                    continue
                if failures_this_step > 0:
                    # Logged, not a stop/freeze condition -- only SLO breaches
                    # (computed from successful requests only) are.
                    print(f"[shape] {name} had {failures_this_step} failure(s) at {user_count} users (logged, not stopping)")
                if not success_times:
                    continue  # nothing successful to check SLOs against this step

                breached = False
                slo95 = self.endpoint_slo_p95_ms.get(name)
                if slo95 is not None:
                    p95 = self._percentile(name, method, 0.95)
                    if p95 is not None and p95 > slo95:
                        print(f"[shape] SLO breach: {name} p95={p95}ms > SLO-95={slo95}ms at {user_count} users")
                        breached = True
                slo99 = self.endpoint_slo_p99_ms.get(name)
                if slo99 is not None:
                    p99 = self._percentile(name, method, 0.99)
                    if p99 is not None and p99 > slo99:
                        print(f"[shape] SLO breach: {name} p99={p99}ms > SLO-99={slo99}ms at {user_count} users")
                        breached = True

                if breached:
                    self._breach_user_count = user_count
                    self._breach_run_time = run_time
                    print(f"[shape] freezing ramp at {user_count} users, soaking for {self.sustain_seconds}s")
                    return (user_count, self.step_users)

        if user_count > self.max_users:
            print(f"[shape] stop: reached max_users={self.max_users} without breaching any SLO")
            return None

        return (user_count, self.step_users)

import os

from locust import LoadTestShape

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
    "WORKFLOW_WRITE",
    "DOCUMENT_FETCH",
    "DOCUMENT_UPLOAD",
]


def _load_endpoint_slo_ms() -> dict[str, int]:
    """One endpoint -> p95-SLO-ms map, built from env.sh's per-class
    sections. A single shared map works for every scenario: each scenario's
    Locust run only ever produces stats.entries for the endpoints it
    actually fires, so SLOStepRampShape naturally only checks the subset
    relevant to whichever scenario is running -- no per-scenario map needed.
    """
    mapping: dict[str, int] = {}
    for cls in SLO_CLASSES:
        p95_env = os.environ.get(f"SLO_P95_{cls}_MS")
        endpoints_env = os.environ.get(f"{cls}_ENDPOINTS", "")
        if not p95_env or not endpoints_env:
            continue
        p95 = int(p95_env)
        for name in endpoints_env.split(","):
            name = name.strip()
            if name:
                mapping[name] = p95
    return mapping


ENDPOINT_SLO_MS = _load_endpoint_slo_ms()


class SLOStepRampShape(LoadTestShape):
    """
    Step-1 (isolated) ramp-to-failure shape, driven by ENDPOINT_SLO_MS
    (loaded from env.sh, not hardcoded -- see documentation/staff-api/
    test-scenarios.md §4/§5). A scenario fires endpoints from several
    different SLO classes in one run (e.g. register_read touches
    Metadata-Read at 200ms and Register-Search at 1000ms), so this checks
    each endpoint against its own SLO, not the whole run against one number.

    Ramps +step_users every step_seconds; stops at the first step where any
    tracked endpoint (with enough samples this step) breaches its own p95
    SLO or has any failure, or when max_users is reached.

    NOTE: -u/-r/-t are ignored by Locust once a custom shape is active (see
    COMMON_OPTIONS in locust/main.py) -- this class owns its entire stop
    condition, including the max_users safety net.

    NOTE: register_read's get_record_history has a known upstream bug
    (SYS-ERR-001 -- see documentation/seeding-design.md) causing 100%
    failures. It's deliberately excluded from REGISTER_READ_ENDPOINTS in
    env.sh (commented-out toggle to re-add it once fixed) -- if it were
    included, this shape would stop register_read's ramp on the very first
    checked step.
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

    endpoint_slo_ms: dict[str, int] = ENDPOINT_SLO_MS
    step_seconds = 90
    step_users = 1
    max_users = 30
    min_requests_for_check = 5

    def __init__(self):
        super().__init__()
        self._step = -1
        self._step_start: dict[tuple[str, str], tuple[int, int]] = {}

    def tick(self):
        run_time = self.get_run_time()
        step = int(run_time // self.step_seconds)
        user_count = self.step_users * (step + 1)

        entries = self.runner.stats.entries

        if step != self._step:
            # New step: snapshot every endpoint's cumulative counters so the
            # check below is scoped to this step's traffic only.
            self._step = step
            self._step_start = {key: (e.num_requests, e.num_failures) for key, e in entries.items()}
        else:
            for (name, method), entry in entries.items():
                if name not in self.endpoint_slo_ms:
                    continue  # not one of this scenario's tracked endpoints
                start_requests, start_failures = self._step_start.get((name, method), (0, 0))
                requests_this_step = entry.num_requests - start_requests
                failures_this_step = entry.num_failures - start_failures
                if requests_this_step < self.min_requests_for_check:
                    continue
                if failures_this_step > 0:
                    print(f"[shape] stop: {name} had {failures_this_step} failure(s) at {user_count} users")
                    return None
                p95 = entry.get_current_response_time_percentile(0.95)
                slo = self.endpoint_slo_ms[name]
                if p95 is not None and p95 > slo:
                    print(f"[shape] stop: {name} p95={p95}ms > SLO={slo}ms at {user_count} users")
                    return None

        if user_count > self.max_users:
            print(f"[shape] stop: reached max_users={self.max_users} without breaching any SLO")
            return None

        return (user_count, self.step_users)

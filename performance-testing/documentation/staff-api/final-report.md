# Final Report

This is the **interpretation** layer: SLO verdicts, the capacity/sizing
model, bottleneck analysis, recommendations — everything that requires a
human reading the numbers and drawing a conclusion. It is built by reading
[`raw-report.md`](raw-report.md) (every measurement, verbatim, no
interpretation) and, for the curated headline endpoints, the
`synthesize_templates/` CSVs under
[`../locust/api/templates/staff-api/`](../locust/api/templates/staff-api/)
once `scripts/synthesize_report.py` has filled them in. See
[`test-scenarios.md`](test-scenarios.md) §3 for the Volume-Tier × Pod-Scale
matrix and the 3-Step + `db-sweep` model these map to.

**Pipeline:** raw Locust `--csv` output → `scripts/create_raw_report.py` →
[`raw-report.md`](raw-report.md) (first output, all endpoints, no judgement)
→ `scripts/synthesize_report.py` → curated `synthesize_templates/*.csv`
(headline endpoints + SLO + PASS/FAIL, second output) → this document
(hand-written interpretation, cites both).

## The deliverables

| # | Output | Form | Source |
|---|--------|------|---|
| 1 | **Per-scenario capacity table** — endpoint, method, max sustainable RPS @ SLO, p50/p90/p95/p99/max, error %, saturating resource, per Volume-Tier/Pod-Scale cell | table | Step 1 (raw: [`raw-report.md`](raw-report.md); curated: `isolated-capacity.csv`) |
| 2 | **Per-pod resource profile** at max RPS (pod CPU, mem, DB conns) | table + graphs | Step 1 |
| 3 | **Latency-vs-RPS ("knee") and RPS-vs-users curves** | charts | Step 1 |
| 4 | **Blended capacity table**, per cell | table | Step 2 (raw: [`raw-report.md`](raw-report.md); curated: `blended-capacity.csv`) |
| 5 | **Horizontal scaling table + curve** — blended max RPS at Pod-Scale 1/2/3, same tier; efficiency; limiting factor | table + chart | *derived* — compare Step 2 across Pod-Scale |
| 6 | **Data-volume sensitivity** — capacity/latency vs Volume-Tier, same pod-scale | chart | *derived* — compare Step 1/2 across Volume-Tier |
| 7 | **Soak/endurance report** — RPS, p95, error rate, pod memory, DB conns over 8h; memory-trend verdict | time-series graphs | Step 3 (raw: [`raw-report.md`](raw-report.md); curated: `soak.csv`) |
| 8 | **DB capacity table** — threshold RPS + first bottleneck per tuning/volume/VM scenario; top slow queries | table | `db-sweep` (raw: [`raw-report.md`](raw-report.md); curated: `db-sweep.csv`) |
| 9 | **Bottleneck & tuning findings** — what saturated first; config changes that moved it (worker count, pool size, indexes, PgBouncer, max_connections, gp3 IOPS) | narrative | all |
| 10 | **Capacity / sizing model** — the headline business output (below) | formula/table | Synthesis |
| 11 | **Pass/fail vs SLO/NFR** | table | Synthesis |
| 12 | **Methodology + reproducible assets** — Locust scripts, env spec, versions, seed manifest | doc + repo | all |

Items **5, 7, 8, and 10** are what reviewers/funders care about most: the
scaling factor, proof of no time-decay, the DB ceiling, and the sizing
formula.

Async pipeline throughput (Celery) is **not** a current deliverable — see
[`test-scenarios.md`](test-scenarios.md) §1/§2.

## The capacity / sizing model (headline output)

The synthesis must yield a statement operators can plan against, e.g.:

> *On the 3-node production profile (compute `m5a.4xlarge`, host-PG
> `t3a.2xlarge`), one `1 vCPU / 4 GB` staff-portal-api pod sustains **R** RPS of
> the blended workload (Step 2) at p95 ≤ SLO over the `primary` (10M farmer)
> Volume-Tier. At Pod-Scale 3 that becomes **R₃** RPS (efficiency **e**). The
> host PostgreSQL becomes the bottleneck at **D** RPS (`db-sweep`, tuned +
> PgBouncer), driven by `<bottleneck>`. Therefore, to serve a target of **T**
> RPS over **V** million records at the SLOs, provision **⌈T/R⌉** app pods
> (bounded by the DB ceiling D) and a DB of **`<size>`** with
> **`<max_connections>`** via PgBouncer.*

with the variables filled from the measured results.

## Report structure

Use the skeleton below as the final written report. Right now only a
`smoke`-tier pipeline dry run exists (see the methodology note in §2 and the
`End-to-End › smoke › pod-1 › 1-isolated` section of
[`raw-report.md`](raw-report.md)) — it proved the raw-report/synthesize
pipeline works and caught one real methodology bug (below), but it is **not**
a capacity figure. Fill in the rest of this skeleton once real `primary`-tier
ramp-to-failure data exists.

### 1. Executive summary
- **Headline:** Pod-Scale 1 (1 vCPU/4 GB) sustains **___ RPS** blended (Step 2) @ p95 ≤ SLO over Volume-Tier **`primary`**. _Not yet measured._
- **Scaling:** Pod-Scale 3 → **___ RPS** (efficiency **___**).
- **DB ceiling:** **___ RPS** (`db-sweep`, tuned + PgBouncer), limited by **______**.
- **Sizing model:** to serve **T RPS** over **V M** records → **___ app pods + DB `___`**.
- **Verdict vs SLO/NFR:** PASS / FAIL — _____.

### 2. Environment & methodology
- Chart version / image tags / git SHA: ______ (Prep step 1, not yet done).
- Nodes: compute `m5a.4xlarge` (16/64), storage host-PG `t3a.2xlarge` (8/32, T3-unlimited: __), RP `t3a.medium` — see [`environment-topology.md`](../environment-topology.md).
- Pod under test: 1 vCPU / 4 GB, `requests==limits`, HPA off, workers = __ (Prep step 6, not yet done — worker-count sweep pending).
- PostgreSQL 16: tuning = ______; PgBouncer = ______; max_connections = __.
- Volume-Tier(s) / Pod-Scale(s) tested: `smoke`/Pod-Scale 1 only so far (pipeline dry run). `primary` pending Prep completion.
- Load tool: Locust 2.46.3; run location: external host against the public perftest hostname (`STAFF_API_BASE`), i.e. **end-to-end** ingress, not in-cluster — Prep step 7 calls for an in-cluster Locust deployment for per-pod/scaling figures, still pending.
- **Methodology finding from the dry run:** the results-folder/template ingress label was initially wrong (`in-cluster` when the run actually went `end-to-end` through the public perftest hostname) — corrected; results are now segmented by ingress at the top level (`results/staff-api/<ingress>/...`) specifically so in-cluster and end-to-end runs of the same cell can never silently overwrite each other.
- **Known upstream bug, not a capacity finding:** in the `smoke` dry run, `register_read`'s `get_record_history` call failed 33/33 (`SYS-ERR-001`) — see [`seeding-design.md`](../seeding-design.md) (`change_request_source.value` on a plain `String` column). Needs a decision before real `primary`-tier Step 1 runs: exclude `get_record_history` from `register_read`'s pass/fail, or block on the upstream fix.

### 3. Per-scenario capacity (Step 1)
_Cite the relevant `Step: 1-isolated` sections of [`raw-report.md`](raw-report.md)
for the full per-endpoint numbers, and `synthesize_templates/isolated-capacity.csv`
(after running `scripts/synthesize_report.py --step isolated ...`) for the
curated headline-endpoint SLO/PASS-FAIL table. Add the latency-vs-RPS "knee"
charts (one per endpoint, across ramp steps) once a real ramp exists — a
single-user dry run can't produce those._

### 4. Blended capacity, scaling, and data-volume sensitivity (Step 2)
_Cite [`raw-report.md`](raw-report.md)'s `Step: 2-blended` sections and
`synthesize_templates/blended-capacity.csv`. Derive the scaling curve
(Pod-Scale 1→2→3, fixed tier) and the volume-sensitivity chart (Volume-Tier
swept, fixed pod-scale) from the same data — see
[`test-scenarios.md`](test-scenarios.md) §3. Limiting factor at Pod-Scale 3: ______._

### 5. Endurance / soak (Step 3)
- Load: 80% of this cell's Step 2 max = ___ RPS, 8h.
- Memory trend: ______ (leak? Y/N). Error rate over time: ______. p95 drift: ______.
_Cite [`raw-report.md`](raw-report.md)'s `Step: 3-soak` sections (time series
from Locust's `_stats_history.csv`) as time-series graphs._

### 6. Database ceiling (`db-sweep`)
_Cite [`raw-report.md`](raw-report.md)'s `Step: 4-db-sweep` sections (hand-recorded
readings) + latency-vs-volume chart + top `pg_stat_statements`._

### 7. Bottlenecks & tuning
- First bottleneck per Step: ______
- Changes that moved it (worker count / pool size / indexes / PgBouncer / max_connections / gp3 IOPS): ______

### 8. Pass / fail vs SLO/NFR
_Per endpoint class (see [`test-scenarios.md`](test-scenarios.md) §6): target p95/p99 vs achieved; PASS/FAIL._

### 9. Recommendations & sizing guide
- Production sizing for target load: ______
- Config recommendations (defaults to change in the chart): ______
- Follow-ups / known limits (incl. async-pipeline throughput, not covered this round): ______

### 10. Appendix
- Raw Locust CSVs, Grafana dashboard exports, `pg_stat_statements` dumps.
- Locust config + seed manifest + exact postgresql.conf diffs.

## Conventions

- Always report **p95 and p99** (not p95 alone) and **error rate by type**.
- Every number carries its **pinned config** (Pod-Scale, worker count,
  Volume-Tier, DB tuning) — a bare "RPS" is meaningless without it.
- Report **median of ≥2 runs** plus spread; flag any run-to-run variance
  > ~10%.
- State the **ingress point** (in-cluster vs end-to-end) for every figure.

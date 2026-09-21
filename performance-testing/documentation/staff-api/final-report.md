# Final Report

Interpretation layer over [`raw-report.md`](raw-report.md) (every
measurement, verbatim, no interpretation) and, for the curated headline
endpoints, the `synthesize_templates/` CSVs under
[`../locust/api/templates/staff-api/`](../locust/api/templates/staff-api/)
once `scripts/synthesize_report.py` has run. See
[`test-scenarios.md`](test-scenarios.md) §3 for the Volume-Tier × Pod-Scale
matrix and the 3-Step + `db-sweep` model these map to.

**Pipeline:** raw Locust `--csv` output → `scripts/create_raw_report.py` →
[`raw-report.md`](raw-report.md) (all endpoints, no judgement) →
`scripts/synthesize_report.py` → curated `synthesize_templates/*.csv`
(headline endpoints + SLO + PASS/FAIL) → this document (interpretation,
cites both).

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

Once primary-tier data exists, the sizing statement takes this form:

> *On the 3-node production profile (compute `m5a.4xlarge`, host-PG
> `t3a.2xlarge`), one `staff-portal-api` pod (spec:
> [`environment-topology.md`](../environment-topology.md)) sustains **R** RPS of
> the blended workload (Step 2) at p95 ≤ SLO over the `primary` (10M farmer)
> Volume-Tier. At Pod-Scale 3 that becomes **R₃** RPS (efficiency **e**). The
> host PostgreSQL becomes the bottleneck at **D** RPS (`db-sweep`, tuned +
> PgBouncer), driven by `<bottleneck>`. Therefore, to serve a target of **T**
> RPS over **V** million records at the SLOs, provision **⌈T/R⌉** app pods
> (bounded by the DB ceiling D) and a DB of **`<size>`** with
> **`<max_connections>`** via PgBouncer.*

Not yet computable — requires primary-tier ramp-to-failure data (§4-§7
below).

## Report structure

Sections are organized **Ingress › Volume-Tier › Capacity Calculations**,
mirroring [`raw-report.md`](raw-report.md)'s own hierarchy (see the
methodology note in §2) — a tier's Capacity Calculations subsection fills
in once that tier's run exists, with no separate status prose needed per
tier. Both End-to-End and In-Cluster now have Primary-tier Step 1
(isolated, §4) and Step 2 (blended, fixed-concurrency, §5) data; End-to-End
also has Smoke (harness validation only). Step 3 (soak) has one cell —
In-Cluster/Primary/Pod-3, a full 8h run (§6), though at a load level that
doesn't match the "80% of Step 2" methodology as documented (see §6's
note). `stretch`/`stress` and `db-sweep` (§7) remain untested. Findings
that stand independent of any single cell's numbers: the AWE-hop
bottleneck (§4, §6, §8, confirmed twice — isolated-tier latency and
soak-run connection resets) and the iam-core JWKS/OIDC-metadata cache fix,
now confirmed active (§8, item 3). Sections 9-11 (pass/fail, sizing) are
still pending `stretch`/`stress`/`db-sweep`.

### 1. Executive summary
- **Reported improvement, code confirmed applied:** the iam-core
  JWKS/OIDC-metadata cache fix was reported to raise Pod-1 (2 vCPU / 2 GB)
  capacity from ~10 to 30+ concurrent Locust users. The fix (`iam` commit
  `4c1888b`, G2P-5647) is in this checkout — `iam` is now on its
  `performance-test` branch — see §8, item 3.
- **Headline:** Pod-Scale 1 (spec: [`environment-topology.md`](../environment-topology.md)) sustains **≥71.0 RPS** in-cluster / **≥66.3 RPS** end-to-end blended (Step 2) over Volume-Tier `primary`, near-zero to zero failures — both measured at a **fixed concurrency** (12 / 20 users respectively), not a ramp-to-failure, so these are floors, not the SLO-confirmed ceiling (§5).
- **Scaling:** Pod-Scale 3 → **123.7 RPS** in-cluster / **122.3 RPS** end-to-end (efficiency **≈58%** / **≈61%** of linear) — both from the same fixed-concurrency data (§5); the two ingresses reach almost the same RPS ceiling, so the RP isn't yet the limiting factor at this load.
- **DB ceiling:** **___ RPS** (`db-sweep`, tuned + PgBouncer), limited by **______**.
- **Sizing model:** to serve **T RPS** over **V M** records → **___ app pods + DB `___`**.
- **Verdict vs SLO/NFR:** PASS / FAIL — _____.

### 2. Environment & methodology
- Chart version / image tags / git SHA: ______ (Prep step 1, not yet done).
- Nodes: compute `m5a.4xlarge` (16/64), storage host-PG `t3a.2xlarge` (8/32, T3-unlimited: __), RP `t3a.medium` — see [`environment-topology.md`](../environment-topology.md).
- Pod under test: spec + `requests==limits`/HPA-off posture in [`environment-topology.md`](../environment-topology.md) ("Pod configuration"); workers = __ (Prep step 6, not yet done — worker-count sweep pending).
- PostgreSQL 16: tuning + PgBouncer config — see §3 (PostgreSQL & PgBouncer configuration); `max_connections` isn't set in either checked-in config file and still needs recording per run.
- Volume-Tier(s) / Pod-Scale(s) tested: `smoke` (end-to-end only) and
  `primary` (both end-to-end and in-cluster), Pod-Scale 1-3, Step 1
  (isolated) and Step 2 (blended, fixed-concurrency — §5). Step 3 (soak):
  one cell, in-cluster/primary/Pod-3, full 8h (§6). `stretch`/`stress` and
  `db-sweep` pending.
- Load tool: Locust 2.46.3; run location: external host against the public perftest hostname (`STAFF_API_BASE`), i.e. **end-to-end** ingress, not in-cluster — Prep step 7 calls for an in-cluster Locust deployment for per-pod/scaling figures, still pending.
- **Methodology finding from the dry run:** the results-folder/template ingress label was initially wrong (`in-cluster` when the run actually went `end-to-end` through the public perftest hostname) — corrected; results are now segmented by ingress at the top level (`results/staff-api/<ingress>/...`) specifically so in-cluster and end-to-end runs of the same cell can never silently overwrite each other.
- **Known upstream bug, resolved by exclusion:** in the `smoke` dry run, `register_read`'s `get_record_history` call failed 33/33 (`SYS-ERR-001`) — see [`seeding-design.md`](../seeding-design.md) (`change_request_source.value` on a plain `String` column). Decision made: the call was dropped from `register_read`'s task code rather than blocking on the upstream fix (`locust/api/env.sh`, `locust/api/shared/slo_shape.py`) — it doesn't appear in the Smoke or Primary runs and needs no further tracking.

### 3. Pod & database configuration

Pod specs (`staff-portal-api` 2 vCPU / 2 GB, AWE 2 vCPU / 2 GB, Keycloak
1 vCPU / 1 GB) and the PostgreSQL/PgBouncer tuning are now maintained in one
place — see [`environment-topology.md`](../environment-topology.md)'s "Pod
configuration" and "PostgreSQL & PgBouncer configuration" sections — rather
than duplicated here. This is the spec the End-to-End Smoke and Primary
Pod-Scale 1/2/3 runs (§4) actually ran against, and matches §2's pod-under-test
spec.

### 4. Per-scenario capacity (Step 1: isolated)

Organized **Ingress › Volume-Tier › Capacity Calculations**, mirroring
[`raw-report.md`](raw-report.md)'s own hierarchy — a tier's Capacity
Calculations subsection is filled in once that tier's isolated run exists;
an untested tier is a placeholder, not a paragraph explaining its absence.
Full per-endpoint numbers for every populated cell: the `Step: 1-isolated`
sections of [`raw-report.md`](raw-report.md); curated headline-endpoint
SLO/PASS-FAIL: `synthesize_templates/isolated-capacity.csv` (after running
`scripts/synthesize_report.py --step isolated ...`). Latency-vs-RPS "knee"
charts (one per endpoint, across ramp steps) are pending — a single-step
run doesn't produce a ramp.

#### Real-life concurrent-user estimates: methodology

Locust's `wait_time` only paces between `@task` picks, not between the
individual API calls inside one task — a Locust "user" fires a whole
scenario's calls back-to-back, unlike a real case worker. Converting
Locust throughput into a real-user-equivalent figure uses Little's Law:

```
Real concurrent users = (unit completions/sec) × (real completion time, seconds)
```

**The unit is one fully-handled record, not one `@task` iteration** — the
realistic single-record journey a case worker actually performs: search,
land on one record, fire every API that record's detail view needs, then
(where applicable) act on it:

| Scenario | One unit of work |
|---|---|
| register_read | search → zoom into 1 record → every tab, every pending CR on that tab, every version date on that tab |
| cr_create | search → pick 1 record → its tabs/sections → edit 1 section → create the CR |
| cr_read_and_approve | search → pick 1 CR → its documents/schema/dedup/tasks → approve |
| intake_create | render the form → save every section → fetch → finalize |
| intake_read_and_approve | search → pick 1 submission → its documents/dedup/tasks → approve |

For each API in a unit's chain, its contribution to "total time for 1
unit" is **its own average response time × how many times it actually
fires per unit** (`endpoint's Request Count ÷ anchor's Request Count`,
both from the same pod's CSV) — not counted once each, since several of
these calls are structurally repeated per record (a record has several
tabs; a tab has however many pending items it has) or repeated by the
test's own search/candidate-discovery process.

**RPS is `Locust users (peak) ÷ Total time for 1 unit`, not the anchor
endpoint's own directly-measured Requests/s.** Locust's `wait_time`
(`shared/base_user.py`, `between(0.5, 2.0)`) pauses every simulated user
between `@task` iterations — a real pause with no relationship to
`T_real`, still present in every run this report covers. An endpoint's own
measured Requests/s is throttled by that pause (it's a raw count of
observed calls over wall-clock time), so it understates what the same
`N` users would sustain firing back-to-back. Summing each API's own
average response time already excludes `wait_time` by construction (the
pause happens *between* tasks, never inside a request's own response
time), so `Locust users ÷ Total time for 1 unit` gives that
zero-wait rate directly — this is what feeds `T_real` below, for every
scenario, including the two-endpoint case (`cr_create`, next paragraph).

`cr_create` is the one scenario whose anchor is two mutually exclusive
endpoints — every CR creation calls exactly one of `create_change_request`
or `create_change_request_for_core_data`, never both. Each variant's
average response time is folded into "total time for 1 unit" as a
share-weighted average (it's a single chain step whose cost depends on
which variant fires) — no separate handling is needed for RPS itself,
since `Locust users ÷ Total time for 1 unit` already accounts for both
variants through that weighted `Total time`.

#### End-to-End

##### Volume-Tier: Smoke

###### Capacity Calculations

Two effects are visible in this tier's data.

Endpoints that stay inside registry-platform improve as pods scale, as
expected — less contention per pod:

| Endpoint | Pod-1 p95 | Pod-2 p95 | Pod-3 p95 |
|---|---|---|---|
| `get_change_request` | 860ms | 790ms | 620ms |
| `get_deduplication_register_results` | 780ms | 760ms | 600ms |

Endpoints that call out to AWE get worse as pods scale — the bottleneck is
the AWE hop, not registry-platform's own DB/CPU (root cause in §8):

| Endpoint | Pod-1 p95 | Pod-2 p95 | Pod-3 p95 |
|---|---|---|---|
| `list_tasks_for_request` | 920ms | 1100ms | 1100ms |
| `submit_task_decision` | 910ms | 980ms | 1000ms |

**register_read** — 1 register record fully read:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_a_register` | 370ms (×1.00) | 374ms (×1.00) | 339ms (×1.00) |
| `get_subject_record` | 244ms (×1.00) | 241ms (×1.00) | 208ms (×1.00) |
| `get_all_tabs` | 263ms (×1.00) | 256ms (×1.00) | 214ms (×1.00) |
| `get_tab_sections` | 270ms (×6.73) | 266ms (×6.81) | 224ms (×6.84) |
| `get_tab_records` | 320ms (×6.72) | 312ms (×6.80) | 262ms (×6.83) |
| `get_number_of_pending_change_requests` | 244ms (×6.70) | 240ms (×6.80) | 201ms (×6.82) |
| `get_change_requests` | 268ms (×6.69) | 266ms (×6.79) | 222ms (×6.82) |
| `get_change_request_documents` | 220ms (×1.87) | 237ms (×2.49) | 201ms (×1.96) |
| `get_section_ui_schema` | 223ms (×1.86) | 235ms (×2.49) | 201ms (×1.96) |
| `get_change_request` | 266ms (×1.86) | 288ms (×2.48) | 250ms (×1.95) |
| `list_tasks_for_request` | 268ms (×1.86) | 307ms (×2.48) | 291ms (×1.95) |
| `get_deduplication_change_request_results` | 224ms (×1.86) | 241ms (×2.48) | 207ms (×1.95) |
| `get_deduplication_register_results` | 234ms (×1.86) | 234ms (×2.48) | 205ms (×1.95) |
| `get_number_of_versions` | 262ms (×6.68) | 259ms (×6.77) | 214ms (×6.80) |
| `get_version_dates` | 258ms (×6.68) | 250ms (×6.77) | 209ms (×6.80) |
| `get_versions_for_a_date` | 263ms (×3.99) | 270ms (×4.22) | 220ms (×4.36) |
| **Total time for 1 register record** | **15.45s** | **16.66s** | **13.45s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 28 | 48 | 56 |
| RPS to serve 1 register record (Locust users ÷ Total time) | 1.812 | 2.880 | 4.164 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 54 | 86 | 125 |

**cr_create** — 1 change request effected:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_a_register` | 382ms (×0.36) | 336ms (×0.35) | 296ms (×0.36) |
| `get_subject_record` | 291ms (×0.18) | 226ms (×0.18) | 178ms (×0.18) |
| `get_all_sections` | 602ms (×0.18) | 516ms (×0.18) | 422ms (×0.18) |
| `get_all_tabs` | 285ms (×0.18) | 246ms (×0.18) | 185ms (×0.18) |
| `get_tab_sections` | 298ms (×1.25) | 248ms (×1.26) | 196ms (×1.28) |
| `get_tab_records` | 354ms (×1.25) | 294ms (×1.25) | 232ms (×1.27) |
| `get_attribute_values` | 273ms (×0.05) | 245ms (×0.05) | 195ms (×0.04) |
| `create_change_request` | 564ms (93% of CRs) | 509ms (94% of CRs) | 518ms (94% of CRs) |
| `create_change_request_for_core_data` | 584ms (7% of CRs) | 566ms (6% of CRs) | 543ms (6% of CRs) |
| **Total time for 1 change request effected** | **1.75s** | **1.50s** | **1.32s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 24 | 36 | 36 |
| RPS to serve 1 change request created (Locust users ÷ Total time) | 13.741 | 23.948 | 27.171 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 412 | 718 | 815 |

**cr_read_and_approve** — 1 change request approved:

_Captured before the change that limits `cr_read_and_approve` to pending
tasks only — expect the ×/unit ratios below (and the derived RPS/real-user
figures) to shift once this scenario is re-run._

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_change_request` | 374ms (×2.17) | 415ms (×1.01) | 314ms (×1.17) |
| `get_change_request_documents` | 306ms (×5.09) | 295ms (×3.07) | 166ms (×3.03) |
| `get_section_ui_schema` | 306ms (×5.09) | 296ms (×3.07) | 164ms (×3.03) |
| `get_change_request` | 374ms (×5.07) | 360ms (×3.06) | 205ms (×3.03) |
| `get_deduplication_change_request_results` | 312ms (×5.06) | 302ms (×3.06) | 168ms (×3.03) |
| `get_deduplication_register_results` | 312ms (×5.06) | 299ms (×3.06) | 167ms (×3.02) |
| `list_tasks_for_request` | 364ms (×5.05) | 370ms (×3.05) | 294ms (×3.02) |
| `submit_task_decision` | 480ms (×1.00) | 453ms (×1.00) | 377ms (×1.00) |
| **Total time for 1 change request approved** | **11.30s** | **6.76s** | **4.27s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 28 | 48 | 32 |
| RPS to serve 1 change request approved (Locust users ÷ Total time) | 2.478 | 7.104 | 7.495 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 74 | 213 | 225 |

**intake_create** — 1 intake submission created:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `render_intake_form` | 257ms (×1.03) | 205ms (×1.02) | 162ms (×1.02) |
| `save_intake_form_submission` | 530ms (×9.17) | 407ms (×9.12) | 304ms (×9.13) |
| `get_intake_form_submission` | 383ms (×1.01) | 298ms (×1.00) | 225ms (×1.00) |
| `finalize_intake_form_submission` | 734ms (×1.00) | 613ms (×1.00) | 510ms (×1.00) |
| **Total time for 1 intake submission created** | **6.24s** | **4.84s** | **3.67s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 20 | 28 | 28 |
| RPS to serve 1 intake submission created (Locust users ÷ Total time) | 3.204 | 5.790 | 7.623 |
| T_real | 60s | 60s | 60s |
| Real concurrent users | 192 | 347 | 457 |

**intake_read_and_approve** — 1 intake submission approved:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_intake_form_submissions` | 547ms (×16.71) | 556ms (×8.84) | 332ms (×1.61) |
| `get_intake_form_submission` | 160ms (×1.05) | 213ms (×1.08) | 233ms (×1.22) |
| `get_intake_form_documents` | 107ms (×1.05) | 145ms (×1.08) | 161ms (×1.22) |
| `get_deduplication_intake_form_register_results` | 114ms (×1.05) | 151ms (×1.08) | 162ms (×1.22) |
| `get_deduplication_intake_form_intake_form_results` | 114ms (×1.05) | 147ms (×1.08) | 161ms (×1.22) |
| `list_tasks_for_request` | 175ms (×1.05) | 226ms (×1.08) | 294ms (×1.22) |
| `submit_task_decision` | 217ms (×1.00) | 280ms (×1.00) | 342ms (×1.00) |
| **Total time for 1 intake submission approved** | **10.07s** | **6.14s** | **2.11s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 24 | 40 | 32 |
| RPS to serve 1 intake submission approved (Locust users ÷ Total time) | 2.384 | 6.509 | 15.187 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 72 | 195 | 456 |

**All five scenarios now scale up with Pod-Scale** under this corrected,
per-record unit — including `cr_read_and_approve` and
`intake_read_and_approve`, which the session/summary-anchored version of
this table had shown shrinking at Pod-Scale 3. That earlier drop was an
artifact of the old anchor choice, not a real capacity regression: once
throughput is measured as "records/CRs/submissions actually completed per
second" instead of "outer search-and-drain sessions completed per
second," both scenarios scale cleanly.

This does **not** contradict the separate peak-concurrency-ceiling finding
from this conversation's cr_read_and_approve re-analysis (the ramp shape
still freezes at a lower user count at Pod-Scale 3 than Pod-Scale 2, and
AWE still logs connection-reset errors under load) — that is a tail/ceiling
effect visible in the ramp shape's own ramp-to-breach behavior, not in
this typical-case, whole-run throughput number. The two findings answer
different questions: this table says "the typical CR/submission is handled
faster and more of them get done per second as pods scale"; the
peak-concurrency finding says "the *ceiling* before things start failing
is still capped by AWE's fixed capacity." Both are true at once.

`N` (each scenario's peak `User Count` from its own `_stats_history.csv`)
is the `Locust users (peak, this run)` row already published in every
table above — it's also what `RPS to serve 1 X` is now computed from
(`Locust users ÷ Total time for 1 unit`, per this section's methodology
note above), so there is no separate cross-check table here anymore: the
"server-time-only" derivation that used to be a second, independent check
against a measured-RPS table **is** the method the tables above use.

##### Volume-Tier: Primary

###### Capacity Calculations

**register_read** — 1 register record fully read:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_a_register` | 171ms (×1.00) | 159ms (×1.00) | 174ms (×1.00) |
| `get_subject_record` | 155ms (×1.00) | 138ms (×1.00) | 140ms (×1.00) |
| `get_all_tabs` | 126ms (×1.00) | 107ms (×1.00) | 114ms (×1.00) |
| `get_tab_sections` | 172ms (×6.94) | 149ms (×6.94) | 155ms (×6.95) |
| `get_tab_records` | 206ms (×6.94) | 175ms (×6.94) | 182ms (×6.95) |
| `get_number_of_pending_change_requests` | 157ms (×6.94) | 134ms (×6.94) | 139ms (×6.94) |
| `get_change_requests` | 175ms (×6.93) | 149ms (×6.93) | 155ms (×6.94) |
| `get_change_request_documents` | 135ms (×0.08) | 139ms (×0.03) | 134ms (×0.04) |
| `get_section_ui_schema` | 121ms (×0.08) | 161ms (×0.03) | 132ms (×0.04) |
| `get_change_request` | 168ms (×0.08) | 204ms (×0.03) | 179ms (×0.04) |
| `list_tasks_for_request` | 149ms (×0.08) | 175ms (×0.03) | 164ms (×0.04) |
| `get_deduplication_change_request_results` | 137ms (×0.08) | 154ms (×0.03) | 130ms (×0.04) |
| `get_deduplication_register_results` | 135ms (×0.08) | 156ms (×0.03) | 144ms (×0.04) |
| `get_number_of_versions` | 168ms (×6.93) | 144ms (×6.93) | 149ms (×6.94) |
| `get_version_dates` | 164ms (×6.93) | 139ms (×6.93) | 144ms (×6.94) |
| `get_versions_for_a_date` | 172ms (×5.83) | 148ms (×5.91) | 152ms (×5.92) |
| **Total time for 1 register record** | **8.75s** | **7.48s** | **7.78s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 20 | 32 | 44 |
| RPS to serve 1 register record (Locust users ÷ Total time) | 2.286 | 4.278 | 5.655 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 69 | 128 | 170 |

**cr_create** — 1 change request effected:

`get_attribute_values` recorded 0 requests in this run (unlike Smoke) and
is excluded from the chain below rather than assumed absent going forward.

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_a_register` | 210ms (×0.39) | 191ms (×0.39) | 222ms (×0.39) |
| `get_subject_record` | 177ms (×0.20) | 162ms (×0.20) | 179ms (×0.20) |
| `get_all_sections` | 191ms (×0.20) | 186ms (×0.20) | 201ms (×0.20) |
| `get_all_tabs` | 136ms (×0.20) | 125ms (×0.20) | 138ms (×0.20) |
| `get_tab_sections` | 190ms (×1.40) | 173ms (×1.40) | 193ms (×1.40) |
| `get_tab_records` | 225ms (×1.40) | 208ms (×1.40) | 228ms (×1.40) |
| `create_change_request` | 341ms (93% of CRs) | 320ms (93% of CRs) | 361ms (93% of CRs) |
| `create_change_request_for_core_data` | 359ms (7% of CRs) | 353ms (7% of CRs) | 395ms (7% of CRs) |
| **Total time for 1 change request effected** | **1.11s** | **1.02s** | **1.14s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 20 | 32 | 48 |
| RPS to serve 1 change request created (Locust users ÷ Total time) | 18.083 | 31.249 | 42.007 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 542 | 937 | 1260 |

**cr_read_and_approve** — 1 change request approved:

_Captured before the change that limits `cr_read_and_approve` to pending
tasks only — expect the ×/unit ratios below (and the derived RPS/real-user
figures) to shift once this scenario is re-run._

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_change_request` | 260ms (×0.32) | 287ms (×0.32) | 380ms (×0.28) |
| `get_change_request_documents` | 158ms (×2.41) | 152ms (×2.20) | 186ms (×1.95) |
| `get_section_ui_schema` | 158ms (×2.41) | 151ms (×2.20) | 186ms (×1.94) |
| `get_change_request` | 196ms (×2.41) | 188ms (×2.20) | 229ms (×1.94) |
| `get_deduplication_change_request_results` | 160ms (×2.41) | 155ms (×2.20) | 189ms (×1.94) |
| `get_deduplication_register_results` | 165ms (×2.41) | 154ms (×2.20) | 189ms (×1.94) |
| `list_tasks_for_request` | 165ms (×2.40) | 159ms (×2.19) | 192ms (×1.94) |
| `submit_task_decision` | 201ms (×1.00) | 198ms (×1.00) | 236ms (×1.00) |
| **Total time for 1 change request approved** | **2.70s** | **2.40s** | **2.62s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 16 | 28 | 48 |
| RPS to serve 1 change request approved (Locust users ÷ Total time) | 5.927 | 11.688 | 18.327 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 178 | 351 | 550 |

**intake_create** — 1 intake submission created:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `render_intake_form` | 192ms (×1.06) | 160ms (×1.01) | 175ms (×1.01) |
| `save_intake_form_submission` | 364ms (×9.06) | 280ms (×9.05) | 319ms (×9.04) |
| `get_intake_form_submission` | 271ms (×1.00) | 214ms (×1.00) | 240ms (×1.00) |
| `finalize_intake_form_submission` | 350ms (×1.00) | 289ms (×1.00) | 326ms (×1.00) |
| **Total time for 1 intake submission created** | **4.12s** | **3.20s** | **3.63s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 20 | 28 | 44 |
| RPS to serve 1 intake submission created (Locust users ÷ Total time) | 4.854 | 8.759 | 12.138 |
| T_real | 60s | 60s | 60s |
| Real concurrent users | 291 | 526 | 728 |

**intake_read_and_approve** — 1 intake submission approved:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_intake_form_submissions` | 190ms (×1.85) | 222ms (×1.54) | 198ms (×14.37) |
| `get_intake_form_submission` | 227ms (×2.37) | 237ms (×2.45) | 205ms (×1.90) |
| `get_intake_form_documents` | 159ms (×2.37) | 166ms (×2.45) | 139ms (×1.90) |
| `get_deduplication_intake_form_register_results` | 161ms (×2.37) | 166ms (×2.44) | 140ms (×1.90) |
| `get_deduplication_intake_form_intake_form_results` | 161ms (×2.37) | 168ms (×2.44) | 141ms (×1.90) |
| `list_tasks_for_request` | 162ms (×2.37) | 170ms (×2.44) | 148ms (×1.90) |
| `submit_task_decision` | 197ms (×1.00) | 206ms (×1.00) | 182ms (×1.00) |
| **Total time for 1 intake submission approved** | **2.61s** | **2.77s** | **4.50s** |

Pod-3's `search_in_intake_form_submissions` ratio (×14.37, vs. ×1.85/×1.54
at Pod-1/Pod-2) is an outlier worth confirming on re-run before trusting
this pod's total — everything else in the chain moves in the expected
direction.

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 24 | 40 | 64 |
| RPS to serve 1 intake submission approved (Locust users ÷ Total time) | 9.199 | 14.453 | 14.224 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 276 | 434 | 427 |

##### Volume-Tier: Stretch

_(pending — no Stretch-tier run yet)_

##### Volume-Tier: Stress

_(pending — no Stress-tier run yet)_

#### In-Cluster

##### Volume-Tier: Primary

###### Capacity Calculations

**register_read** — 1 register record fully read:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_a_register` | 133ms (×1.00) | 102ms (×1.00) | 118ms (×1.00) |
| `get_subject_record` | 119ms (×1.00) | 79ms (×1.00) | 104ms (×1.00) |
| `get_all_tabs` | 87ms (×1.00) | 58ms (×1.00) | 76ms (×1.00) |
| `get_tab_sections` | 127ms (×6.94) | 90ms (×6.96) | 114ms (×6.94) |
| `get_tab_records` | 155ms (×6.94) | 111ms (×6.96) | 140ms (×6.94) |
| `get_number_of_pending_change_requests` | 113ms (×6.94) | 78ms (×6.96) | 101ms (×6.94) |
| `get_change_requests` | 127ms (×6.93) | 90ms (×6.95) | 115ms (×6.93) |
| `get_change_request_documents` | 109ms (×0.27) | 71ms (×0.24) | 101ms (×0.36) |
| `get_section_ui_schema` | 110ms (×0.27) | 70ms (×0.24) | 103ms (×0.36) |
| `get_change_request` | 140ms (×0.27) | 99ms (×0.24) | 135ms (×0.36) |
| `list_tasks_for_request` | 114ms (×0.27) | 81ms (×0.24) | 110ms (×0.36) |
| `get_deduplication_change_request_results` | 115ms (×0.27) | 73ms (×0.24) | 103ms (×0.36) |
| `get_deduplication_register_results` | 113ms (×0.27) | 71ms (×0.24) | 104ms (×0.36) |
| `get_number_of_versions` | 122ms (×6.93) | 86ms (×6.95) | 112ms (×6.93) |
| `get_version_dates` | 117ms (×6.92) | 82ms (×6.95) | 107ms (×6.93) |
| `get_versions_for_a_date` | 122ms (×6.02) | 88ms (×5.86) | 114ms (×5.97) |
| **Total time for 1 register record** | **6.54s** | **4.60s** | **6.00s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 16 | 20 | 36 |
| RPS to serve 1 register record (Locust users ÷ Total time) | 2.448 | 4.345 | 6.003 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 73 | 130 | 180 |

**cr_create** — 1 change request effected:

`get_attribute_values` recorded 0 requests in this run, same as Primary
end-to-end, and is excluded from the chain below.

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_a_register` | 122ms (×0.38) | 141ms (×0.39) | 201ms (×0.39) |
| `get_subject_record` | 91ms (×0.20) | 91ms (×0.20) | 154ms (×0.20) |
| `get_all_sections` | 82ms (×0.20) | 80ms (×0.20) | 137ms (×0.20) |
| `get_all_tabs` | 67ms (×0.20) | 66ms (×0.20) | 117ms (×0.20) |
| `get_tab_sections` | 103ms (×1.40) | 99ms (×1.40) | 170ms (×1.40) |
| `get_tab_records` | 127ms (×1.40) | 121ms (×1.40) | 202ms (×1.40) |
| `create_change_request` | 221ms (93% of CRs) | 218ms (93% of CRs) | 330ms (93% of CRs) |
| `create_change_request_for_core_data` | 237ms (7% of CRs) | 240ms (7% of CRs) | 353ms (7% of CRs) |
| **Total time for 1 change request effected** | **0.64s** | **0.63s** | **1.01s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 12 | 20 | 44 |
| RPS to serve 1 change request created (Locust users ÷ Total time) | 18.785 | 31.747 | 43.512 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 564 | 952 | 1305 |

**cr_read_and_approve** — 1 change request approved:

_Captured before the change that limits `cr_read_and_approve` to pending
tasks only — expect the ×/unit ratios below (and the derived RPS/real-user
figures) to shift once this scenario is re-run._

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_change_request` | 159ms (×0.24) | 153ms (×0.16) | 152ms (×0.29) |
| `get_change_request_documents` | 108ms (×2.67) | 69ms (×2.07) | 102ms (×2.21) |
| `get_section_ui_schema` | 106ms (×2.67) | 67ms (×2.07) | 101ms (×2.21) |
| `get_change_request` | 138ms (×2.67) | 93ms (×2.07) | 133ms (×2.21) |
| `get_deduplication_change_request_results` | 110ms (×2.66) | 70ms (×2.07) | 104ms (×2.21) |
| `get_deduplication_register_results` | 109ms (×2.66) | 69ms (×2.07) | 103ms (×2.20) |
| `list_tasks_for_request` | 111ms (×2.63) | 79ms (×2.07) | 112ms (×2.13) |
| `submit_task_decision` | 159ms (×1.00) | 110ms (×1.00) | 153ms (×1.00) |
| **Total time for 1 change request approved** | **2.01s** | **1.06s** | **1.63s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 12 | 12 | 28 |
| RPS to serve 1 change request approved (Locust users ÷ Total time) | 5.961 | 11.337 | 17.132 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 179 | 340 | 514 |

**intake_create** — 1 intake submission created:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `render_intake_form` | 114ms (×1.01) | 88ms (×1.00) | 79ms (×1.01) |
| `save_intake_form_submission` | 284ms (×9.05) | 229ms (×9.02) | 210ms (×9.03) |
| `get_intake_form_submission` | 205ms (×1.00) | 164ms (×1.00) | 152ms (×1.00) |
| `finalize_intake_form_submission` | 284ms (×1.00) | 239ms (×1.00) | 228ms (×1.00) |
| **Total time for 1 intake submission created** | **3.18s** | **2.56s** | **2.36s** |

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 16 | 24 | 28 |
| RPS to serve 1 intake submission created (Locust users ÷ Total time) | 5.036 | 9.389 | 11.877 |
| T_real | 60s | 60s | 60s |
| Real concurrent users | 302 | 563 | 713 |

**intake_read_and_approve** — 1 intake submission approved:

| API | Pod-1 avg ms (×/unit) | Pod-2 avg ms (×/unit) | Pod-3 avg ms (×/unit) |
|---|---|---|---|
| `search_in_intake_form_submissions` | 197ms (×2.81) | 103ms (×10.02) | 210ms (×35.63) |
| `get_intake_form_submission` | 197ms (×4.14) | 134ms (×2.33) | 158ms (×1.94) |
| `get_intake_form_documents` | 131ms (×4.14) | 84ms (×2.33) | 102ms (×1.94) |
| `get_deduplication_intake_form_register_results` | 131ms (×4.14) | 84ms (×2.33) | 102ms (×1.94) |
| `get_deduplication_intake_form_intake_form_results` | 131ms (×4.14) | 84ms (×2.33) | 102ms (×1.94) |
| `list_tasks_for_request` | 131ms (×4.14) | 92ms (×2.33) | 108ms (×1.94) |
| `submit_task_decision` | 158ms (×1.00) | 123ms (×1.00) | 126ms (×1.00) |
| **Total time for 1 intake submission approved** | **3.70s** | **2.27s** | **8.71s** |

Pod-3's `search_in_intake_form_submissions` ratio (×35.63, vs. ×2.81/×10.02
at Pod-1/Pod-2) is a larger outlier than the same scenario's End-to-End
Primary run — worth confirming on re-run before trusting this pod's total.

| | Pod-1 | Pod-2 | Pod-3 |
|---|---|---|---|
| Locust users (peak, this run) | 16 | 28 | 80 |
| RPS to serve 1 intake submission approved (Locust users ÷ Total time) | 4.330 | 12.337 | 9.181 |
| T_real | 30s | 30s | 30s |
| Real concurrent users | 130 | 370 | 275 |

##### Volume-Tier: Stretch

_(pending — no Stretch-tier run yet)_

##### Volume-Tier: Stress

_(pending — no Stress-tier run yet)_

These are still `1-isolated` runs, each scenario measured with the pod
running only that workload — each figure is that scenario's ceiling in
isolation, not additive. A pod serving the real mixed workload contends
for the same DB connections, CPU, and AWE capacity across all five
scenarios at once, so the real mixed-workload concurrent-user number is
lower than each isolated figure.

### 5. Blended capacity, scaling, and data-volume sensitivity (Step 2)

Primary-tier raw data exists — Pod-Scale 1/2/3, `Step: 2-blended` (see
[`raw-report.md`](raw-report.md)) — but it's a **fixed-concurrency** run
(20/28/48 simulated users respectively), not a ramp-to-failure, so it
gives a measured floor on each pod's blended capacity, not the confirmed
SLO ceiling `test-scenarios.md` calls for:

| Pod-Scale | Concurrent users | Requests | Failures | p95 | Aggregated RPS |
|---|---|---|---|---|---|
| Pod-1 | 20 | 29,216 | 2 | 420ms | 66.26 |
| Pod-2 | 28 | 50,486 | 3 | 440ms | 93.39 |
| Pod-3 | 48 | 62,520 | 2 | 290ms | 122.26 |

Horizontal scaling efficiency from this floor: Pod-2 ≈70% of linear
(93.39 ÷ (2×66.26)), Pod-3 ≈61% of linear (122.26 ÷ (3×66.26)) — both
below the isolated-tier scaling seen in §4, consistent with AWE being a
shared, fixed-capacity bottleneck under the blended mix (§4, §8).

In-Cluster has the same cell now, also fixed-concurrency (12/16/32 users):

| Pod-Scale | Concurrent users | Requests | Failures | p95 | Aggregated RPS |
|---|---|---|---|---|---|
| Pod-1 | 12 | 28,469 | 0 | 220ms | 71.03 |
| Pod-2 | 16 | 40,560 | 0 | 270ms | 89.98 |
| Pod-3 | 32 | 49,486 | 0 | 140ms | 123.70 |

Scaling efficiency: Pod-2 ≈63% of linear (89.98 ÷ (2×71.03)), Pod-3 ≈58% of
linear (123.70 ÷ (3×71.03)) — close to End-to-End's, so the sub-linear
scaling itself isn't an RP artifact.

**Ingress comparison, same cells:** at every Pod-Scale, In-Cluster reaches
essentially the same (Pod-1, Pod-3) or slightly lower (Pod-2) RPS as
End-to-End, but with roughly 35-45% fewer concurrent users doing it
(Pod-1: 12 vs 20; Pod-2: 16 vs 28; Pod-3: 32 vs 48) and zero measured
failures throughout versus End-to-End's handful. This is the RP-hop latency
[`environment-topology.md`](../environment-topology.md) calls out — it adds
per-request latency (so Little's Law needs more concurrent users to sustain
the same RPS end-to-end) without capping the throughput ceiling itself at
this load level; the two ingresses' near-equal RPS ceilings say the RP
(`t3a.medium`, 2 vCPU) isn't yet the bottleneck at these cells.

#### Estimating Real Concurrent Users

The blended run only reports one pool of simulated Locust users — it
doesn't break down which real-user-equivalent load that represents,
because (unlike the isolated tables in §4) its per-endpoint stats mix
requests from all 5 scenarios together. Two things already known are
enough to estimate it without a blended-specific breakdown: the blend's
**weight distribution** (§4: register_read 40%, cr_read_and_approve 20%,
intake_read_and_approve 20%, cr_create 10%, intake_create 10% — since
Locust spawns users by weight, a blended run frozen at `B` total Locust
users has `weight × B` simulated users of each scenario type, even though
the run's own stats don't say so directly), and each scenario's **per-unit
server time**, computed the same way §4 now computes every isolated
scenario's RPS — summing each API's own average response time (weighted
by how many times it fires per unit), not reading a directly-measured
throughput number. That choice matters here for the same reason it does in
§4: `shared/base_user.py`'s `wait_time = between(0.5, 2.0)` pauses every
simulated user between `@task` iterations, throttling any *observed*
throughput figure, but never entering a request's own response time — so
summing response times and dividing headcount by that sum gives a rate
untouched by the pause, with `T_real` substituted in deliberately in its
place:

```
A = total Locust users in the blended run (this cell)
B (per scenario) = weight(scenario) × A
C (per scenario) = Σ [ avg ms(endpoint) × fires-per-unit(endpoint, scenario) ] over that scenario's chain
D (per scenario) = B ÷ C           — RPS implied by B simulated users each taking C seconds/unit
E (per scenario) = T_real(scenario)
real_users(scenario) = D × E
real_users(blended cell) = Σ real_users(scenario)
```

`C` is measured **from the blended run itself** — each endpoint's own
average response time as recorded in the blended run's per-endpoint
breakdown (`raw-report.md`'s `2-blended` table), not the `1-isolated` one,
so it reflects actual blended-load contention (all 5 scenarios sharing
DB/CPU/AWE capacity at once), not isolated-tier conditions.

One thing still carries over from isolated data and can't be avoided: each
endpoint's **fires-per-unit ratio** (`§4`'s ×N.NN multiplier — e.g.
`get_tab_sections` firing ~6.94× per `register_read` record). Several
endpoints are shared across scenarios in the blend — `get_subject_record`
(register_read *and* cr_create), `submit_task_decision`
(cr_read_and_approve *and* intake_read_and_approve), and others — so the
blended run's raw request *counts* for those endpoints mix multiple
scenarios' traffic with no way to attribute a call back to the scenario
that issued it. A ratio computed from blended counts would be
contaminated. **Average response time doesn't have this problem** — an
endpoint's latency under blended load is the same number regardless of
which scenario's user happened to call it — so only the *time* component
(`C`) is sourced from the blended run; the fires-per-unit structure stays
from isolated data as a workflow constant (seed-data shape and task
logic, not a load-dependent quantity).

**End-to-End:**

*Pod-1 (A = 20):*

| Scenario | B (Locust users) | C (time, blended) | D = B÷C (RPS) | E (T_real) | Real users = D×E |
|---|---:|---:|---:|---:|---:|
| register_read | 8.00 | 10.18s | 0.786 | 30s | 23.6 |
| cr_create | 2.00 | 1.17s | 1.712 | 30s | 51.4 |
| cr_read_and_approve | 4.00 | 2.94s | 1.360 | 30s | 40.8 |
| intake_create | 2.00 | 3.98s | 0.503 | 60s | 30.2 |
| intake_read_and_approve | 4.00 | 3.17s | 1.262 | 30s | 37.9 |
| **Total** | **20.00** | — | — | — | **≈183.8** |

Blended ratio: 183.8 ÷ 20 = **9.2×**

*Pod-2 (A = 28):*

| Scenario | B (Locust users) | C (time, blended) | D = B÷C (RPS) | E (T_real) | Real users = D×E |
|---|---:|---:|---:|---:|---:|
| register_read | 11.20 | 8.20s | 1.365 | 30s | 41.0 |
| cr_create | 2.80 | 0.97s | 2.895 | 30s | 86.9 |
| cr_read_and_approve | 5.60 | 2.29s | 2.450 | 30s | 73.5 |
| intake_create | 2.80 | 3.37s | 0.831 | 60s | 49.9 |
| intake_read_and_approve | 5.60 | 2.51s | 2.227 | 30s | 66.8 |
| **Total** | **28.00** | — | — | — | **≈318.0** |

Blended ratio: 318.0 ÷ 28 = **11.4×**

*Pod-3 (A = 48):*

| Scenario | B (Locust users) | C (time, blended) | D = B÷C (RPS) | E (T_real) | Real users = D×E |
|---|---:|---:|---:|---:|---:|
| register_read | 19.20 | 9.32s | 2.060 | 30s | 61.8 |
| cr_create | 4.80 | 1.10s | 4.378 | 30s | 131.4 |
| cr_read_and_approve | 9.60 | 2.36s | 4.074 | 30s | 122.2 |
| intake_create | 4.80 | 3.73s | 1.287 | 60s | 77.2 |
| intake_read_and_approve | 9.60 | 4.76s | 2.018 | 30s | 60.6 |
| **Total** | **48.00** | — | — | — | **≈453.1** |

Blended ratio: 453.1 ÷ 48 = **9.4×**

**In-Cluster:**

*Pod-1 (A = 12):*

| Scenario | B (Locust users) | C (time, blended) | D = B÷C (RPS) | E (T_real) | Real users = D×E |
|---|---:|---:|---:|---:|---:|
| register_read | 4.80 | 5.83s | 0.823 | 30s | 24.7 |
| cr_create | 1.20 | 0.69s | 1.745 | 30s | 52.3 |
| cr_read_and_approve | 2.40 | 1.89s | 1.270 | 30s | 38.1 |
| intake_create | 1.20 | 2.12s | 0.567 | 60s | 34.0 |
| intake_read_and_approve | 2.40 | 3.64s | 0.659 | 30s | 19.8 |
| **Total** | **12.00** | — | — | — | **≈168.9** |

Blended ratio: 168.9 ÷ 12 = **14.1×**

*Pod-2 (A = 16):*

| Scenario | B (Locust users) | C (time, blended) | D = B÷C (RPS) | E (T_real) | Real users = D×E |
|---|---:|---:|---:|---:|---:|
| register_read | 6.40 | 4.42s | 1.448 | 30s | 43.4 |
| cr_create | 1.60 | 0.57s | 2.828 | 30s | 84.8 |
| cr_read_and_approve | 3.20 | 1.14s | 2.810 | 30s | 84.3 |
| intake_create | 1.60 | 2.21s | 0.723 | 60s | 43.4 |
| intake_read_and_approve | 3.20 | 2.42s | 1.322 | 30s | 39.7 |
| **Total** | **16.00** | — | — | — | **≈295.6** |

Blended ratio: 295.6 ÷ 16 = **18.5×**

*Pod-3 (A = 32):*

| Scenario | B (Locust users) | C (time, blended) | D = B÷C (RPS) | E (T_real) | Real users = D×E |
|---|---:|---:|---:|---:|---:|
| register_read | 12.80 | 6.51s | 1.966 | 30s | 59.0 |
| cr_create | 3.20 | 0.76s | 4.192 | 30s | 125.8 |
| cr_read_and_approve | 6.40 | 1.82s | 3.515 | 30s | 105.4 |
| intake_create | 3.20 | 2.96s | 1.080 | 60s | 64.8 |
| intake_read_and_approve | 6.40 | 6.53s | 0.981 | 30s | 29.4 |
| **Total** | **32.00** | — | — | — | **≈384.4** |

Blended ratio: 384.4 ÷ 32 = **12.0×**

In-Cluster Pod-3's `intake_read_and_approve` contribution (29.4, that
cell's smallest of the five) is built on a `C` that inherits the same
`search_in_intake_form_submissions` Pod-3 outlier already flagged in §4 —
its fires-per-unit ratio is structurally inflated there, so this figure
should be treated as a lower bound until that isolated scenario is
re-run.

This computation is consistent with §4's isolated-tier method — both
derive RPS from `Locust users ÷ Σ per-request response times` rather than
a directly-observed throughput number, so both are equally unaffected by
`shared/base_user.py`'s `wait_time = between(0.5, 2.0)`, which is still
active on every simulated user across every tier and would otherwise
throttle any observed-throughput figure without reflecting anything about
`T_real`.

Synthesizing this into the curated `blended-capacity.csv`
and a proper scaling/volume-sensitivity chart is still pending — see
[`test-scenarios.md`](test-scenarios.md) §3.

### 6. Endurance / soak (Step 3)

One cell run: **In-Cluster, Primary, Pod-Scale 3**, full 8h (28,800s) via
[`k8s/soak-job.yaml`](../../locust/api/k8s/soak-job.yaml) /
[`soak_locustfile.py`](../../locust/api/staff-api/blended/soak_locustfile.py)
— the same 80:20 weighted mix as Step 2 (§4), but run without
`SLOStepRampShape`: a fixed `SOAK_USERS=36` (ramped at `-r 2`, no
SLO/CPU-breach freeze logic) with total HTTP throughput capped at
`SOAK_MAX_RPS=172` so CPU doesn't climb back to the ramp's closed-loop
ceiling once latency settles. **This is not "80% of this cell's Step 2 max
RPS"** as originally planned (§3, §7): Step 2 at this cell measured 123.70
RPS at 32 users (§5); this soak ran 36 users capped at 172 RPS and actually
sustained ~154-170 RPS throughout — roughly **130% of the Step 2 figure**,
not 80% of it. The 36-user/172-RPS combination was instead chosen to hold
pod CPU near 1.7-1.8 of the 2-vCPU limit (`k8s/soak-job.yaml` comment) —
worth reconciling with `test-scenarios.md`'s stated Step 3 definition
before citing this as "the" soak methodology.

**Throughput and latency:** stable for the full 8h, no decay —

| t (h) | RPS | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| 0.5 | 166.6 | 140ms | 300ms | 530ms | 14.0s |
| 2.0 | 168.3 | 130ms | 290ms | 560ms | 16.0s |
| 4.0 | 165.1 | 110ms | 270ms | 540ms | 16.0s |
| 6.0 | 167.2 | 110ms | 260ms | 530ms | 28.0s |
| 8.0 | 169.7 | 110ms | 260ms | 530ms | 31.0s |

p50/p95 actually *improve* slightly over the run (140→110ms / 300→260ms);
p99 is flat at ~530-560ms — no latency creep on the percentiles the SLOs
are defined against (§5). The **max** (100th percentile) is the one
metric that visibly grows — 1.2s in the first half-hour to 14-16s by hour
2, then 28-31s from hour 6 on — a small number of increasingly severe
tail-latency outliers, not visible in p99. Worth isolating (which
endpoint, which pod, timed with what else) before dismissing as noise.

**Errors:** 34 failures out of 4,733,071 requests over 8h (0.0007%),
arriving in a scattered trickle throughout the run (`soak_failures.csv`),
not concentrated or accelerating toward the end — two distinct causes:
- **24 of 34** are `AWE-ERR-006` connection resets talking to AWE
  (`list_tasks_for_request`, `submit_task_decision`,
  `finalize_intake_form_submission`) — direct, fresh evidence for the
  AWE-hop bottleneck already flagged from isolated-tier data (§4, §8).
- **10 of 34** are `SYS-ERR-001` on `create_change_request` — a **new**
  finding, not the same bug as `get_record_history`'s (different endpoint,
  different code path; `SYS-ERR-001` is a generic wrapper code, not
  evidence of a shared root cause). Not yet investigated.

**Memory:** pod CPU/memory panels for all 3 Pod-3 replicas
(`locust/api/results/staff-api/in-cluster/primary/pod-3/3-soak/pod-*.png`)
show CPU oscillating 1.5-2 of the 2-vCPU limit throughout (matching the
`SOAK_MAX_RPS` design target), and memory climbing **steadily and
near-linearly on all three pods** — roughly 362→385-400 MiB over the 8h
(~7-10% growth), never plateauing. This is a real, consistent trend across
replicas, not a one-off — but it's modest and still rising at the 8h mark,
so it's a **borderline result**: neither a flat pass nor an unambiguous
leak. A longer soak (or a heap/object-count profile) is needed to tell
"grows then plateaus" (fine) from "unbounded" (not). DB connection counts
weren't captured for this run (not part of `soak_stats_history.csv` or the
pod dashboards pulled) — a gap against the deliverable's own definition
(§2 deliverable 7).

**Verdict:** provisional PASS on throughput/error-rate/percentile-latency
stability; **memory trend is a watch item, not a clean pass** — see above.
Caveat the whole cell on the RPS-target deviation noted above before
treating it as validating "80% of Step 2 max."

### 7. Database ceiling (`db-sweep`)
Pending — no `db-sweep` run exists yet. Planned source:
[`raw-report.md`](raw-report.md)'s `Step: 4-db-sweep` sections
(hand-recorded readings), a latency-vs-volume chart, and the top
`pg_stat_statements`.

### 8. Bottlenecks & tuning

Nine changes were reported as identified/applied against this list; each
is checked here against the actual commit history in the `registry-platform`,
`awe`, `iam`, and `openg2p-fastapi-common` repos (this `venky-github`
checkout, which is ahead of `openg2p-github` on all four) rather than taken
at face value.

**1. AWE worker/pool tuning — applied, but not literally Gunicorn.**
`awe` commit `072e943` ("Increase UVICORN workers...") raised
`UVICORN_WORKERS` 1→2 in the `Dockerfile`. `docker-entrypoint.sh` still
runs `exec uvicorn awe.main:app --workers "${UVICORN_WORKERS}"` directly —
there is no `gunicorn` dependency or invocation anywhere in the `awe` repo,
so this is uvicorn's own multi-worker flag, not a Gunicorn-managed
uvicorn-worker setup. The same commit also changed `db.py`'s *default*
pool_size/max_overflow (used only when the env vars are unset) from 20/15
back to 10/5 — but the deployed values come from
`helm/openg2p-awe/values.yaml`, which an earlier same-day commit
(`155463b`) set to `DB_POOL_SIZE=5`/`DB_POOL_MAX_OVERFLOW=10`. Net effect
in production: total connection ceiling is unchanged at 15, just
re-split (smaller persistent pool, larger overflow) and now
environment-configurable instead of hardcoded (see item 8).

**2. Composite index in registry-platform — applied.**
`ix_change_requests_lookup` on
`g2p_register_change_requests(register_id, internal_record_id, tab_id, created_at)`,
added in `59209d7` (G2P-5507, backing `get_change_requests_flattened`) and
extended with `approval_status` in `5c0a396` (G2P-5510, backing
`get_number_of_pending_change_requests`). A separate, non-composite index
was also added on `g2p_registers.last_approved_at` in `c8efcac` (G2P-5513,
`search_in_a_register`). None of this touches the `get_register_summary_data`
count path — see item 5.

**3. iam-core oidc_client/jwks ContextVar fix — applied.** `iam` commit
`4c1888b` (G2P-5647, "Implement caching for JWKS and OIDC metadata")
replaces both `jwks_cache` and `server_metadata_cache` — previously plain
`ContextVar`s, the same copy-per-asyncio-Task bug flagged earlier in this
conversation — with `fastapi_cache` `@cache` decorators on `get_jwks`
(`jwks_helper.py`) and `get_server_metadata` (`oidc_client.py`), keyed by
issuer/`jwks_uri` and login-provider id respectively, each with its own
5-minute TTL (`auth_jwks_cache_ttl_seconds` / `auth_oidc_metadata_cache_ttl_seconds`).
Backed by `FastAPICache.init(InMemoryBackend(), prefix="iam-cache")`
(`iam_core/user_auth/cache.py`) — genuinely process-wide, unlike the
`ContextVar` it replaces — and covered by tests
(`test_helpers_and_middleware.py`, `test_oidc_and_adapters.py`). `iam` is
now checked out on `performance-test` (the branch this fix lives on,
matching `registry-platform` and this repo), confirming the ~1000ms
`get_subject_record` cost reported earlier is fixed at the code level.

**4. Connection pooling via singleton session-maker — applied.**
`openg2p-fastapi-common` commit `17057b7` (G2P-5620) replaced the
per-call `async_sessionmaker(dbengine.get())` construction with
`get_async_session_maker()`, backed by `GlobalVar` (a plain instance
attribute, not a `ContextVar` — genuinely process-wide) and memoized after
first build. Pool size/overflow are now `Settings` fields
(`db_pool_size`/`db_pool_max_overflow`, defaults 5/10). `registry-platform`
adopted it the same day (`41147a9`, G2P-5620) across its services.

**5. Registry-platform caching changes, Aug 12 – Sep 2 (this checkout) —
applied, mixed effect.** In commit order:
  - `59209d7`/`5c0a396`/`c8efcac`/`4342369`/`7ade042`/`3fa183e` (G2P-5507–5513,
    Aug 12): per-endpoint tuning for `get_change_requests_flattened`,
    `get_number_of_pending_change_requests`, `get_subject_record`,
    `get_all_tabs`, `get_version_dates`, `get_versions_for_a_date`,
    `search_in_a_register` — mostly the indexes in item 2 plus new cached
    helpers `_get_register_definition`/`_require_register_definition` and
    `_get_tab_sections` (`single_id_key_builder`/`pair_id_key_builder`),
    reused across several of these methods instead of re-querying inline.
  - `b852f24` (G2P-5514): wrapped `get_register_summary_data` itself in
    `@cache(key_builder=data_policies_key_builder)` (TTL fixed at 60s in
    `0699d12`), and moved tab→sections assembly in
    `g2p_register_metadata_service` behind a similar cache, replacing an
    N-per-section validation loop with one join query. **This masks but
    does not fix** the underlying per-register N+1 unindexed `COUNT(*)` —
    see item 5's continuation below and the original finding in this
    conversation: the 60s cache absorbs repeat calls, but a cold cache or
    TTL expiry under load still pays the full sequential-scan cost, and
    concurrent misses aren't coalesced (a stampede risk `fastapi-cache`'s
    `@cache` doesn't address). The proposed
    `pg_stat_user_tables.n_live_tup` approximate-count fix was not applied.
  - `0699d12` (G2P-5609): namespaced, invalidated `@cache` on AWE-policy
    resolution (`policy_lookup_key_builder`, explicit
    `FastAPICache.clear(namespace=...)` on create/update/delete) — correctly
    designed and covered by unit tests (cache-hit, cache-miss-on-different-key,
    invalidation-on-write).
  - `37284e2`: the same thin-cached-wrapper-plus-`_assemble_*` pattern
    extended to intake-form services (`render_intake_form`, `get_all_tabs`,
    `get_all_sections`).
  - `2ef461b`: validation-method refactors in the same services, no new
    caching primitives.

**6. Async AWE-request creation for `create_cr`/`finalize_intake` —
identified as a candidate, not yet applied.** Both still call AWE
synchronously to create the workflow. A Celery worker/beat setup already
exists in this codebase (`celery/openg2p-registry-celery-beat`) for the
data-ingest pipeline, but nothing yet routes AWE request creation through
a queue table or a Celery task.

**7. Second AWE call in `list_tasks_for_request` — not found in the repo.**
`awe_helper.py`'s `list_tasks_for_request` still makes two sequential
`_list_tasks` calls (`assignee="*"` then `assignee="me"`) — unchanged
since it was introduced (`0ac9dce`), across all branches, no uncommitted
diff. Same caveat as item 3: this is still the contributor behind §4's
`list_tasks_for_request` p95 growth and needs confirming before it's
cited as resolved.

**8. AWE connection-pool parameters made configurable — applied.**
`DB_POOL_SIZE`/`DB_POOL_MAX_OVERFLOW`/`DB_POOL_RECYCLE` env vars, added in
`155463b` and adjusted in `072e943` (both `awe`) — see item 1 for the
actual deployed numbers.

**9. PgBouncer added for connection pooling — applied, infra-level, not
yet load-tested.**
[`postgres-settings/pgbouncer-config.txt`](../../postgres-settings/pgbouncer-config.txt)
(added `0520f97`, alongside the Primary-tier seed) configures a PgBouncer
instance in front of the host PostgreSQL — `pool_mode = transaction`,
`listen_port = 6432`, `default_pool_size = 50`, `min_pool_size = 10`,
`reserve_pool_size = 10` (`reserve_pool_timeout = 5s`),
`max_client_conn = 200`; see §3 for the full settings table. This is an
infra-level change — no application code references PgBouncer directly,
app pods connect to `:6432` instead of Postgres' own port — addressing
[`environment-topology.md`](../environment-topology.md)'s note that
connection pooling in front of the host Postgres is "usually the real
ceiling" on this topology. Whether it actually raises that ceiling isn't
validated yet: that's exactly what `db-sweep` (§7, still pending) is for.

**Also confirmed while auditing the above (not in the original list):**
`155463b` added several more indexes on AWE's own tables
(`ApprovalTask`, `ApprovalRequest`, `ApprovalDecision`, `ApprovalEvent`,
`UserDelegation`), switched `list_tasks`/`decide` from `selectinload` to
`joinedload` to fold a decision's owning-request lookup into one query
instead of a second `session.get()`, reduced `search_requests`'s max
`limit` from 500 to 100, and added a 5-minute in-process TTL cache for
`_load_policy` (`engine.py`). `resolver.py`'s dead `_ResolutionCache` and
`auth_id_type_config_cache`'s `ContextVar` bug (both flagged earlier in
this conversation) remain unaddressed — real gaps for `role`/`group`
approver rules and for the sibling `auth_models` package respectively, but
a no-op on the current `rule_type='user'` seed data.

### 9. Pass / fail vs SLO/NFR
Pending overall PASS/FAIL — no ramp-to-failure SLO run exists yet (§4 has
isolated data, §5 a fixed-concurrency blended floor; neither is a ramp).
`register_read`'s `get_record_history` (§2's upstream `SYS-ERR-001` bug)
was dropped from the task code after the Smoke dry run and doesn't appear
in any run since. The one completed endurance check — the 8h In-Cluster
soak (§6) — is a **provisional pass with a watch item**: throughput,
error rate (0.0007%), and p95/p99 latency held stable for the full window,
but pod memory climbed steadily on all 3 replicas without plateauing, and
the soak logged two real error types (AWE connection resets, and a new
`SYS-ERR-001` on `create_change_request`) — see §6 for the caveat that
this run's load level doesn't match the documented "80% of Step 2" methodology.

### 10. Recommendations & sizing guide
- **Production sizing:** partially computable. Primary-tier blended data
  exists (§5): Pod-Scale 1 sustains **≥66.3 RPS** blended over `primary`
  at p95 ≈420ms with near-zero failures — but at a **fixed 20-user load**,
  not a ramp-to-failure, so this is a measured floor on `R`, not the
  SLO-confirmed ceiling `test-scenarios.md` defines. A fully validated
  sizing figure still needs (a) a ramp-to-failure blended run per
  Volume-Tier/Pod-Scale cell, and (b) the DB ceiling `D` from `db-sweep`
  (§7, not yet run) to bound total pods against.
- **Config recommendations:** item 3 (JWKS/OIDC cache fix) is confirmed
  active now that `iam` is checked out on `performance-test`; confirm
  item 7 actually landed (it doesn't appear in any `awe` branch checked)
  before treating it as done; the remaining open items from §8 — moving
  AWE-request creation onto Celery (item 6), the
  `get_register_summary_data` approximate-count fix (item 5), and
  validating PgBouncer's effect under load (item 9, `db-sweep`) — are
  still open.
- **Follow-ups / known limits:** async-pipeline throughput for the
  AWE-request-creation queue (item 6 above) is separate from the existing
  ingest-pipeline Celery deployment and not covered by this round's
  scenarios ([`test-scenarios.md`](test-scenarios.md) §1/§2).
- **New from the soak run (§6):** `create_change_request`'s `SYS-ERR-001`
  (10 occurrences over 8h) hasn't been root-caused — needs its own
  investigation, distinct from `get_record_history`'s. The soak's
  memory-growth trend (all 3 Pod-3 replicas, still rising at 8h) warrants
  either a longer soak or a heap profile before calling it benign.
  `test-scenarios.md`'s Step 3 definition ("80% of Step 2 max RPS") should
  be reconciled with what `soak-job.yaml` actually runs (fixed users +
  RPS cap, targeted at a CPU band instead) — whichever is intended, the
  other should be fixed to match.

### 11. Appendix
- Raw Locust CSVs, Grafana dashboard exports (`locust/api/results/staff-api/in-cluster/primary/pod-3/3-soak/pod-*.png`), `pg_stat_statements` dumps.
- Locust config + seed manifest + exact postgresql.conf diffs.

## Conventions

- Always report **p95 and p99** (not p95 alone) and **error rate by type**.
- Every number carries its **pinned config** (Pod-Scale, worker count,
  Volume-Tier, DB tuning) — a bare "RPS" is meaningless without it.
- Report **median of ≥2 runs** plus spread; flag any run-to-run variance
  > ~10%.
- State the **ingress point** (in-cluster vs end-to-end) for every figure.

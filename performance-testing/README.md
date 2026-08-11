# Farmer Registry — Performance & Scale Testing

This directory holds the performance-testing programme for the **OpenG2P Farmer
Registry**: the test plan, the environment/topology it targets, the workload
model, data-seeding strategy, the execution runbook, the expected outputs, and
the Locust load-test assets.

The exercise establishes, with evidence:

1. **Per-pod capacity** — the true max RPS a single, resource-constrained API
   pod serves at its latency SLO with zero failures, discovered by ramping
   load until failure.
2. **Stability over time** — that capacity does not decay over an 8-hour soak
   (no memory leaks, connection-pool exhaustion, or error creep).
3. **Horizontal scaling factor** — how RPS grows from 1 → 2 → 3 pods (always
   sub-linear; we quantify the multiplier) — derived by comparing results
   across Pod-Scale, not a separately run test.
4. **Database ceiling** — the RPS / data-volume at which the (host) PostgreSQL
   node becomes the bottleneck, across tuning/sizing scenarios (`db-sweep`).
5. A **capacity / sizing model** — the headline deliverable: *"to serve X RPS
   over Y million records at the target SLOs, you need N app pods + a DB of
   size Z."*

Async pipeline throughput (Celery ingestion/outgestion/dedup) is **out of
scope for this round** — API-tier only until the matrix below is done.

Every result is a point in a **Volume-Tier** (smoke/primary/stretch/stress) ×
**Pod-Scale** (1/2/3 replicas) matrix, filled in by repeating a fixed 3-Step
plan (Isolated → Blended → Soak) at whichever cells matter — plus `db-sweep`,
a related but separate exercise. See
[`documentation/staff-api/test-scenarios.md`](documentation/staff-api/test-scenarios.md) §3.

## Documents

| File | Purpose |
|------|---------|
| [`documentation/environment-topology.md`](documentation/environment-topology.md) | The 3-node production target, node sizing, what runs where, and the constraints/gotchas that shape the tests. |
| [`documentation/seeding-design.md`](documentation/seeding-design.md) | Target Volume-Tiers, the bulk generator's design (generation DAG, search-anchor rationale, why fields are generator-computed), known simplifications. |
| [`documentation/staff-api/test-scenarios.md`](documentation/staff-api/test-scenarios.md) | Objectives, scope, the Volume-Tier/Pod-Scale/Step model, the workload model, the 5 Locust scenarios (APIs fired, search-anchor usage), SLOs, pass/fail criteria, execution runbook. |
| [`documentation/staff-api/raw-report.md`](documentation/staff-api/raw-report.md) | Auto-generated (`scripts/create_raw_report.py`): every measurement Locust actually recorded, verbatim, per Ingress/Volume-Tier/Pod-Scale/Step/Scenario. No interpretation. |
| [`documentation/staff-api/final-report.md`](documentation/staff-api/final-report.md) | The interpretation layer: deliverables checklist, capacity/sizing-model narrative, SLO verdicts, and the final written report skeleton — built from `raw-report.md`. |
| [`documentation/partner-api/test-scenarios.md`](documentation/partner-api/test-scenarios.md) | **Deferred** — placeholder; `partner-api` has no working Locust flows yet. |
| [`documentation/celery/test-scenarios.md`](documentation/celery/test-scenarios.md) | **Deferred** — placeholder; async-pipeline throughput testing is undesigned. |
| [`seeding/`](seeding/) | The bulk seed generator (install/run quick-start — see `seeding-design.md` for the why). |
| [`locust/api/`](locust/api/) | Locust load-test scripts against `staff-portal-api`/`partner-api` — 5 working staff-api scenarios, results, and per-Step CSV templates. |
| [`locust/celery/`](locust/celery/) | Async-pipeline throughput tooling — deferred, scaffolded only. |
| [`scripts/`](scripts/) | `create_raw_report.py` (raw dump, first output) and `synthesize_report.py` (fills the curated `locust/api/templates/staff-api/synthesize_templates/*.csv`, second output) from raw Locust run output. |

## Status

This is the **test-plan specification** plus a **working staff-api Locust
harness and bulk seeder** — 5 scenarios exist and run
([`documentation/staff-api/test-scenarios.md`](documentation/staff-api/test-scenarios.md) §4).
It does not yet contain a full result set: no blended-mix locustfile (needed
for Steps 2–3), and `locust/celery/` tooling is undesigned/deferred.
Execution produces the artefacts described in
[`documentation/staff-api/final-report.md`](documentation/staff-api/final-report.md), built on
top of the raw measurements in
[`documentation/staff-api/raw-report.md`](documentation/staff-api/raw-report.md).

> Scope note: the plan targets the **Farmer Registry**, but the methodology,
> workload model, and tooling apply unchanged to NSR and any other registry
> built on the OpenG2P Registry platform — only the register mnemonics and
> seed data differ.

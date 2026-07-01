# Farmer Registry — Performance & Scale Testing

This directory holds the performance-testing programme for the **OpenG2P Farmer
Registry**: the test plan, the environment/topology it targets, the workload
model, data-seeding strategy, the execution runbook, the expected outputs, and
starter load-test assets.

The exercise establishes, with evidence:

1. **Per-pod capacity** — the sustainable requests/sec (RPS) a single, resource-
   constrained API pod serves while meeting its latency SLO with zero failures.
2. **Stability over time** — that capacity does not decay over an 8-hour soak
   (no memory leaks, connection-pool exhaustion, or error creep).
3. **Horizontal scaling factor** — how RPS grows from 1 → 2 → 3 pods (always
   sub-linear; we quantify the multiplier).
4. **Database ceiling** — the RPS / data-volume at which the (host) PostgreSQL
   node becomes the bottleneck, across tuning/sizing scenarios.
5. **Async pipeline throughput** — records/sec for ingestion / outgestion /
   deduplication (Celery), which are throughput-bound, not latency-bound.
6. A **capacity / sizing model** — the headline deliverable: *"to serve X RPS
   over Y million records at the target SLOs, you need N app pods + a DB of
   size Z."*

## Documents

| File | Purpose |
|------|---------|
| [`01-test-plan.md`](01-test-plan.md) | Master plan: objectives, scope, refined methodology, phases, SLOs, pass/fail criteria. |
| [`02-environment-and-topology.md`](02-environment-and-topology.md) | The 3-node production target, node sizing, what runs where, and the constraints/gotchas that shape the tests. |
| [`03-workload-model.md`](03-workload-model.md) | The endpoint catalogue (real registry-platform routes), per-endpoint SLOs, read/write/async classification, and the blended workload mix. |
| [`04-data-seeding.md`](04-data-seeding.md) | Target data volumes and how to seed them (db-seed image + bulk generation), including history/supporting-table growth. |
| [`05-execution-runbook.md`](05-execution-runbook.md) | Step-by-step procedure for each phase, including pinning, warm-up, and steady-state measurement. |
| [`06-outputs-and-report.md`](06-outputs-and-report.md) | The benchmark outputs/deliverables and the final report template. |
| [`locust/`](locust/) | Starter Locust load-test scripts (auth + tasks for the key endpoints). |
| [`templates/`](templates/) | CSV result templates and the report skeleton. |

## Status

This is the **test-plan specification** (the "what" and "how"). It does not yet
contain results. Execution produces the artefacts described in
[`06-outputs-and-report.md`](06-outputs-and-report.md).

> Scope note: the plan targets the **Farmer Registry**, but the methodology,
> workload model, and tooling apply unchanged to NSR and any other registry
> built on the OpenG2P Registry platform — only the register mnemonics and
> seed data differ.

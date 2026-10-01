# Test Scenarios — celery (async pipelines)

**Status: harness written, not yet executed.** Measurement is a closed
Postgres backlog drained by **1 beat pod** and **1, 2, or 3 worker pods**,
snapshotted at 5/10/15/20/25/30 minutes. It is not a Locust user class.
See [`../../locust/celery/README.md`](../../locust/celery/README.md).

## Still outside this harness

Outgestion, score-computation, and the partner ingest pipeline are not cases
yet. The first cases are functional-id allocation, the four dedup producers,
and intake-to-register ingest. Unlike staff-api and partner-api, this is not
request/response latency. The unit is rows moved out of `PENDING` by the
checkpoint, plus Redis queue depth.

`get_deduplication_register_results` / `get_deduplication_change_request_results`
in [`../staff-api/test-scenarios.md`](../staff-api/test-scenarios.md) are a
concrete link to this tier: those staff-api calls only *fetch* results this
pipeline already computed — this doc will eventually cover the cost of doing
that computation, which staff-api's Register-Read numbers deliberately don't
include.

## Reports

Checkpoint CSVs from `locust/celery/results/` are the raw record. A
`raw-report.md` / `final-report.md` for this tier can be written after the
first matrix (case × worker count × cohort size) exists. Shape it around
`done_delta` at each mark and Redis depth, not the staff-api
Ingress/Volume-Tier/Pod-Scale/Step tables.

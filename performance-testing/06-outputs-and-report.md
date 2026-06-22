# Benchmark Outputs & Report

These are the artefacts the exercise must produce — the "what gets submitted"
for API scale testing of a registry. CSV/MD templates are in
[`templates/`](templates/).

## The deliverables

| # | Output | Form | From phase |
|---|--------|------|-----------|
| 1 | **Per-API capacity table** — endpoint, method, max sustainable RPS @ SLO, p50/p90/p95/p99/max, error %, saturating resource | table | 1 |
| 2 | **Per-pod resource profile** at max RPS (pod CPU, mem, DB conns) | table + graphs | 1 |
| 3 | **Latency-vs-RPS ("knee") and RPS-vs-users curves** | charts | 1 |
| 4 | **Soak/endurance report** — RPS, p95, error rate, pod memory, DB conns over 8h; memory-trend verdict | time-series graphs | 2 |
| 5 | **Horizontal scaling table + curve** — RPS at 1/2/3 pods; efficiency; limiting factor | table + chart | 3 |
| 6 | **DB capacity table** — threshold RPS + first bottleneck per tuning/volume/VM scenario; top slow queries | table | 4 |
| 7 | **Data-volume sensitivity** — key read/search latency vs 1M→100M | chart | 4 |
| 8 | **Async pipeline throughput** — records/sec, queue depth, drain time, worker utilisation | table + graphs | 5 |
| 9 | **Bottleneck & tuning findings** — what saturated first; config changes that moved it (worker count, pool size, indexes, PgBouncer, max_connections, gp3 IOPS) | narrative | all |
| 10 | **Capacity / sizing model** — the headline business output (below) | formula/table | 6 |
| 11 | **Pass/fail vs SLO/NFR** | table | 6 |
| 12 | **Methodology + reproducible assets** — Locust scripts, env spec, versions, seed manifest | doc + repo | all |

Items **4, 5, 6, and 10** are what reviewers/funders care about most: proof of
no time-decay, the scaling factor, the DB ceiling, and the sizing formula.

## The capacity / sizing model (headline output)

The synthesis must yield a statement operators can plan against, e.g.:

> *On the 3-node production profile (compute `m5a.4xlarge`, host-PG
> `t3a.2xlarge`), one `1 vCPU / 4 GB` staff-portal-api pod sustains **R** RPS of
> the blended workload at p95 ≤ SLO over 10 M farmer records. Scaling to 3 pods
> yields **R₃** RPS (efficiency **e**). The host PostgreSQL becomes the
> bottleneck at **D** RPS (tuned + PgBouncer), driven by `<bottleneck>`.
> Therefore, to serve a target of **T** RPS over **V** million records at the
> SLOs, provision **⌈T/R⌉** app pods (bounded by the DB ceiling D), a DB of
> **`<size>`** with **`<max_connections>`** via PgBouncer, and **W** Celery
> workers to sustain **I** records/sec ingestion.*

with the variables filled from the measured results.

## Report

Use [`templates/report-template.md`](templates/report-template.md) as the
skeleton. It maps 1:1 to the deliverables above. Final report sections:

1. Executive summary (headline numbers + sizing model)
2. Environment & methodology (pinned config)
3. Per-API capacity (Phase 1)
4. Endurance/soak (Phase 2)
5. Horizontal scaling (Phase 3)
6. Database ceiling (Phase 4)
7. Async throughput (Phase 5)
8. Bottlenecks & tuning
9. Pass/fail vs SLO/NFR
10. Recommendations & sizing guide
11. Appendix: raw data, Locust configs, seed manifest, dashboards

## Conventions

- Always report **p95 and p99** (not p95 alone) and **error rate by type**.
- Every number carries its **pinned config** (pod size, worker count, data
  volume, DB tuning) — a bare "RPS" is meaningless without it.
- Report **median of ≥2 runs** plus spread; flag any run-to-run variance > ~10%.
- State the **ingress point** (in-cluster vs end-to-end) for every figure.

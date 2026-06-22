# Farmer Registry — Scale & Performance Test Report

> Fill this in from the measured results. Sections map 1:1 to
> `../06-outputs-and-report.md`.

## 1. Executive summary
- **Headline:** 1 pod (1 vCPU/4 GB) sustains **___ RPS** blended @ p95 ≤ SLO over **___ M** records.
- **Scaling:** 3 pods → **___ RPS** (efficiency **___**).
- **DB ceiling:** **___ RPS** (tuned + PgBouncer), limited by **______**.
- **Async ingestion:** **___ records/sec** at **___** workers.
- **Sizing model:** to serve **T RPS** over **V M** records → **___ app pods + DB `___` + ___ workers**.
- **Verdict vs SLO/NFR:** PASS / FAIL — _____.

## 2. Environment & methodology
- Chart version / image tags / git SHA: ______
- Nodes: compute `m5a.4xlarge` (16/64), storage host-PG `t3a.2xlarge` (8/32, T3-unlimited: __), RP `t3a.medium`.
- Pod under test: 1 vCPU / 4 GB, `requests==limits`, HPA off, workers = __.
- PostgreSQL 16: tuning = ______; PgBouncer = ______; max_connections = __.
- Data volume(s): ______. Ingress point(s): in-cluster / end-to-end.
- Load tool: Locust ___; run location: ______; model: closed/open.

## 3. Per-API capacity (Phase 1)
_Insert `results-per-api.csv` as a table + latency-vs-RPS "knee" charts._

## 4. Endurance / soak (Phase 2)
- Load: 80% of blended max = ___ RPS, 8h.
- Memory trend: ______ (leak? Y/N). Error rate over time: ______. p95 drift: ______.
_Insert time-series graphs._

## 5. Horizontal scaling (Phase 3)
_Insert `scaling-factor.csv` + curve. Limiting factor at 3 pods: ______._

## 6. Database ceiling (Phase 4)
_Insert `db-capacity.csv` + latency-vs-volume chart + top `pg_stat_statements`._

## 7. Async pipeline throughput (Phase 5)
_Insert `async-throughput.csv` + queue-depth/drain graphs._

## 8. Bottlenecks & tuning
- First bottleneck per phase: ______
- Changes that moved it (worker count / pool size / indexes / PgBouncer / max_connections / gp3 IOPS): ______

## 9. Pass / fail vs SLO/NFR
_Per endpoint class: target p95/p99 vs achieved; PASS/FAIL._

## 10. Recommendations & sizing guide
- Production sizing for target load: ______
- Config recommendations (defaults to change in the chart): ______
- Follow-ups / known limits: ______

## 11. Appendix
- Raw Locust CSVs, Grafana dashboard exports, `pg_stat_statements` dumps.
- Locust config + seed manifest + exact postgresql.conf diffs.

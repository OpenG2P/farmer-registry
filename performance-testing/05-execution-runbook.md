# Execution Runbook

Step-by-step procedure. Run phases in order; each depends on the previous.
Record the [environment pinning checklist](02-environment-and-topology.md#environment-pinning-checklist-record-in-every-result-set)
at the start of every result set.

## Phase 0 — Preparation

1. **Freeze versions** — chart version, image tags, git SHA, Postgres version.
2. **Seed data** to the chosen tier (start at 10 M) per
   [`04-data-seeding.md`](04-data-seeding.md); `ANALYZE`; verify indexes; warm cache.
3. **De-burst the DB node** — enable T3 Unlimited on the storage node, or move PG
   to a non-burstable instance for the duration.
4. **Stand up observability** — Prometheus/Grafana for pod+node CPU/mem;
   `postgres_exporter` + `pg_stat_statements` on the storage node; Redis queue
   metrics. Confirm dashboards show live data.
5. **Pin the pod under test** — `replicas: 1`, HPA off, `requests == limits` at
   **1 vCPU / 4 GB**. Sweep gunicorn/uvicorn `NO_OF_WORKERS ∈ {1,2,4}` at a fixed
   moderate load and keep the value with best RPS-at-SLO; record it.
6. **Deploy Locust** in-cluster (for per-pod/scaling) and/or on an external host
   (for end-to-end). Load the seed manifest. Validate one of each request type
   returns 2xx before load.

## Phase 1 — Per-pod capacity

For each API class (and then the blended mix):
1. Warm up 3–5 min at low load; **discard** this window.
2. Ramp users stepwise (e.g. +N users every 60–120 s) so each step reaches
   steady state. Hold each step long enough for stable percentiles.
3. At each step record: RPS, p50/p90/p95/p99/max, error count by type, pod
   CPU/mem, DB connections, DB CPU/IO.
4. Identify **max RPS** = highest step where p95 ≤ SLO **and** errors = 0 **and**
   pod CPU≈100% or mem≈100%. Note the saturating resource.
5. Repeat each point ≥ 2× on separate runs; report median + spread.

Deliverable: per-API capacity table (+ the latency-vs-RPS "knee" chart).

## Phase 2 — Soak (endurance)

1. Set load to **80% of the blended max RPS** from Phase 1.
2. Run **8 hours** continuously.
3. Watch for: upward memory trend (leak), growing DB connections (pool/handle
   leak), latency creep, any errors, Celery backlog growth.
4. Pass = SLOs hold + 0 errors + flat memory for the full window.

Deliverable: time-series graphs (RPS, p95, error rate, pod memory, DB conns).

## Phase 3 — Horizontal scaling

1. Set `replicas: 2` (same per-pod size, HPA still off). Re-run the blended
   capacity test → record max RPS(2).
2. Set `replicas: 3` → record max RPS(3).
3. Compute **scaling efficiency** = RPS(n) ÷ (n × RPS(1)).
4. At each step capture **node-level** CPU/mem (shared compute node) and DB
   connections — identify whether the app, the node, or the DB caps scaling.

Deliverable: scaling table + curve, with the limiting factor named.

## Phase 4 — Database ceiling

For each scenario below, drive a read/write mix from enough app pods to push the
DB, raising load to the **point of failure** (errors / p95 breach / connection
exhaustion / IOPS saturation); record the threshold RPS and the first bottleneck:

1. **Tuning sweep** (same VM): baseline postgresql.conf → tuned (`shared_buffers`
   ≈ 25% RAM, `effective_cache_size` ≈ 50–75% RAM, `work_mem`, `max_connections`,
   autovacuum) → **+ PgBouncer** (transaction pooling).
2. **Data-volume sweep:** 1M → 10M → 50M → 100M (re-`ANALYZE`/warm each).
3. **VM resize (optional):** storage 8/32 → 16/64 (non-burstable).
4. **I/O (optional):** raise gp3 IOPS/throughput if disk-bound.

Deliverable: DB capacity table (RPS + first bottleneck per scenario) + latency-vs-
volume chart + top `pg_stat_statements` offenders.

## Phase 5 — Async pipeline throughput

1. **Ingestion:** submit a large batch via `partner-api /partner/ingest_data`;
   measure records/sec end-to-end, Redis queue depth over time, worker CPU/mem,
   and backlog-drain time. Scale `celery-worker` replicas to find the throughput
   curve.
2. Repeat for **outgestion** and **deduplication** pipelines.
3. (Optional) overlay a fixed ingestion rate during a Phase-1 blended run to
   measure read/write contention.

Deliverable: pipeline throughput table + queue-depth/drain graphs.

## Phase 6 — Synthesis

1. Assemble all tables/graphs into the report
   ([`templates/report-template.md`](templates/report-template.md)).
2. Derive the **capacity / sizing model** (see
   [`06-outputs-and-report.md`](06-outputs-and-report.md)).
3. List bottlenecks found and the tuning that moved them.
4. Map results to the SLOs/NFR targets → pass/fail summary.

## Useful inspection commands

```bash
# pod resource use (needs metrics-server / Prometheus)
kubectl top pod -n <ns> -l app.kubernetes.io/name=staff-portal-api

# pod limits actually applied
kubectl get pod -n <ns> <pod> -o jsonpath='{.spec.containers[0].resources}'

# live DB connections + activity (on storage node / via psql)
psql -c "SELECT state,count(*) FROM pg_stat_activity GROUP BY state;"
psql -c "SELECT * FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;"

# Redis (Celery broker) queue depth
kubectl exec -n <ns> <release>-redis-master-0 -- redis-cli LLEN registry_worker_queue
```

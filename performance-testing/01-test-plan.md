# Farmer Registry — Performance & Scale Test Plan

## 1. Objectives

Establish, with reproducible evidence on the production-equivalent 3-node
deployment:

1. **Per-pod API capacity** — max sustainable RPS for each API class while
   meeting its latency SLO with zero failures, at a fixed pod size.
2. **Time-stability** — that per-pod capacity holds over an 8-hour soak (no
   memory leak, connection leak, latency creep, or error growth).
3. **Horizontal scaling factor** — measured RPS at 1 → 2 → 3 pods and the
   scaling efficiency (actual ÷ ideal-linear).
4. **Database ceiling** — RPS and latency vs **data volume** and vs PostgreSQL
   tuning/sizing scenarios, including the connection-pool ceiling.
5. **Async pipeline throughput** — records/sec for ingestion, outgestion, and
   deduplication (Celery), plus queue-drain time and worker utilisation.
6. **Capacity / sizing model** — the headline output (see
   [`06-outputs-and-report.md`](06-outputs-and-report.md)).

## 2. Scope

**In scope**
- Synchronous APIs of `staff-portal-api` and `partner-api` (see
  [`03-workload-model.md`](03-workload-model.md)).
- Async pipelines executed by `celery-worker` / `celery-beat-producer`.
- Host PostgreSQL on the storage node; Redis broker; MinIO object store.
- Auth on the hot path (Keycloak OIDC token validation).

**Out of scope (this round)**
- Staff Portal **UI** (Next.js) front-end rendering — API-tier only.
- Keycloak / MinIO / Kafka internal scaling (treated as provided dependencies;
  monitored, not the subject under test).
- bene-portal-api (disabled by default).
- Chaos/failover/DR testing (separate exercise).

## 3. Methodology (refined)

The methodology refines the original thought-process with four corrections that
the production topology and registry architecture make necessary
(see [`02-environment-and-topology.md`](02-environment-and-topology.md)):

- **Seed to target data volume *before* the app-tier benchmark.** Registry read
  APIs are DB-bound and size-sensitive; benchmarking on an empty DB produces
  numbers that the DB phase then invalidates. Pick the target volume first
  (see [`04-data-seeding.md`](04-data-seeding.md)), seed it, warm it, then measure.
- **Per-endpoint SLOs, not a single 1s target** (see §5).
- **Benchmark the async pipeline separately** as throughput, not request latency.
- **Pin concurrency and DB connections** (worker count per pod; pool size;
  PgBouncer; Postgres `max_connections`) and treat them as first-class variables.

### Phases

| Phase | Question it answers | Output |
|------|---------------------|--------|
| **0. Prep** | Is the rig pinned, seeded, warmed, observable? | Baseline env record |
| **1. Per-pod capacity** | What RPS does 1 constrained pod sustain per API at its SLO with zero failures, at resource saturation? | Per-API capacity table |
| **2. Soak** | Does that hold for 8h at 80% of max? | Endurance time-series |
| **3. Horizontal scaling** | What RPS at 2 and 3 pods? Scaling factor? | Scaling curve |
| **4. DB ceiling** | At what combined RPS / data volume does host PG become the bottleneck, across tuning/sizing scenarios? | DB capacity table |
| **5. Async throughput** | Records/sec for ingest/outgest/dedup; queue-drain time? | Pipeline throughput table |
| **6. Synthesis** | What's the sizing model + bottleneck/tuning findings? | Capacity model + report |

### Phase 1 — per-pod capacity (per API class)

1. Pin the pod under test: **1 vCPU / 4 GB**, `requests == limits`, `replicas: 1`,
   HPA off. Tune and record the gunicorn/uvicorn **worker count** (the image
   default is `NO_OF_WORKERS=8`, which over-subscribes 1 vCPU — sweep `{1,2,4}`
   and pick the best; document).
2. Warm up (token cache, connection pool, PG cache) — discard the ramp window.
3. Ramp Locust users for **one API class at a time** against the warm,
   target-volume DB.
4. Find **max RPS** where simultaneously: **p95 ≤ the endpoint SLO**,
   **0 failures**, and **the pod is saturated** (CPU ~100% *or* memory ~100%).
   Record which resource saturated.
5. Repeat per API class; also run the **blended mix** (§ workload model).

### Phase 2 — soak

- Drive **80% of max RPS** for **8 hours** continuously (blended mix).
- Pass = p95 stays within SLO, error rate stays 0, and **memory does not trend
  upward** (no leak), DB connections stable, no latency creep.

### Phase 3 — horizontal scaling

- Repeat the blended capacity test at **2** then **3** replicas (HPA still off,
  same per-pod size). Record RPS and **scaling efficiency** = RPS(n) ÷ (n × RPS(1)).
- Watch node-level CPU/mem (shared compute node) and DB connections — scaling
  usually flattens because of the DB/connection ceiling, not the app.

### Phase 4 — DB ceiling

- With app pods fixed at the count that saturates the DB, drive a **read/write
  mix at the target data volume**; raise load to the **point of DB failure**
  (errors, p95 breach, connection exhaustion, IOPS saturation). Record the
  threshold.
- Repeat across scenarios:
  - **Tuning:** baseline postgresql.conf → tuned (shared_buffers,
    effective_cache_size, work_mem, max_connections) → **+ PgBouncer**.
  - **Data volume:** 1M → 10M → 50M → 100M farmer records.
  - **VM resize (optional):** storage node 8/32 → 16/64 (non-burstable).
  - **I/O (optional):** gp3 3000 → higher IOPS/throughput if disk-bound.
- Document RPS achieved per scenario and the first bottleneck each time.

### Phase 5 — async throughput

- Submit bulk ingestion via `partner-api /partner/ingest_data`; measure
  **records/sec** end-to-end, **queue depth** (Redis), worker CPU/mem, and
  **backlog-drain time**. Repeat for outgestion and deduplication.

## 4. Workload

See [`03-workload-model.md`](03-workload-model.md) for the endpoint catalogue,
per-endpoint SLOs, and the blended read/write/async mix.

## 5. Service-Level Objectives (per endpoint class)

| Class | Examples | p95 SLO | p99 SLO |
|------|----------|--------:|--------:|
| Metadata / config read (cacheable) | schemas, tabs, sections, attributes | 200 ms | 400 ms |
| Record read | `get_subject_record`, `get_section_records`, `get_tab_records`, scores | 300 ms | 600 ms |
| Search (paginated) | `search_in_a_register`, intake search, DCI `sync/search` | 1000 ms | 1500 ms |
| Deduplication (fuzzy, `pg_trgm`) | `get_deduplication_*_results` | 1500 ms | 2500 ms |
| Write — intake | `save/finalize_intake_form_submission` | 800 ms | 1200 ms |
| Write — change request | `create/approve/reject_change_request` | 800 ms | 1200 ms |
| Verification / doc metadata | `add_verification`, `get_file_url` | 500 ms | 800 ms |
| Document upload (MinIO) | `upload_documents` | 1500 ms (size-dependent) | — |
| Async ingestion/outgestion/dedup | Celery | **throughput target (records/sec)**, not latency | — |

> These SLO numbers are the **proposed starting targets** — confirm against the
> registry NFR document and any programme/funder commitments before execution,
> then freeze them for the run.

## 6. Pass / fail criteria

A configuration **passes** at a given RPS when, at steady state:
- p95 (and p99) ≤ the endpoint SLO, **and**
- error rate = 0 (no 5xx, no timeouts, no DB-connection errors), **and**
- for the soak: the above hold for the full 8h with no upward memory/latency trend.

The **reported max RPS** is the highest load satisfying all three at the defined
resource-saturation stop condition.

## 7. Risks & gotchas (must mitigate)

- Burstable `t3a` storage node throttling under sustained DB load → enable T3
  Unlimited or use non-burstable for DB phases.
- Shared single compute node → other platform pods add noise; run in quiet
  windows, capture node-level metrics, record co-tenants.
- gunicorn worker count vs 1 vCPU → tune, don't accept the default 8.
- DB connection exhaustion (pods × workers × pool) → size pools, use PgBouncer.
- Benchmarking through the 2-vCPU RP for end-to-end runs → RP can cap throughput;
  separate that finding from the microservice's own capacity.
- Token endpoint accidentally under test → cache tokens in the load script.
- DB grows during write phases → pre-size or measure write throughput separately.

## 8. Deliverables

See [`06-outputs-and-report.md`](06-outputs-and-report.md).

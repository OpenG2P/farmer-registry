# Environment & Topology

The benchmark targets the **OpenG2P 3-node production deployment** defined in
`openg2p-deployment/automation/production`. Understanding what runs where — and
the constraints each node imposes — is essential, because they directly shape
how the test must be run and how results are interpreted.

## The 3 nodes (default AWS sizing)

| Node | Instance | vCPU / RAM | Disk | Role |
|------|----------|-----------|------|------|
| Reverse Proxy (RP) | `t3a.medium` | **2 / 4 GB** | 64 GB gp3 @ 3000 IOPS | Public ingress: WireGuard endpoint + admin Nginx + TLS. The internet-facing hop. |
| **Compute** | `m5a.4xlarge` | **16 / 64 GB** | 128 GB gp3 @ 3000 IOPS | Single **RKE2 Kubernetes** node. Runs **all** application pods. |
| **Storage** | `t3a.2xlarge` | **8 / 32 GB** | 256 GB gp3 @ 3000 IOPS | **Host PostgreSQL 16** (not a K8s pod) + NFS server. |

Source: `automation/production/aws/aws-config.example.yaml` and `prod-config.example.yaml`.

## What this means for the test (read carefully)

These topology facts change the original thought-process in concrete ways:

1. **All app pods share ONE compute node (16 vCPU / 64 GB).**
   The 1-pod / 2-pod / 3-pod horizontal-scaling test runs on the *same* node, so
   the pods compete for the same cores and for the node with **all the platform
   pods** (Keycloak, Redis, MinIO, Kafka, Istio, master-data, eSignet, Superset,
   observability, AWE, …). Realistic free headroom for the registry pods is well
   under 16 vCPU — budget perhaps ~8–10 vCPU. **Capture node-level CPU/mem
   throughout** and treat node saturation as a real ceiling, not just pod limits.

2. **PostgreSQL is host-based on the storage node — not a K8s pod.**
   The original plan's "provision a DB pod with 4 CPU / 16 GB, then 6/24, then
   8/24, increase # of DB pods" does **not** map here. On this prod the DB is a
   single host Postgres on a fixed 8 vCPU / 32 GB VM. Therefore DB "scaling" is:
   - **postgresql.conf tuning** (shared_buffers, work_mem, effective_cache_size,
     max_connections, autovacuum) — the primary, in-place lever.
   - **Connection pooling** (PgBouncer) in front — usually the real ceiling.
   - **VM resize** as discrete scenarios (e.g. 8/32 → 16/64) — a provisioning
     change, not a `kubectl scale`.
   - Optional **read replica** for the read-heavy search/dedup load.

3. **The storage node is a BURSTABLE `t3a` instance (CPU credits).**
   Under sustained DB load (and especially the 8-hour soak), a t3a can **exhaust
   CPU credits and throttle**, which would silently corrupt results. Before DB
   load tests either (a) enable **T3 Unlimited** mode, or (b) temporarily run the
   DB on a **non-burstable** instance (e.g. `m5a`/`m6a` of equal vCPU). The
   compute node (`m5a`) is non-burstable — fine as-is.

4. **gp3 at 3000 IOPS / 125 MB/s is a fixed I/O ceiling.**
   Large-table scans (search/dedup over 50–100M rows) and write-heavy phases can
   saturate disk before CPU. Monitor disk IOPS/throughput/await on the storage
   node. Bumping gp3 IOPS/throughput is a documented scenario if I/O-bound.

5. **Two ingress points — measure both, label clearly.**
   - **In-cluster** (Locust pod → service ClusterIP): isolates the microservice;
     use this for per-pod capacity and scaling-factor numbers.
   - **End-to-end** (through RP Nginx → Istio gateway → Keycloak): the real-world
     latency users see. Note the RP is only `t3a.medium` (2 vCPU) and can itself
     bottleneck end-to-end throughput — that's a finding, not a defect.

6. **Auth is on the hot path.** Every API validates an OIDC token against
   Keycloak (`commons-keycloak`). Use realistic tokens; account for token-cache
   effects (fetch once, reuse until expiry — see `locust/`). Don't accidentally
   benchmark Keycloak's token endpoint instead of the registry.

7. **Audit middleware** logs every API call (non-blocking, to
   `commons-services-auditmanager`). It adds per-request overhead and its own
   load — keep it enabled (production-representative) and note it.

## Test rig

- **Load generator (Locust):** run as a pod (or small deployment) **on the
  cluster** for in-cluster tests so the generator isn't bottlenecked by the RP /
  internet. For end-to-end tests, run Locust from a separate, well-provisioned
  host (not the 3 nodes) hitting the public hostname. Never co-locate Locust on
  the compute node under test.
- **Metrics:** the prod stack ships Prometheus + Grafana (rancher-monitoring) and
  OpenTelemetry + Loki. Use these for pod CPU/mem, node CPU/mem, and app logs.
  For the host Postgres, use `node_exporter` / `postgres_exporter` on the storage
  node (install for the test window) plus `pg_stat_statements`.
- **Isolation:** disable HPA, set `requests == limits` on the pod under test,
  and run during a quiet window (shared compute node). Record everything that
  else is running on the node at test time.

## Environment pinning checklist (record in every result set)

- Chart version + image tags (registry images, `appVersion`), git SHA.
- Node instance types + whether T3 Unlimited was enabled on storage.
- Pod resource requests/limits and **gunicorn/uvicorn worker count**
  (the API Dockerfiles default to `NO_OF_WORKERS=8` — see workload model; this
  must be tuned for a 1-vCPU pod and recorded).
- PostgreSQL version + the postgresql.conf values changed + PgBouncer settings.
- Data volume (row counts per register + history + supporting tables).
- Locust version, run location (in-cluster vs external), and config.

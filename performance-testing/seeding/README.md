# Bulk seed generator — quick start

Generates realistic, high-volume `Farmer` register data (households, farmers,
household members, lands, crops, livestock, farm inputs, membership details,
and `*_history` twins) directly into PostgreSQL via `COPY`. Design notes live in
[`../documentation/seeding-design.md`](../documentation/seeding-design.md).
This file is install, run, and the command list.

**Primary tier = 10 million farmers** (not 20M). Each live row also gets a
history twin, so farmer live+history ≈ 20M rows, and all tables together ≈ 200M.

## Indexing — nothing manual in the happy path

`SEED_DEFER_INDEXES` defaults to **on**. You do **not** run `CREATE INDEX` by
hand after a successful 10M load.

1. The first pod drops non-PK indexes on **live and history** tables (PK stays).
2. All pods COPY in parallel.
3. The **last pod to finish** rebuilds every dropped index from
   `_seed_deferred_indexes`, then `ANALYZE`s the tables, then drops the helper
   tables.

Watch the last-finishing pod for:

```text
[db] last writer: rebuilding deferred indexes
[index] rebuild 1/N ...
[analyze] g2p_register_farmers
[seed] pod=… wall time …
```

The other pod logs `[db] N writer(s) still running; skipping index rebuild`
and exits. That is expected.

Do **not** start Locust / benchmark searches until rebuild + ANALYZE finish.
During COPY, `search_text ILIKE` will seq-scan; after rebuild, GIN/`pg_trgm`
should show up in `EXPLAIN`.

Leave indexes in place only for a smoke check:

```sh
export SEED_DEFER_INDEXES=false
python3 run.py --tier smoke
```

### Manual indexing — only if a pod dies mid-rebuild

If the last pod crashes after COPY but before `[index] rebuild` finishes, leftover
rows may sit in `_seed_deferred_indexes` / `_seed_active_writers`. Check:

```sql
SELECT * FROM _seed_active_writers;
SELECT tablename, left(indexdef, 80) FROM _seed_deferred_indexes;
```

- Empty / tables missing → indexes already rebuilt. Nothing to do.
- `_seed_active_writers` still has a dead pod id → `DELETE` that row, then
  re-run **one** seeder with `--workers 1` on an empty shard, or rebuild from
  the stored `indexdef` values (`CREATE INDEX …` exactly as stored). Prefer
  re-running the last pod (same Job) so the code path does it.
- Do not invent new index SQL; use the captured `indexdef` so GIN/`pg_trgm`
  matches production.

## Prerequisites

1. **Configuration/meta-data must already be loaded** — register definitions,
   schemas, UI tabs/sections, attribute lookups. Platform `db-seed` Job
   (`dbSeed.enabled=true`, **not** `dbSeed.loadSampleData=true`). The generator
   reads `g2p_register_definitions` / `g2p_register_sections` /
   `g2p_register_ui_tab_sections` and fails if they are missing.
2. **Run close to the DB** — COPY over a slow network link bottlenecks first.
3. Local: `pip install -r requirements.txt` (`psycopg2-binary`, `Faker`).
   On this machine the interpreter is `python3`.

## Commands

Set a namespace once if you use Kubernetes (this cluster uses `perftest`):

```sh
export NS=perftest
```

### Local — smoke (10K) then primary (10M)

```sh
cd performance-testing/seeding
pip install -r requirements.txt

export SEED_DB_DSN=postgresql://user:pass@host:5432/farmer_registry

# 10K sanity check (keep indexes)
SEED_DEFER_INDEXES=false python3 run.py --tier smoke

# 10M, one process (slow; prefer k8s below)
python3 run.py --tier primary

# 10M, two logical pods locally (ID ranges match k8s)
python3 run.py --tier primary --pod-index 0 --total-pods 2 --workers 4
python3 run.py --tier primary --pod-index 1 --total-pods 2 --workers 4
```

Optional flags / env:

| Flag / env | Default | Notes |
|---|---|---|
| `--dsn` | `SEED_DB_DSN` | Overrides DSN |
| `--pod-index` / `--total-pods` | 0 / 1 | Shard ID ranges |
| `--workers` / `SEED_WORKERS` | 1 | COPY processes inside one run |
| `SEED_DEFER_INDEXES` | `true` | Drop/rebuild non-PK indexes |
| `SEED_BATCH_SIZE` | `50000` | Do not raise with `--workers 4` (OOM) |
| `PGHOST` `PGPORT` `PGDATABASE` `PGUSER` `PGPASSWORD` | — | If set, used instead of DSN (k8s) |

### Kubernetes — 10M with 2 pods × 4 workers

Rebuild the image after code changes (`imagePullPolicy: Always`).

```sh
cd performance-testing/seeding/k8s

# 1. Image
./build_and_push.sh
# or: IMAGE_NAME=vin0dkhichar/farmer-registry-seeding IMAGE_TAG=v3 ./build_and_push.sh

# 2. Job YAML (writes jobs/seeding-primary-pod-{0,1}.yaml + kustomization.yaml)
#    -k needs a DIRECTORY, not a file. Do not: kubectl apply -k jobs/kustomization-primary.yaml
python3 generate_jobs.py --tier primary --pods 2 --workers 4 \
  --image vin0dkhichar/farmer-registry-seeding:v3 \
  --pg-host 172.29.2.191 \
  --pg-port 5432 \
  --pg-database farmer_registry \
  --pg-user farmer_registry_user \
  --db-secret farmer-registry \
  --db-secret-key farmer-registry-db-user \
  --cpu-request 250m --cpu-limit 4 \
  --memory-request 1Gi --memory-limit 8Gi

# 3. Replace any old run, then apply into the farmer-registry namespace
kubectl delete jobs -n "$NS" -l app=farmer-registry-seeding
kubectl apply -k jobs -n "$NS"
# equivalent:
# kubectl apply -n "$NS" -f jobs/seeding-primary-pod-0.yaml -f jobs/seeding-primary-pod-1.yaml

# 4. Watch
kubectl get jobs -n "$NS" -l app=farmer-registry-seeding -w
kubectl get pods -n "$NS" -l app=farmer-registry-seeding -o wide
kubectl logs -n "$NS" -l app=farmer-registry-seeding --tail=50 -f --prefix
```

Rancher: cluster **openg2p** → namespace **perftest** → Workloads → **Jobs**
(not Deployments). Jobs are `seeding-primary-pod-0` and `seeding-primary-pod-1`.

If pods stay **Pending / Insufficient cpu**, lower `--cpu-request` (250m is
what this node needed). If CrashLoop shows `unrecognized arguments: --workers`,
the node cached an old image — `imagePullPolicy: Always` plus a new tag/push.

### After both jobs Complete

```sh
# Confirm Complete, not still Running (index rebuild can take 30–90 min extra)
kubectl get jobs -n "$NS" -l app=farmer-registry-seeding
kubectl logs -n "$NS" job/seeding-primary-pod-0 --tail=80
kubectl logs -n "$NS" job/seeding-primary-pod-1 --tail=80

# Copy shard manifests (2 pods × 4 workers → seed_manifest_pod0.json … pod7.json)
mkdir -p manifests && cd manifests
for p in $(kubectl get pods -n "$NS" -l app=farmer-registry-seeding -o name); do
  kubectl cp -n "$NS" "${p#pod:}":/app/ ./ --retries=3 || true
done
# keep only seed_manifest_pod*.json, then:
python3 ../merge_manifests.py --tier primary --pods 2
```

`merge_manifests.py` globs `seed_manifest_pod*.json` in `--output-dir` (default `.`).

Then verify counts (SQL below), warm a few `ILIKE` searches, then Locust.

### Rebuild missing live indexes (Job)

The 10M seed restored **history** btrees only. Live UNIQUE/btree/GIN (including
`search_text`) must be created by this Job. Do not start Locust until it
finishes farmer GIN + ANALYZE.

```sh
export NS=perftest
cd performance-testing/seeding

kubectl delete job -n "$NS" rebuild-indexes --ignore-not-found
kubectl create configmap farmer-registry-rebuild-indexes \
  --from-file=rebuild_indexes.py=rebuild_indexes.py \
  -n "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/jobs/rebuild-indexes.yaml -n "$NS"

kubectl get jobs,pods -n "$NS" -l app=farmer-registry-rebuild-indexes
kubectl logs -n "$NS" -l app=farmer-registry-rebuild-indexes --tail=50 -f
```

The Job client is cheap; Postgres does the work. `activeDeadlineSeconds` is 16h.
Re-run is safe (`IF NOT EXISTS`).

### Reassign 10k search anchors on existing farmers (Job)

Does **not** reseed. Updates `first_name` / `record_name` / `search_text` only
(round-robin 10k 4-char terms, ~1k hits each on 10M rows). Drops farmer GIN
for the UPDATE, then rebuilds it + `ANALYZE`. Re-run replaces the 4-char
prefix if it is already one of the 10k terms.

```sh
export NS=perftest
cd performance-testing/seeding

kubectl delete job -n "$NS" reassign-search-anchors --ignore-not-found
kubectl create configmap farmer-registry-reassign-search-anchors \
  --from-file=reassign_search_anchors.py=reassign_search_anchors.py \
  -n "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/jobs/reassign-search-anchors.yaml -n "$NS"

kubectl get jobs,pods -n "$NS" -l app=farmer-registry-reassign-search-anchors
kubectl logs -n "$NS" -l app=farmer-registry-reassign-search-anchors --tail=50 -f
```

Do not start Locust until GIN rebuild + ANALYZE finish. Locust reads the
same 10k terms from `seed_manifest.json` (`search_terms`).

### Cleanup

```sh
kubectl delete jobs -n "$NS" -l app=farmer-registry-seeding
# or from k8s/: kubectl delete -k jobs -n "$NS"
```

### Original 10-pod layout (1 worker each)

```sh
cd performance-testing/seeding/k8s
python3 generate_jobs.py --tier primary --pods 10 --workers 1
kubectl apply -k jobs -n "$NS"
python3 merge_manifests.py --tier primary --pods 10
```

## Tiers

| Tier    | Farmers | Default pods | Use |
|---------|---------|--------------|-----|
| smoke   | 10K     | 1            | Sanity check |
| primary | **10M** | 10 (use **2** with `--workers 4`) | Headline benchmark |
| stretch | 50M     | 15           | Scaling |
| stress  | 100M    | 20           | Max load |

See `config.DATA_VOLUME_TIERS`. Batch size **50,000**. Session also sets
`synchronous_commit=off`, `work_mem=256MB`, `maintenance_work_mem=1GB`.

## Verify after seeding

```sql
SELECT relname, n_live_tup FROM pg_stat_user_tables
 WHERE relname LIKE 'g2p_register_%' ORDER BY n_live_tup DESC;

SELECT count(*) FROM g2p_register_farmers;          -- ~10_000_000
SELECT count(*) FROM g2p_register_history_farmers;  -- ~10_000_000

SELECT extname FROM pg_extension WHERE extname='pg_trgm';

-- leftover helper tables should be gone after a successful rebuild
SELECT to_regclass('_seed_active_writers'), to_regclass('_seed_deferred_indexes');

EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM g2p_register_farmers WHERE search_text ILIKE '%<an anchor>%' LIMIT 20;
```

Then warm the cache with representative reads before measuring.

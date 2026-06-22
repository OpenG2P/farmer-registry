# Data Seeding

Read-path latency (search, dedup, history) is **highly sensitive to table size**.
The DB must be seeded to the target volume — and warmed — **before** the app-tier
benchmark, not after. This document defines the target volumes and how to load
them.

## Target data volumes

| Tier | Farmer records | Purpose |
|------|---------------:|---------|
| Smoke | 10 K | Functional sanity of the harness; not a benchmark figure. |
| **Primary** | **10 M** | Headline national-farmer-registry scale; the figure most results are reported at. |
| Stretch | 50 M | Scaling/headroom characterisation. |
| Stress | 100 M | DB-ceiling and worst-case search/dedup behaviour. |

Per farmer, seed **proportional related rows** so the schema is realistic:

| Table | Rough ratio to farmers | Notes |
|---|---|---|
| `g2p_register_households` | ~0.3–0.5 × | Many farmers per household. |
| `g2p_register_household_members` | ~3–5 × | Members per household. |
| `g2p_register_lands` | ~1–2 × | Parcels per farmer. |
| `g2p_register_crops` | ~1–3 × | Crops per land. |
| `g2p_register_livestocks` | ~0.5–1 × | |
| `g2p_register_farm_inputs` | ~1 × | |
| `g2p_register_membership_details` | ~1 × | |
| `g2p_register_poverty_scores` | ~1 × per household | |
| `*_history` twins | ≥ 1 × edited rows | Seed history for a realistic % of edited records (e.g. 20–30%) so version/history reads aren't trivial. |

Confirm exact ratios with the domain team; the point is that supporting tables
and history are populated, not just the `Farmer` register.

## How to seed

### 1. Configuration / meta-data (always first)
The `openg2p-farmer-registry-db-seed` image loads register definitions, schemas,
UI tabs/sections, attribute lookups, registry config, and AWE meta-data. This is
run by the chart's db-seed Job (`dbSeed.enabled=true`). It is a prerequisite for
any data load. **Do not** use `dbSeed.loadSampleData=true` demo rows for scale
testing — that's a handful of demo records, not a volume tier.

### 2. Bulk register data (the volume tiers)
The demo sample-data path does not scale to millions. Use a **bulk generator**
that writes directly to PostgreSQL with realistic, indexed, varied data:

- Generate via `COPY` / batched multi-row `INSERT` (orders of magnitude faster
  than per-row API calls). Target ~50–100 K rows per batch inside a transaction.
- Populate **indexed/search columns** with high-cardinality, varied values
  (names, ids, geo, attributes) so `search_in_a_register` and `pg_trgm` dedup
  exercise the indexes realistically — not all-identical rows.
- Generate valid `functional_record_id` / `internal_record_id` values consistent
  with the platform's id scheme so reads-by-id resolve.
- After loading: `ANALYZE` every table (and `VACUUM ANALYZE`), verify indexes
  (incl. the `pg_trgm` GIN/GiST indexes) exist and are used (`EXPLAIN`), and
  **warm the cache** before measuring.
- Emit a **seed manifest** — a sample of valid ids / search terms across the full
  key space — for the load scripts to parameterise reads against (avoids hot-row
  cache-only reads). See `scripts/seed_bulk.md`.

> A generator is intentionally **not** committed here yet — it depends on the
> frozen schema and id scheme. `scripts/seed_bulk.md` specifies exactly what it
> must produce so it can be written against the final models.

### 3. Verify before benchmarking
```sql
-- row counts
SELECT relname, n_live_tup FROM pg_stat_user_tables
 WHERE relname LIKE 'g2p_register_%' ORDER BY n_live_tup DESC;

-- indexes exist and pg_trgm present
SELECT extname FROM pg_extension WHERE extname='pg_trgm';
\di+ *register*

-- a representative search uses an index (not a seq scan over 10M+ rows)
EXPLAIN (ANALYZE, BUFFERS) /* a search_in_a_register-equivalent query */;
```

## Storage sizing

100M farmer records + supporting tables + history + indexes can be **hundreds of
GB**. The storage node ships **256 GB gp3**. Confirm free space before the 50M/
100M tiers; resize the data disk if needed (and remember gp3 IOPS is a separate
ceiling — see [`02-environment-and-topology.md`](02-environment-and-topology.md)).

## Reset between tiers

Keep tiers reproducible: snapshot the storage volume (or `pg_dump`/restore, or a
templated database) after each tier load so a run can be repeated without
re-generating, and so a failed write-phase can be rolled back to a known size.

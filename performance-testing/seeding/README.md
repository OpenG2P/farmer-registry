# Bulk seed generator — quick start

Generates realistic, high-volume `Farmer` register data (households, farmers,
household members, lands, crops, livestock, farm inputs, membership details,
and `*_history` twins) directly into PostgreSQL via `COPY`, for the Volume-
Tiers defined in
[`../documentation/seeding-design.md`](../documentation/seeding-design.md).
See that document for the design rationale (generation DAG, why fields are
generator-computed instead of ORM-computed, search-anchor design, known
simplifications and the one known upstream issue) — this file is just
install/run.

## Prerequisites

1. **Configuration/meta-data must already be loaded** — register definitions,
   schemas, UI tabs/sections, attribute lookups. This is the platform's
   `db-seed` Job (`dbSeed.enabled=true`, **not** `dbSeed.loadSampleData=true`
   — that's a handful of demo rows, not a volume tier). The generator reads
   real `g2p_register_definitions` / `g2p_register_sections` /
   `g2p_register_ui_tab_sections` rows at runtime and will fail loudly if
   they're missing.
2. **Run close to the DB** — COPY over a slow network link will bottleneck
   before Postgres does.
3. `pip install -r requirements.txt` (`psycopg2-binary`, `Faker`).

## Running

```sh
cd performance-testing/seeding
export SEED_DB_DSN=postgresql://user:pass@host:5432/g2p_registry
python run.py --tier smoke      # 10K farmers, sanity check first
python run.py --tier primary    # 10M farmers, the headline benchmark figure
```

Tiers: `smoke` (10K), `primary` (10M), `stretch` (50M), `stress` (100M) — see
`config.DATA_VOLUME_TIERS`. For a `smoke`-tier correctness check, also set
`config.DEFER_INDEXES = False` first — see
[`seeding-design.md`](../documentation/seeding-design.md) "Load mechanics" for
why.

## Verify after seeding

```sql
-- row counts
SELECT relname, n_live_tup FROM pg_stat_user_tables
 WHERE relname LIKE 'g2p_register_%' ORDER BY n_live_tup DESC;

-- pg_trgm present
SELECT extname FROM pg_extension WHERE extname='pg_trgm';
\di+ *register*

-- a representative anchor search uses an index (not a seq scan)
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM g2p_register_farmers WHERE search_text ILIKE '%<an anchor>%' LIMIT 20;
```

Then warm the cache (representative reads) before measuring.

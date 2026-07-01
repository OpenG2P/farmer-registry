# Bulk seeding — specification for the generator

A bulk generator is **not committed yet** because it depends on the frozen
schema and the platform's id scheme. This file specifies exactly what it must do
so it can be written against the final `farmer-extension` models. See
[`../04-data-seeding.md`](../04-data-seeding.md) for volumes and ratios.

## What it must produce

1. **Volume tiers** (parameterised): 10K (smoke), 10M (primary), 50M, 100M
   `Farmer` register rows, plus proportional `Household`, `HouseholdMember`,
   `Land`, `Crop`, `Livestock`, `FarmInputs`, `MembershipDetails`,
   `PovertyScore` rows, and `*_history` rows for ~20–30% of records.

2. **Realistic, high-cardinality values** in indexed/search columns (names,
   ids, geo, attributes) so `search_in_a_register` and `pg_trgm` dedup exercise
   indexes — never all-identical rows.

3. **Valid id values** (`internal_record_id`, `functional_record_id`,
   `link_internal_record_id`) consistent with the platform id scheme so
   reads-by-id and parent/child links resolve.

4. A **seed manifest** (`seed_manifest.json`) for the load scripts:
   ```json
   {
     "record_ids":  ["...", "..."],   // sample of valid ids across the full key space
     "search_terms": ["...", "..."],  // realistic prefixes/substrings present in data
     "household_ids": ["..."],
     "data_volume": "10M",
     "generated_at": "..."
   }
   ```

## How (performance)

- Write with `COPY` or batched multi-row `INSERT` inside transactions
  (~50–100K rows/batch). Per-row API calls are orders of magnitude too slow for
  10M+.
- Disable/defer non-essential indexes during load, then build them and run
  `ANALYZE` / `VACUUM ANALYZE` afterwards. Confirm the `pg_trgm` GIN/GiST
  indexes exist and are used (`EXPLAIN`).
- Run the generator close to the DB (on/near the storage node) to avoid network
  being the bottleneck during seeding.

## After loading (gates before benchmarking)

```sql
SELECT relname, n_live_tup FROM pg_stat_user_tables
 WHERE relname LIKE 'g2p_register_%' ORDER BY n_live_tup DESC;
SELECT extname FROM pg_extension WHERE extname='pg_trgm';
EXPLAIN (ANALYZE, BUFFERS) /* a search_in_a_register-equivalent query */;
```
- Warm the cache (run representative reads) before measuring.
- Snapshot the volume / `pg_dump` so the tier can be restored for repeat runs.

## Reuse for NSR / other registries
Same generator, different mnemonics + columns. Parameterise the register/table
list and column generators per extension.

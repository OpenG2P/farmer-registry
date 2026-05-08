#!/bin/sh
set -e

# ──────────────────────────────────────────────────────────────
# OpenG2P Registry DB Seed Entrypoint
#
# Expects the following environment variables:
#   PGHOST      - PostgreSQL host
#   PGPORT      - PostgreSQL port           (default: 5432)
#   PGDATABASE  - Target database name
#   PGUSER      - Database user
#   PGPASSWORD  - Database password
#   LOAD_SAMPLE_DATA - "true" to load sample data (default: "false")
# ──────────────────────────────────────────────────────────────

PGPORT="${PGPORT:-5432}"
LOAD_SAMPLE_DATA="${LOAD_SAMPLE_DATA:-false}"

SEED_DIR="/seed"
CONFIGURATIONS_DIR="${SEED_DIR}/meta_data"
SAMPLE_DATA_DIR="${SEED_DIR}/sample_data"

run_sql_files() {
  dir="$1"
  label="$2"

  if [ ! -d "$dir" ]; then
    echo "[db-seed] No ${label} directory found at ${dir}, skipping."
    return
  fi

  # Collect all .sql files, sorted by full path for deterministic order.
  sql_files=$(find "$dir" -name '*.sql' -type f | sort)

  if [ -z "$sql_files" ]; then
    echo "[db-seed] No SQL files found in ${dir}, skipping."
    return
  fi

  echo "[db-seed] Running ${label} scripts from ${dir} ..."
  for f in $sql_files; do
    echo "[db-seed]   -> $(basename "$f")"
    psql -v ON_ERROR_STOP=0 -f "$f"
  done
  echo "[db-seed] ${label} scripts completed."
}

echo "============================================="
echo " OpenG2P Registry DB Seed"
echo " Extension : ${EXTENSION_FOLDER:-unknown}"
echo " Database  : ${PGDATABASE}@${PGHOST}:${PGPORT}"
echo " Sample data : ${LOAD_SAMPLE_DATA}"
echo "============================================="

# 1. Always run configuration scripts (register definitions, schemas, tabs, sections, attributes, registry-config)
run_sql_files "$CONFIGURATIONS_DIR" "meta_data"

# 2. Optionally run sample data scripts
if [ "$LOAD_SAMPLE_DATA" = "true" ]; then
  run_sql_files "$SAMPLE_DATA_DIR" "sample data"
else
  echo "[db-seed] Skipping sample data (LOAD_SAMPLE_DATA=${LOAD_SAMPLE_DATA})."
fi

echo "[db-seed] Done."

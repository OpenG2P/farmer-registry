#!/bin/sh
set -e

# ──────────────────────────────────────────────────────────────
# OpenG2P Registry DB Seed Entrypoint
#
# Registry database:
#   PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
#   LOAD_SAMPLE_DATA — "true" to load sample data (default: "false")
#   LOAD_TEMPLATES   — "true" to upload templates to MinIO (default: "false")
#   MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY — MinIO connection
#   MINIO_SECURE     — "true" for HTTPS (default: "false")
#   TEMPLATE_BUCKET_NAME — MinIO bucket (default: "template")
#   TEMPLATES_DIR    — path to flat .j2 files (default: /seed/templates)
#
# AWE database (implementation extension data; optional):
#   AWE_DB_SEED_ENABLED — "true" to seed the AWE Postgres database
#   AWE_PGHOST, AWE_PGPORT, AWE_PGDATABASE, AWE_PGUSER, AWE_PGPASSWORD
#   AWE_CALLBACK_HMAC_SECRET — callback_secret row + registry staff API
# ──────────────────────────────────────────────────────────────

PGPORT="${PGPORT:-5432}"
LOAD_SAMPLE_DATA="${LOAD_SAMPLE_DATA:-false}"
LOAD_TEMPLATES="${LOAD_TEMPLATES:-false}"
AWE_DB_SEED_ENABLED="${AWE_DB_SEED_ENABLED:-false}"

SEED_DIR="/seed"
META_DATA_DIR="${SEED_DIR}/meta_data"
SAMPLE_DATA_DIR="${SEED_DIR}/sample_data"
AWE_META_DATA_DIR="${SEED_DIR}/awe_meta_data"

run_sql_files() {
  dir="$1"
  label="$2"
  db_host="${3:-$PGHOST}"
  db_port="${4:-$PGPORT}"
  db_name="${5:-$PGDATABASE}"
  db_user="${6:-$PGUSER}"
  db_password="${7:-$PGPASSWORD}"

  if [ ! -d "$dir" ]; then
    echo "[db-seed] No ${label} directory found at ${dir}, skipping."
    return
  fi

  sql_files=$(find "$dir" -name '*.sql' -type f | sort)
  if [ -z "$sql_files" ]; then
    echo "[db-seed] No SQL files found in ${dir}, skipping."
    return
  fi

  echo "[db-seed] Running ${label} on ${db_name}@${db_host}:${db_port} ..."
  PGHOST="$db_host" PGPORT="$db_port" PGDATABASE="$db_name" PGUSER="$db_user" PGPASSWORD="$db_password"
  export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD
  for f in $sql_files; do
    echo "[db-seed]   -> $(basename "$f")"
    psql -v ON_ERROR_STOP=0 -f "$f"
  done
  echo "[db-seed] ${label} completed."
}

run_callback_secret() {
  tpl="${AWE_META_DATA_DIR}/40_callback_secret.sql.tpl"
  if [ ! -f "$tpl" ]; then
    return
  fi
  if [ -z "$AWE_CALLBACK_HMAC_SECRET" ]; then
    echo "[db-seed] AWE_CALLBACK_HMAC_SECRET unset — skipping callback_secret."
    return
  fi
  echo "[db-seed]   -> callback_secret (AWE DB, from template)"
  export AWE_CALLBACK_HMAC_SECRET
  PGHOST="${AWE_PGHOST}" PGPORT="${AWE_PGPORT:-5432}" PGDATABASE="${AWE_PGDATABASE}" \
    PGUSER="${AWE_PGUSER}" PGPASSWORD="${AWE_PGPASSWORD}" \
    envsubst '${AWE_CALLBACK_HMAC_SECRET}' < "$tpl" | psql -v ON_ERROR_STOP=0 -f -
}

echo "============================================="
echo " OpenG2P Registry DB Seed"
echo " Extension : ${EXTENSION_FOLDER:-unknown}"
echo " Registry DB : ${PGDATABASE}@${PGHOST}:${PGPORT}"
echo " AWE DB seed : ${AWE_DB_SEED_ENABLED}"
echo " Sample data : ${LOAD_SAMPLE_DATA}"
echo " Templates   : ${LOAD_TEMPLATES}"
echo "============================================="

# 1. Registry meta_data (includes awe-integration mappings under meta_data/)
run_sql_files "$META_DATA_DIR" "meta-data"

# 2. Optionally run sample data scripts
if [ "$LOAD_SAMPLE_DATA" = "true" ]; then
  run_sql_files "$SAMPLE_DATA_DIR" "sample data"
else
  echo "[db-seed] Skipping sample data (LOAD_SAMPLE_DATA=${LOAD_SAMPLE_DATA})."
fi

# 3. Optionally upload Jinja templates to MinIO (object key = filename)
if [ "$LOAD_TEMPLATES" = "true" ]; then
  echo "[db-seed] Uploading templates to MinIO ..."
  python3 /seed/upload_templates.py
else
  echo "[db-seed] Skipping template upload (LOAD_TEMPLATES=${LOAD_TEMPLATES})."
fi

# 4. Optionally seed AWE database (policies, stages, callback_secret)
if [ "$AWE_DB_SEED_ENABLED" = "true" ]; then
  if [ -z "$AWE_PGDATABASE" ] || [ -z "$AWE_PGHOST" ]; then
    echo "[db-seed] AWE_DB_SEED_ENABLED but AWE DB env incomplete — skipping AWE seed."
  else
    echo "---------------------------------------------"
    echo " AWE DB : ${AWE_PGDATABASE}@${AWE_PGHOST}:${AWE_PGPORT:-5432}"
    echo "---------------------------------------------"
    run_sql_files "$AWE_META_DATA_DIR" "AWE meta_data" \
      "$AWE_PGHOST" "${AWE_PGPORT:-5432}" "$AWE_PGDATABASE" "$AWE_PGUSER" "$AWE_PGPASSWORD"
    run_callback_secret
  fi
fi

echo "[db-seed] Done."

#!/usr/bin/env bash
# Insert one isolated backlog for a Celery case.
# Rows are copied from a real record already in the database.
# Sibling status columns are not PENDING, so the other beat producers
# do not claim this cohort.
#
#   ./populate.sh <case> <count>
#
# Examples:
#   ./populate.sh dedup_register 20000
#   ./populate.sh dedup_change_request 10000
#
# Scale beat and workers to 0 first. Then pin, then start the run.
# A second run of the same case replaces that case's previous perf rows.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${CELERY_NAMESPACE:-perftest}"
CASE="${1:?case name}"
COUNT="${2:?count}"

[[ "$CASE" =~ ^[a-z0-9_]+$ ]] || { echo "Bad case name: $CASE" >&2; exit 2; }
[[ "$COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "Count must be a positive integer" >&2; exit 2; }
grep -q "('${CASE}'," "$ROOT/sql/case_defs.sql" || { echo "Unknown case: $CASE" >&2; exit 2; }

beat="$(kubectl -n "$NS" get deploy farmer-registry-celery-beat-producer -o jsonpath='{.spec.replicas}')"
workers="$(kubectl -n "$NS" get deploy farmer-registry-celery-worker -o jsonpath='{.spec.replicas}')"
if [[ "$beat" != "0" || "$workers" != "0" ]]; then
  echo "Beat replicas=${beat}, worker replicas=${workers}." >&2
  echo "Scale both to 0 before populating. Beat would claim rows during the insert." >&2
  exit 1
fi

SQL="$ROOT/sql/populate/${CASE}.sql"
[[ -f "$SQL" ]] || { echo "No populate script for ${CASE}" >&2; exit 2; }

{
  printf '\\set count %s\n' "$COUNT"
  cat "$SQL"
  case "$CASE" in
    dedup_intake_vs_register|dedup_intake_vs_intake|intake_register_ingest)
      cat "$ROOT/sql/populate/intake_clone.sql"
      ;;
  esac
} | "$ROOT/psql.sh" celery-populate

#!/usr/bin/env bash
# Keep SIZE pending rows for one worker case. Park every other beat producer.
# Beat must be at 0. Workers may already be up; they do not claim rows.
#
#   ./pin-case.sh dedup_register 10000

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${CELERY_NAMESPACE:-perftest}"
CASE="${1:?case name}"
SIZE="${2:?size}"

[[ "$CASE" =~ ^[a-z0-9_]+$ ]] || { echo "Bad case name: $CASE" >&2; exit 2; }
[[ "$SIZE" =~ ^[0-9]+$ ]] || { echo "SIZE must be an integer" >&2; exit 2; }
grep -q "('${CASE}'," "$ROOT/sql/case_defs.sql" || { echo "Unknown case: $CASE" >&2; exit 2; }

beat="$(kubectl -n "$NS" get deploy farmer-registry-celery-beat-producer -o jsonpath='{.spec.replicas}')"
workers="$(kubectl -n "$NS" get deploy farmer-registry-celery-worker -o jsonpath='{.spec.replicas}')"
if [[ "$beat" != "0" ]]; then
  echo "Beat replicas=${beat}, worker replicas=${workers}." >&2
  echo "Scale beat to 0 before pinning. Beat would claim rows during the update." >&2
  exit 1
fi

sed -e "s/__KEEP_CASE__/${CASE}/" -e "s/__KEEP_SIZE__/${SIZE}/" "$ROOT/sql/pin_body.sql" \
  | cat "$ROOT/sql/case_defs.sql" - "$ROOT/sql/count_body.sql" \
  | "$ROOT/psql.sh" celery-pin

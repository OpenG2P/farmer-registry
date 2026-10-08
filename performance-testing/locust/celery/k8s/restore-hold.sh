#!/usr/bin/env bash
# Put parked rows back to the status they had before pin-case.sh.
# Beat and workers must be at 0.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${CELERY_NAMESPACE:-perftest}"

beat="$(kubectl -n "$NS" get deploy farmer-registry-celery-beat-producer -o jsonpath='{.spec.replicas}')"
workers="$(kubectl -n "$NS" get deploy farmer-registry-celery-worker -o jsonpath='{.spec.replicas}')"
if [[ "$beat" != "0" || "$workers" != "0" ]]; then
  echo "Beat replicas=${beat}, worker replicas=${workers}. Scale both to 0 before restore." >&2
  exit 1
fi

cat "$ROOT/sql/restore_body.sql" | "$ROOT/psql.sh" celery-restore

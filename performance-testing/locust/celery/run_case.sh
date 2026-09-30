#!/usr/bin/env bash
# Laptop helper. The supported runner is the in-cluster Job:
# k8s/collector-job.yaml. Use that when beat, workers, and the collector
# all run in Kubernetes.
#
# Run one isolated celery backlog observation.
#
# Beat is scaled to exactly 1. Workers are scaled to --workers (1, 2, or 3).
# The clock starts once both deployments are Ready. Processing is left running
# after the last mark; this script only records snapshots.
#
# Required environment:
#   DATABASE_URL   or   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
# Optional:
#   REDIS_URL                 redis://host:6379/0  (queue depth column)
#   CELERY_NAMESPACE          default: default
#   CELERY_BEAT_DEPLOYMENT    default: discovered by component label
#   CELERY_WORKER_DEPLOYMENT  default: discovered by component label
#
# Example:
#   ./run_case.sh --case dedup_register --size 10000 --workers 2

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${CELERY_NAMESPACE:-default}"
CASE=""
SIZE=""
WORKERS=""
MARKS="5,10,15,20,25,30"
STOP_FIRST=0
ALLOW_MIXED=0
ALLOW_SIZE_MISMATCH=0
STRICT_BEAT=0

usage() {
  sed -n '2,20p' "$0"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --case) CASE="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --marks) MARKS="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --stop-first) STOP_FIRST=1; shift ;;
    --allow-mixed) ALLOW_MIXED=1; shift ;;
    --allow-size-mismatch) ALLOW_SIZE_MISMATCH=1; shift ;;
    --strict-beat) STRICT_BEAT=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ -n "$CASE" && -n "$SIZE" && -n "$WORKERS" ]] || usage
[[ "$WORKERS" =~ ^[123]$ ]] || { echo "--workers must be 1, 2, or 3" >&2; exit 2; }

discover() {
  local component="$1"
  kubectl -n "$NAMESPACE" get deploy -l "app.kubernetes.io/component=${component}" -o jsonpath='{.items[0].metadata.name}'
}

BEAT_DEPLOY="${CELERY_BEAT_DEPLOYMENT:-$(discover celery-beat-producer)}"
WORKER_DEPLOY="${CELERY_WORKER_DEPLOYMENT:-$(discover celery-worker)}"
[[ -n "$BEAT_DEPLOY" && -n "$WORKER_DEPLOY" ]] || {
  echo "Could not find celery beat/worker deployments in namespace ${NAMESPACE}." >&2
  exit 1
}

env_value() {
  local deploy="$1"
  local name="$2"
  kubectl -n "$NAMESPACE" get deploy "$deploy" \
    -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name==\"${name}\")].value}"
}

if [[ "$STOP_FIRST" -eq 1 ]]; then
  echo "Scaling ${BEAT_DEPLOY} and ${WORKER_DEPLOY} to 0 before the backlog check"
  kubectl -n "$NAMESPACE" scale "deploy/${BEAT_DEPLOY}" --replicas=0
  kubectl -n "$NAMESPACE" scale "deploy/${WORKER_DEPLOY}" --replicas=0
  kubectl -n "$NAMESPACE" rollout status "deploy/${BEAT_DEPLOY}" --timeout=180s
  kubectl -n "$NAMESPACE" rollout status "deploy/${WORKER_DEPLOY}" --timeout=180s
fi

beat_now="$(kubectl -n "$NAMESPACE" get deploy "$BEAT_DEPLOY" -o jsonpath='{.spec.replicas}')"
worker_now="$(kubectl -n "$NAMESPACE" get deploy "$WORKER_DEPLOY" -o jsonpath='{.spec.replicas}')"
if [[ "$beat_now" != "0" || "$worker_now" != "0" ]]; then
  echo "Beat replicas=${beat_now}, worker replicas=${worker_now}." >&2
  echo "Stop them first so the cohort is not already draining, or pass --stop-first." >&2
  exit 1
fi

TASKS_PER_TICK="$(env_value "$BEAT_DEPLOY" REGISTRY_CELERY_BEAT_NO_OF_TASKS_TO_PROCESS)"
TASKS_PER_TICK="${TASKS_PER_TICK:-4}"

read -r FREQ_ENV FREQ_DEFAULT < <(
  cd "$ROOT"
  python3 - "$CASE" <<'PY'
import sys
from cases import get_case
case = get_case(sys.argv[1])
print(case.frequency_env, case.frequency_s)
PY
)
FREQUENCY_S="$(env_value "$BEAT_DEPLOY" "$FREQ_ENV")"
FREQUENCY_S="${FREQUENCY_S:-$FREQ_DEFAULT}"

CELERY_OPTS="$(env_value "$WORKER_DEPLOY" CELERY_OPTS)"
echo "beat_deployment=${BEAT_DEPLOY} worker_deployment=${WORKER_DEPLOY}"
echo "CELERY_OPTS=${CELERY_OPTS:-unset}"
echo "If CELERY_OPTS has no -c/--concurrency, each pod's process count follows the CPUs visible in the container, not the replica count."

PREFLIGHT=(python3 "$ROOT/preflight.py" --case "$CASE" --size "$SIZE" --frequency-s "$FREQUENCY_S" --tasks-per-tick "$TASKS_PER_TICK")
[[ "$ALLOW_MIXED" -eq 1 ]] && PREFLIGHT+=(--allow-mixed)
[[ "$ALLOW_SIZE_MISMATCH" -eq 1 ]] && PREFLIGHT+=(--allow-size-mismatch)
[[ "$STRICT_BEAT" -eq 1 ]] && PREFLIGHT+=(--strict-beat)
( cd "$ROOT" && "${PREFLIGHT[@]}" )

echo "Starting beat=1 workers=${WORKERS}"
kubectl -n "$NAMESPACE" scale "deploy/${WORKER_DEPLOY}" --replicas="$WORKERS"
kubectl -n "$NAMESPACE" scale "deploy/${BEAT_DEPLOY}" --replicas=1
kubectl -n "$NAMESPACE" rollout status "deploy/${WORKER_DEPLOY}" --timeout=300s
kubectl -n "$NAMESPACE" rollout status "deploy/${BEAT_DEPLOY}" --timeout=300s

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/results/${CASE}/workers-${WORKERS}/size-${SIZE}/${STAMP}.csv"
echo "Observing ${CASE} at marks ${MARKS}. Processing keeps running after the last mark."
python3 "$ROOT/observe.py" \
  --case "$CASE" \
  --size "$SIZE" \
  --workers "$WORKERS" \
  --marks "$MARKS" \
  --out "$OUT"

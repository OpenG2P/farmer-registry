#!/bin/sh
# Entrypoint for the in-cluster collector Job.
# Does not scale anything. Beat and worker replica changes are done with kubectl.

set -eu

CASE="${CASE:?set CASE}"
SIZE="${SIZE:?set SIZE}"
WORKERS="${WORKERS:?set WORKERS}"
MARKS="${MARKS:-5,10,15,20,25,30}"
FREQUENCY_S="${FREQUENCY_S:-}"
TASKS_PER_TICK="${TASKS_PER_TICK:-4}"
OUT="${OUT:-/results/${CASE}/workers-${WORKERS}/size-${SIZE}.csv}"

PREFLIGHT="python3 /app/preflight.py --case ${CASE} --size ${SIZE} --tasks-per-tick ${TASKS_PER_TICK}"
if [ -n "$FREQUENCY_S" ]; then
  PREFLIGHT="${PREFLIGHT} --frequency-s ${FREQUENCY_S}"
fi
if [ "${ALLOW_MIXED:-0}" = "1" ]; then
  PREFLIGHT="${PREFLIGHT} --allow-mixed"
fi
if [ "${ALLOW_SIZE_MISMATCH:-0}" = "1" ]; then
  PREFLIGHT="${PREFLIGHT} --allow-size-mismatch"
fi
if [ "${STRICT_BEAT:-0}" = "1" ]; then
  PREFLIGHT="${PREFLIGHT} --strict-beat"
fi

# shellcheck disable=SC2086
$PREFLIGHT

python3 /app/observe.py \
  --case "$CASE" \
  --size "$SIZE" \
  --workers "$WORKERS" \
  --marks "$MARKS" \
  --arm \
  --out "$OUT"

echo "Pod is staying up so the CSV can be copied. Delete the Job when you have it."
sleep "${KEEP_SECONDS:-3600}"

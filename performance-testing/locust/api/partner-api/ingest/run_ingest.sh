#!/usr/bin/env bash
# Open the Locust web UI for partner ingest.
#   ./run_ingest.sh 1
#   ./run_ingest.sh 2
#   ./run_ingest.sh 3
# Scale the partner-api deployment yourself first. The argument only
# sets POD_SCALE (CPU freeze quorum) and the results folder.
# Then open http://127.0.0.1:8089 and click Start swarming.
# HEADLESS=1 runs until the shape finishes the soak, without the UI.
# CSVs land in locust/api/results/partner-api/ingest/pod-<N>/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${PARTNER_API_BASE:-https://partner-farmer-registry.perftest.openg2p.org}"
POD_SCALE="${1:-${POD_SCALE:-1}}"
if ! [[ "${POD_SCALE}" =~ ^[123]$ ]]; then
  echo "pass 1, 2, or 3 (got ${POD_SCALE})" >&2
  exit 1
fi
OUT="${HERE}/../../results/partner-api/ingest/pod-${POD_SCALE}"
mkdir -p "${OUT}"

export PARTNER_API_BASE="${HOST}"
export PYTHONPATH="${HERE}/../..${PYTHONPATH:+:${PYTHONPATH}}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/perftest.yaml}"
export CPU_BREACH_CORES="${CPU_BREACH_CORES:-1.85}"
export CPU_BREACH_POLLS="${CPU_BREACH_POLLS:-2}"
export SLO_BREACH_STEPS="${SLO_BREACH_STEPS:-2}"
export MAX_USERS="${MAX_USERS:-100}"
export SUSTAIN_MINUTES=5
export POD_SCALE
export STAFF_API_KUBE_NAMESPACE=perftest
export STAFF_API_POD_GREP=farmer-registry-partner-api
export ENDPOINT_SLOS="
ingest 1000000 1000
"

if [[ -n "${LOCUST_BIN:-}" ]]; then
  # shellcheck disable=SC2206
  LOCUST=(${LOCUST_BIN})
elif [[ -x "${HERE}/../../../../../../venv/.perf-venv/bin/python" ]]; then
  LOCUST=("${HERE}/../../../../../../venv/.perf-venv/bin/python" -m locust)
elif command -v locust >/dev/null 2>&1; then
  LOCUST=(locust)
else
  echo "locust is not on PATH. Set LOCUST_BIN." >&2
  exit 1
fi

ARGS=(
  -f "${HERE}/locustfile.py"
  --host "${HOST}"
  -u 4
  -r 4
  --tags ingest
  --csv "${OUT}/ingest"
  --web-port "${WEB_PORT:-8089}"
)
if [[ "${HEADLESS:-}" == "1" ]]; then
  ARGS+=(--headless)
else
  echo "Locust web UI: http://127.0.0.1:${WEB_PORT:-8089}"
  echo "Click Start swarming. The shape starts at 4 users and adds 4 every 30s until CPU is 1.85 or p99 is over 1000ms, then holds for 5 minutes and stops."
fi
echo "POD_SCALE=${POD_SCALE}"
echo "Results: ${OUT}"

exec "${LOCUST[@]}" "${ARGS[@]}"

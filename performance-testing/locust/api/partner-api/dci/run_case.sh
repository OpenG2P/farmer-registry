#!/usr/bin/env bash
# Open the Locust web UI for one indexed DCI case.
#   ./run_case.sh sync btree_fid
#   ./run_case.sh async composite
# Then open http://127.0.0.1:8089 and click Start swarming.
# HEADLESS=1 keeps the timed run used by run_all.sh.
set -euo pipefail

MODE="${1:?sync or async}"
CASE="${2:?case tag}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${PARTNER_API_BASE:-https://partner-farmer-registry.perftest.openg2p.org}"
OUT="${HERE}/results/${MODE}"
mkdir -p "${OUT}"

export DCI_MODE="${MODE}"
export PARTNER_API_BASE="${HOST}"
export PYTHONPATH="${HERE}/../..${PYTHONPATH:+:${PYTHONPATH}}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/perftest.yaml}"
# Same knobs as locust/api/env.sh. One partner pod, so one core reading
# at 1.85 freezes the ramp. p95 is unset in practice (very high) so the
# gate is p99 5000ms.
export CPU_BREACH_CORES="${CPU_BREACH_CORES:-1.85}"
export CPU_BREACH_POLLS="${CPU_BREACH_POLLS:-2}"
export SLO_BREACH_STEPS="${SLO_BREACH_STEPS:-2}"
export MAX_USERS="${MAX_USERS:-100}"
export SUSTAIN_MINUTES="${SUSTAIN_MINUTES:-5}"
export POD_SCALE=1
export STAFF_API_KUBE_NAMESPACE=perftest
export STAFF_API_POD_GREP=farmer-registry-partner-api
export ENDPOINT_SLOS="
sync:btree_fid 1000000 5000
sync:btree_uin 1000000 5000
sync:btree_birth 1000000 5000
sync:gin_first 1000000 5000
sync:gin_last 1000000 5000
sync:gin_text 1000000 5000
sync:composite 1000000 5000
sync:id_fid 1000000 5000
sync:id_uin 1000000 5000
async:btree_fid 1000000 5000
async:btree_uin 1000000 5000
async:btree_birth 1000000 5000
async:gin_first 1000000 5000
async:gin_last 1000000 5000
async:gin_text 1000000 5000
async:composite 1000000 5000
async:id_fid 1000000 5000
async:id_uin 1000000 5000
"

# The Music venv's locust script points at a moved interpreter. python -m locust works.
if [[ -n "${LOCUST_BIN:-}" ]]; then
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
  --tags "${CASE}"
  --csv "${OUT}/${CASE}"
  --web-port "${WEB_PORT:-8089}"
)
if [[ "${HEADLESS:-}" == "1" ]]; then
  ARGS+=(--headless)
else
  echo "Locust web UI: http://127.0.0.1:${WEB_PORT:-8089}"
  echo "Click Start swarming. The shape starts at 4 users and adds 4 every 30s until CPU is 1.85 or p99 is over 5000ms. Tag ${CASE}."
fi

exec "${LOCUST[@]}" "${ARGS[@]}"

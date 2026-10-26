#!/usr/bin/env bash
# Open the Locust web UI for one indexed DCI case.
#   ./run_case.sh sync btree_fid 1
#   ./run_case.sh async composite 3
# Scale the partner-api deployment yourself first. The last argument
# sets POD_SCALE and the results folder.
# Then open http://127.0.0.1:8089 and click Start swarming.
# HEADLESS=1 keeps the timed run used by run_all.sh.
# CSVs land in locust/api/results/partner-api/<sync|async>/pod-<N>/.
set -euo pipefail

MODE="${1:?sync or async}"
CASE="${2:?case tag}"
POD_SCALE="${3:?pass 1, 2, or 3}"
if [[ "${MODE}" != "sync" && "${MODE}" != "async" ]]; then
  echo "mode must be sync or async (got ${MODE})" >&2
  exit 1
fi
if ! [[ "${POD_SCALE}" =~ ^[123]$ ]]; then
  echo "pass 1, 2, or 3 (got ${POD_SCALE})" >&2
  exit 1
fi
PAGE_SIZE="${4:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${PARTNER_API_BASE:-https://partner-farmer-registry.perftest.openg2p.org}"
OUT="${HERE}/../../results/partner-api/${MODE}/pod-${POD_SCALE}"
mkdir -p "${OUT}"

export DCI_MODE="${MODE}"
export PARTNER_API_BASE="${HOST}"
export PYTHONPATH="${HERE}/../..${PYTHONPATH:+:${PYTHONPATH}}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/perftest.yaml}"
# Same knobs as locust/api/env.sh. POD_SCALE 1 or 2 freezes when one pod
# stays at 1.85 cores; 3 freezes when two pods do. p95 is unset in
# practice (very high) so the gate is p99 5000ms.
export CPU_BREACH_CORES="${CPU_BREACH_CORES:-1.85}"
export CPU_BREACH_POLLS="${CPU_BREACH_POLLS:-2}"
export SLO_BREACH_STEPS="${SLO_BREACH_STEPS:-2}"
export MAX_USERS="${MAX_USERS:-100}"
CSV_NAME="${CASE}"
LOCUST_USERS=4
RANGE_CASE=0
if [[ "${CASE}" == "expression" || "${CASE}" == "predicate" || "${CASE}" == "graphql" ]]; then
  if [[ "${PAGE_SIZE}" != "100" && "${PAGE_SIZE}" != "500" ]]; then
    echo "range case needs page size 100 or 500: ./run_case.sh ${MODE} ${CASE} ${POD_SCALE} 100" >&2
    exit 1
  fi
  # 8 users for 1 pod, 16 for 2, 24 for 3.
  RANGE_USERS=$((POD_SCALE * 8))
  export DCI_PAGE_SIZE="${PAGE_SIZE}"
  export DCI_FIXED_USERS="${RANGE_USERS}"
  export MAX_USERS="${RANGE_USERS}"
  CSV_NAME="${CASE}_p${PAGE_SIZE}"
  export DCI_RECORDS_LOG="${OUT}/${CSV_NAME}_records.csv"
  LOCUST_USERS="${RANGE_USERS}"
  RANGE_CASE=1
fi
export SUSTAIN_MINUTES=5
export POD_SCALE
export STAFF_API_KUBE_NAMESPACE=perftest
export STAFF_API_POD_GREP=farmer-registry-partner-api
export ENDPOINT_SLOS="
sync:btree_fid 1000000 5000
sync:btree_uin 1000000 5000
sync:btree_birth 1000000 5000
sync:expression 1000000 5000
sync:predicate 1000000 5000
sync:graphql 1000000 5000
sync:idtype_value 1000000 5000
sync:gin_first 1000000 5000
sync:gin_last 1000000 5000
sync:gin_text 1000000 5000
sync:composite 1000000 5000
sync:id_fid 1000000 5000
sync:id_uin 1000000 5000
async:btree_fid 1000000 5000
async:btree_uin 1000000 5000
async:btree_birth 1000000 5000
async:expression 1000000 5000
async:predicate 1000000 5000
async:graphql 1000000 5000
async:idtype_value 1000000 5000
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
  -u "${LOCUST_USERS}"
  -r "${LOCUST_USERS}"
  --tags "${CASE}"
  --csv "${OUT}/${CSV_NAME}"
  --web-port "${WEB_PORT:-8089}"
)
if [[ "${HEADLESS:-}" == "1" ]]; then
  ARGS+=(--headless)
else
  echo "Locust web UI: http://127.0.0.1:${WEB_PORT:-8089}"
  if [[ "${RANGE_CASE}" == "1" ]]; then
    echo "Click Start swarming. Leave Run time empty. This run stays at ${LOCUST_USERS} users, page size ${PAGE_SIZE}, and stops at 10 minutes. Each user sends one request, waits for the response, then sends the next. Tag ${CASE}."
  else
    echo "Click Start swarming. The shape starts at 4 users and adds 4 every 30s until CPU is 1.85 or p99 is over 5000ms, then holds for 5 minutes and stops. Tag ${CASE}."
  fi
fi
echo "POD_SCALE=${POD_SCALE}"
echo "Results: ${OUT}/${CSV_NAME}"
if [[ "${CASE}" == "expression" || "${CASE}" == "predicate" || "${CASE}" == "graphql" ]]; then
  echo "Birth ranges: ${HERE}/../../../../../../perf-seed/partner_birth_weeks.csv"
  echo "Page size: ${PAGE_SIZE}. Users: ${LOCUST_USERS}. Each user keeps one week until every page of that week is done."
  echo "Records served: ${DCI_RECORDS_LOG}"
fi

exec "${LOCUST[@]}" "${ARGS[@]}"

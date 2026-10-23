#!/usr/bin/env bash
# Write 100000 functional ids for btree_fid. Does not touch the name/birth pool.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/perftest.yaml}"
NS="${PERF_NAMESPACE:-perftest}"
DEPLOY="${PARTNER_DEPLOY:-farmer-registry-partner-api}"
OUT="${FID_POOL:-${HERE}/../../../../../../perf-seed/partner_btree_fids.txt}"
LIMIT="${FID_POOL_SIZE:-100000}"
TMP="${OUT}.tmp"

POD="$(kubectl -n "${NS}" get pod -o name | awk -F/ '/farmer-registry-partner-api-/ {print $2; exit}')"
if [[ -z "${POD}" ]]; then
  echo "no running ${DEPLOY} pod" >&2
  exit 1
fi

kubectl -n "${NS}" cp "${HERE}/prepare_fids.py" "${POD}:/tmp/prepare_fids.py" -c partner-api
kubectl -n "${NS}" exec "${POD}" -c partner-api --request-timeout=180s -- \
  env FID_POOL_SIZE="${LIMIT}" python3 /tmp/prepare_fids.py > "${TMP}"
mv "${TMP}" "${OUT}"
echo "wrote ${OUT}"
wc -l "${OUT}"

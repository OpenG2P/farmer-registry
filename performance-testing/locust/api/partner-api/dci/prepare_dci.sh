#!/usr/bin/env bash
# Configure async WebSub for PARTNER_STAFF_PORTAL and write search_pool.csv.
# Does not print database passwords.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/perftest.yaml}"
NS="${PERF_NAMESPACE:-perftest}"
DEPLOY="${PARTNER_DEPLOY:-farmer-registry-partner-api}"
POOL="${PERF_SEED_POOL:-${HERE}/../../../../../../perf-seed/partner_search_pool.csv}"

kubectl -n "${NS}" set env "deploy/${DEPLOY}" \
  REGISTRY_PARTNER_API_WEBSUB_BASE_URL=http://websub
# rollout status can stay open after printing success when another watcher is attached.
for _ in $(seq 1 60); do
  ready="$(kubectl -n "${NS}" get deploy "${DEPLOY}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  if [[ "${ready}" == "1" ]]; then
    break
  fi
  sleep 3
done

POD="$(kubectl -n "${NS}" get pod -l app.kubernetes.io/name="${DEPLOY}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "${POD}" ]]; then
  POD="$(kubectl -n "${NS}" get pod -o name | awk -F/ '/farmer-registry-partner-api-/ {print $2; exit}')"
fi

kubectl -n "${NS}" cp "${HERE}/prepare_remote.py" "${POD}:/tmp/prepare_remote.py" -c partner-api
kubectl -n "${NS}" exec "${POD}" -c partner-api --request-timeout=120s -- python3 /tmp/prepare_remote.py > "${POOL}"
echo "wrote ${POOL}"
wc -l "${POOL}"

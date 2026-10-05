#!/usr/bin/env bash
# Run SQL on the perftest farmer_registry database from inside the cluster.
# Usage: psql.sh <pod-name> < sql-file

set -euo pipefail

NS="${CELERY_NAMESPACE:-perftest}"
POD="${1:?pod name}"

kubectl -n "$NS" delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  kubectl -n "$NS" get pod "$POD" >/dev/null 2>&1 || break
  sleep 1
done
kubectl -n "$NS" apply -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${POD}
  namespace: ${NS}
spec:
  restartPolicy: Never
  containers:
    - name: psql
      image: postgres:16-alpine
      env:
        - name: PGHOST
          value: "172.29.2.191"
        - name: PGPORT
          value: "5432"
        - name: PGDATABASE
          value: farmer_registry
        - name: PGUSER
          value: farmer_registry_user
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: farmer-registry
              key: farmer-registry-db-user
      command: ["sleep", "600"]
EOF

ready=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  phase="$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  deleting="$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.metadata.deletionTimestamp}' 2>/dev/null || true)"
  if [[ "$phase" == "Running" && -z "$deleting" ]]; then
    ready=1
    break
  fi
  sleep 2
done
[[ -n "$ready" ]] || { echo "Pod ${POD} did not start" >&2; exit 1; }
set +e
kubectl -n "$NS" exec -i "$POD" -- psql -v ON_ERROR_STOP=1 -f - < /dev/stdin
status=$?
set -e
kubectl -n "$NS" delete pod "$POD" --wait=false >/dev/null
exit "$status"

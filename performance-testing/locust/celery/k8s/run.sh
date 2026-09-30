#!/usr/bin/env bash
# One isolated run: workers, one task, backlog size.
# Parks every other beat producer, scales beat to 1, collects 0..30 min.
#
#   ./run.sh 1 dedup_register 10000
#   ./run.sh 2 intake_register_ingest 10000
#   ./run.sh 3 functional_id_allocation 5000

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${CELERY_NAMESPACE:-perftest}"
WORKERS="${1:?workers 1, 2, or 3}"
CASE="${2:?task name}"
SIZE="${3:?backlog size}"
MARKS="${MARKS:-$(seq 0 30)}"

[[ "$WORKERS" =~ ^[123]$ ]] || { echo "workers must be 1, 2, or 3" >&2; exit 2; }
[[ "$SIZE" =~ ^[0-9]+$ ]] || { echo "size must be an integer" >&2; exit 2; }

case "$CASE" in
  ingest_data_classification) TABLE=incoming_raw_data; PK=ingest_id; COL=classification_status; EXTRA="TRUE" ;;
  ingest_data_transformation) TABLE=incoming_classified_data; PK=ingest_id; COL=transformation_status; EXTRA="TRUE" ;;
  ingest_data) TABLE=incoming_classified_data; PK=ingest_id; COL=ingestion_status; EXTRA="pipeline_action IS DISTINCT FROM 'UPDATE'" ;;
  change_request_ingest) TABLE=incoming_classified_data; PK=ingest_id; COL=ingestion_status; EXTRA="pipeline_action = 'UPDATE'" ;;
  outgest_data_transformation) TABLE=outgoing_raw_data; PK=outgest_id; COL=transformation_status; EXTRA="TRUE" ;;
  outgest_data_publish) TABLE=outgoing_raw_data; PK=outgest_id; COL=publish_status; EXTRA="TRUE" ;;
  outgest_topic_register) TABLE=outgoing_topics; PK=topic_id; COL=websub_register_status; EXTRA="TRUE" ;;
  dedup_register) TABLE=g2p_register_change_requests; PK=change_request_id; COL=deduplication_register_status; EXTRA="TRUE" ;;
  dedup_change_request) TABLE=g2p_register_change_requests; PK=change_request_id; COL=deduplication_change_request_status; EXTRA="TRUE" ;;
  dedup_intake_vs_register) TABLE=g2p_intake_form_submissions; PK=submission_id; COL=deduplication_status_vs_register; EXTRA="draft_status = 'FINAL'" ;;
  dedup_intake_vs_intake) TABLE=g2p_intake_form_submissions; PK=submission_id; COL=deduplication_status_vs_intake_forms; EXTRA="draft_status = 'FINAL'" ;;
  intake_register_ingest) TABLE=g2p_intake_form_submissions; PK=submission_id; COL=register_ingest_process_status; EXTRA="approval_status = 'APPROVED'" ;;
  functional_id_allocation) TABLE=g2p_functional_id_generation_queue; PK=queue_id; COL=id_allocation_status; EXTRA="TRUE" ;;
  functional_id_updation) TABLE=g2p_functional_id_generation_queue; PK=queue_id; COL=id_updation_status; EXTRA="TRUE" ;;
  score_compute) TABLE=g2p_score_compute_queue; PK=queue_id; COL=compute_status; EXTRA="TRUE" ;;
  completion_score) TABLE=g2p_completion_score_computation_queue; PK=queue_id; COL=compute_status; EXTRA="TRUE" ;;
  import_file_process) TABLE=import_file_process_queue; PK=import_file_id; COL=intake_form_ingestion_status; EXTRA="TRUE" ;;
  *) echo "Unknown task: $CASE" >&2; exit 2 ;;
esac

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/perftest.yaml}"

echo "Stopping beat and workers"
kubectl -n "$NS" scale deploy/farmer-registry-celery-beat-producer --replicas=0
kubectl -n "$NS" scale deploy/farmer-registry-celery-worker --replicas=0
# rollout status does not return when the desired count is already 0.
for _ in $(seq 1 60); do
  # grep exits 1 when no pods match. That is the state we want, not a script failure.
  left="$(kubectl -n "$NS" get pods --no-headers 2>/dev/null | grep -E 'celery-beat-producer|celery-worker' | grep -v redis | wc -l || true)"
  left="${left// /}"
  [[ "${left:-0}" -eq 0 ]] && break
  sleep 2
done
echo "Beat and workers are at 0 replicas"

OUT="$ROOT/../results/${CASE}-workers-${WORKERS}-size-${SIZE}.csv"
mkdir -p "$(dirname "$OUT")"
# --wait hangs on this cluster even when the pod is already gone.
# apply while the name is still terminating leaves the pod unchanged.
kubectl -n "$NS" delete pod celery-collect --ignore-not-found --wait=false >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  kubectl -n "$NS" get pod celery-collect >/dev/null 2>&1 || break
  sleep 1
done
kubectl -n "$NS" apply -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: celery-collect
  namespace: ${NS}
spec:
  restartPolicy: Never
  containers:
    - name: psql
      image: postgres:16-alpine
      env:
        - name: PGHOST
          value: "172.29.2.191"
        - name: PGDATABASE
          value: farmer_registry
        - name: PGUSER
          value: farmer_registry_user
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: farmer-registry
              key: farmer-registry-db-user
      command: ["sleep", "2400"]
EOF

echo "Restoring any previous pin, then keeping ${SIZE} ${CASE} rows"
"$ROOT/restore-hold.sh"
"$ROOT/pin-case.sh" "$CASE" "$SIZE"

echo "Clearing registry_worker_queue. This Redis rejects FLUSHDB."
kubectl -n "$NS" delete pod redis-clear --ignore-not-found --wait=false >/dev/null 2>&1 || true
kubectl -n "$NS" apply -f - << EOF
apiVersion: v1
kind: Pod
metadata:
  name: redis-clear
  namespace: ${NS}
spec:
  restartPolicy: Never
  containers:
    - name: redis
      image: redis:7-alpine
      command:
        - sh
        - -c
        - redis-cli -h farmer-registry-redis-master -n 0 LLEN registry_worker_queue; redis-cli -h farmer-registry-redis-master -n 0 DEL registry_worker_queue; redis-cli -h farmer-registry-redis-master -n 0 LLEN registry_worker_queue
EOF
for _ in $(seq 1 30); do
  phase="$(kubectl -n "$NS" get pod redis-clear -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "$phase" == "Succeeded" || "$phase" == "Failed" ]] && break
  sleep 2
done
kubectl -n "$NS" logs pod/redis-clear
kubectl -n "$NS" delete pod redis-clear --wait=false >/dev/null

collect_ready=""
for _ in $(seq 1 30); do
  phase="$(kubectl -n "$NS" get pod celery-collect -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  deleting="$(kubectl -n "$NS" get pod celery-collect -o jsonpath='{.metadata.deletionTimestamp}' 2>/dev/null || true)"
  if [[ "$phase" == "Running" && -z "$deleting" ]]; then
    collect_ready=1
    break
  fi
  sleep 2
done
[[ -n "$collect_ready" ]] || { echo "celery-collect did not start" >&2; exit 1; }

echo "Starting workers=${WORKERS} beat=1"
kubectl -n "$NS" scale deploy/farmer-registry-celery-worker --replicas="$WORKERS"
kubectl -n "$NS" scale deploy/farmer-registry-celery-beat-producer --replicas=1

echo "mark_min,pending,in_progress,done,parked,done_delta" | tee "$OUT"
baseline=""
start=$(date +%s)
for mark in $MARKS; do
  target=$((start + mark * 60))
  now=$(date +%s)
  if (( target > now )); then
    sleep $((target - now))
  fi
  row="$(kubectl -n "$NS" exec celery-collect -- psql -At -F, -c \
    "SELECT ${mark},
            COUNT(*) FILTER (WHERE ${COL} = 'PENDING' AND (${EXTRA})),
            COUNT(*) FILTER (WHERE ${COL} IN ('PROCESSING','INPROGRESS') AND (${EXTRA})),
            COUNT(*) FILTER (WHERE ${COL} IN ('PROCESSED','COMPLETED') AND (${EXTRA})),
            COUNT(*) FILTER (WHERE ${COL} = 'FAILED' AND (${EXTRA}))
     FROM ${TABLE}
     WHERE ${PK}::text IN (SELECT row_id FROM celery_perf_cohort)")"
  IFS=',' read -r _mark _pending _in_progress done_now _parked <<< "$row"
  if [[ -z "$baseline" ]]; then
    baseline="$done_now"
  fi
  echo "${row},$((done_now - baseline))" | tee -a "$OUT"
  if [[ "${_pending}" -eq 0 && "${_in_progress}" -eq 0 ]]; then
    echo "Pending and in_progress are 0. Stopping collection."
    break
  fi
done

echo "COLLECTOR_FINISHED ${OUT}"
kubectl -n "$NS" scale deploy/farmer-registry-celery-beat-producer --replicas=0
kubectl -n "$NS" scale deploy/farmer-registry-celery-worker --replicas=0
kubectl -n "$NS" delete pod celery-collect --wait=false >/dev/null

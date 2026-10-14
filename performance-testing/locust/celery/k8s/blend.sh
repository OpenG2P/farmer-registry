#!/usr/bin/env bash
# One blend run: every beat producer and worker on, except dedup_change_request,
# outgest_topic_register, and functional_id_updation. Each producer keeps its
# isolated frequency. Every producer claims at most 3000 tasks per tick.
# Each case keeps a backlog of 10000.
# import_file_process keeps 2 files per worker pod. The files together hold 10000 records.
# The script populates every included case, then pins, then starts the run.
# Counts are written inside pod celery-collect. Copy that file when you want it.
#
#   ./blend.sh 1
#   ./blend.sh 2
#   ./blend.sh 3
#
# CSV: results/pod-<workers>/blend/blend-workers-<workers>.csv
# Columns: mark_min,case,pending,in_progress,done
# import_file_process counts records. Every other case counts status rows.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${CELERY_NAMESPACE:-perftest}"
WORKERS="${1:?workers 1, 2, or 3}"
IMPORT_FILES=$((WORKERS * 2))

[[ "$WORKERS" =~ ^[123]$ ]] || { echo "workers must be 1, 2, or 3" >&2; exit 2; }

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/perftest.yaml}"

# name, isolated backlog. Order is the CSV order.
# dedup_change_request, outgest_topic_register, and functional_id_updation are omitted.
BLEND_CASES=(
  "dedup_register:10000"
  "completion_score:10000"
  "dedup_intake_vs_register:10000"
  "dedup_intake_vs_intake:10000"
  "intake_register_ingest:10000"
  "functional_id_allocation:10000"
  "score_compute:10000"
  "ingest_data_classification:10000"
  "ingest_data_transformation:10000"
  "ingest_data:10000"
  "change_request_ingest:10000"
  "outgest_data_transformation:10000"
  "outgest_data_publish:10000"
  "import_file_process:${IMPORT_FILES}"
)

case_sql() {
  local name="$1"
  local mark="$2"
  local table pk col extra
  case "$name" in
    ingest_data_classification) table=incoming_raw_data; pk=ingest_id; col=classification_status; extra="TRUE" ;;
    ingest_data_transformation) table=incoming_classified_data; pk=ingest_id; col=transformation_status; extra="TRUE" ;;
    ingest_data) table=incoming_classified_data; pk=ingest_id; col=ingestion_status; extra="pipeline_action IS DISTINCT FROM 'UPDATE'" ;;
    change_request_ingest) table=incoming_classified_data; pk=ingest_id; col=ingestion_status; extra="pipeline_action = 'UPDATE'" ;;
    outgest_data_transformation) table=outgoing_raw_data; pk=outgest_id; col=transformation_status; extra="TRUE" ;;
    outgest_data_publish) table=outgoing_raw_data; pk=outgest_id; col=publish_status; extra="TRUE" ;;
    dedup_register) table=g2p_register_change_requests; pk=change_request_id; col=deduplication_register_status; extra="TRUE" ;;
    dedup_intake_vs_register) table=g2p_intake_form_submissions; pk=submission_id; col=deduplication_status_vs_register; extra="draft_status = 'FINAL'" ;;
    dedup_intake_vs_intake) table=g2p_intake_form_submissions; pk=submission_id; col=deduplication_status_vs_intake_forms; extra="draft_status = 'FINAL'" ;;
    intake_register_ingest) table=g2p_intake_form_submissions; pk=submission_id; col=register_ingest_process_status; extra="approval_status = 'APPROVED'" ;;
    functional_id_allocation) table=g2p_functional_id_generation_queue; pk=queue_id; col=id_allocation_status; extra="TRUE" ;;
    score_compute) table=g2p_score_compute_queue; pk=queue_id; col=compute_status; extra="TRUE" ;;
    completion_score) table=g2p_completion_score_computation_queue; pk=queue_id; col=compute_status; extra="TRUE" ;;
    import_file_process)
      printf '%s' "SELECT ${mark}, 'import_file_process',
        COALESCE(GREATEST(
          SUM(COALESCE(q.number_of_records_present, 0))
          - SUM(COALESCE(logged.n, 0))
          - SUM(CASE
              WHEN q.intake_form_ingestion_status IN ('PROCESSING','INPROGRESS')
               AND COALESCE(logged.n, 0) < COALESCE(q.number_of_records_present, 0)
              THEN 1 ELSE 0 END),
          0), 0),
        COALESCE(SUM(CASE
              WHEN q.intake_form_ingestion_status IN ('PROCESSING','INPROGRESS')
               AND COALESCE(logged.n, 0) < COALESCE(q.number_of_records_present, 0)
              THEN 1 ELSE 0 END), 0),
        COALESCE(SUM(COALESCE(logged.n, 0)), 0)
      FROM import_file_process_queue q
      LEFT JOIN (
        SELECT import_file_id, COUNT(*) AS n
        FROM import_file_process_log
        GROUP BY import_file_id
      ) logged ON logged.import_file_id = q.import_file_id
      WHERE q.import_file_id::text IN (
        SELECT row_id FROM celery_perf_blend WHERE case_name = 'import_file_process'
      )"
      return
      ;;
    *) echo "Unknown blend case: $name" >&2; exit 2 ;;
  esac
  printf '%s' "SELECT ${mark}, '${name}',
    COUNT(*) FILTER (WHERE ${col} = 'PENDING' AND (${extra})),
    COUNT(*) FILTER (WHERE ${col} IN ('PROCESSING','INPROGRESS') AND (${extra})),
    COUNT(*) FILTER (WHERE ${col} IN ('PROCESSED','COMPLETED') AND (${extra}))
  FROM ${table}
  WHERE ${pk}::text IN (
    SELECT row_id FROM celery_perf_blend WHERE case_name = '${name}'
  )"
}

wait_celery_ready() {
  local want="$1"
  local needle="$2"
  local label="$3"
  local pod_re="$4"
  for _ in $(seq 1 150); do
    local ready_pods=0
    local names
    names="$(kubectl -n "$NS" get pods --no-headers -o custom-columns=NAME:.metadata.name,PHASE:.status.phase 2>/dev/null | grep -E "$pod_re" | grep -v redis || true)"
    local name phase
    while read -r name phase; do
      [[ -n "${name:-}" && "$phase" == "Running" ]] || continue
      if timeout 8 kubectl -n "$NS" logs "$name" --tail=30 2>/dev/null | grep -qE "$needle"; then
        ready_pods=$((ready_pods + 1))
      fi
    done <<< "$names"
    if [[ "$ready_pods" -ge "$want" ]]; then
      echo "${label} ready (${ready_pods})"
      return 0
    fi
    sleep 2
  done
  echo "${label} did not reach a ready Celery process" >&2
  return 1
}

echo "Stopping beat and workers"
kubectl -n "$NS" scale deploy/farmer-registry-celery-beat-producer --replicas=0
kubectl -n "$NS" scale deploy/farmer-registry-celery-worker --replicas=0
for _ in $(seq 1 60); do
  left="$(kubectl -n "$NS" get pods --no-headers 2>/dev/null | grep -E 'celery-beat-producer|celery-worker' | grep -v redis | wc -l || true)"
  left="${left// /}"
  [[ "${left:-0}" -eq 0 ]] && break
  sleep 2
done
echo "Beat and workers are at 0 replicas"
[[ "${left:-0}" -eq 0 ]] || { echo "Beat or worker pods are still running." >&2; exit 1; }

echo "Restoring any previous pin"
"$ROOT/restore-hold.sh"

echo "Populating each blend case while beat and workers are at 0"
for item in "${BLEND_CASES[@]}"; do
  name="${item%%:*}"
  size="${item##*:}"
  if [[ "$name" == "import_file_process" ]]; then
    echo "Populating import_file_process: ${size} files, $((10000 / size)) records each, 10000 records in total"
    IMPORT_FILES="$size" "$ROOT/populate.sh" import_file_process "$((10000 / size))"
  else
    echo "Populating ${name} ${size}"
    "$ROOT/populate.sh" "$name" "$size"
  fi
done

echo "Setting isolated frequencies and 3000 tasks per tick, with every producer on except change-request dedup, topic register, and functional id updation"
kubectl -n "$NS" set env deploy/farmer-registry-celery-beat-producer \
  REGISTRY_CELERY_BEAT_NO_OF_TASKS_TO_PROCESS=3000 \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_REGISTER_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_CHANGE_REQUEST_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_INTAKE_FORMS_VS_REGISTER_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_INTAKE_FORMS_VS_INTAKE_FORMS_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_COMPLETION_SCORE_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_COMPLETION_SCORE_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_INTAKE_FORM_REGISTER_INGEST_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_INTAKE_FORM_REGISTER_INGEST_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_ALLOCATION_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_ALLOCATION_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_UPDATION_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_UPDATION_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_SCORE_COMPUTE_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_SCORE_COMPUTE_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_INGEST_DATA_CLASSIFICATION_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_INGEST_DATA_CLASSIFICATION_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_DATA_TRANSFORMATION_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_INGEST_DATA_TRANSFORMATION_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_OUTGEST_DATA_TRANSFORMATION_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_INGEST_DATA_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_INGEST_DATA_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_OUTGEST_DATA_PUBLISH_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_OUTGEST_DATA_PUBLISH_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_OUTGEST_TOPIC_REGISTER_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_OUTGEST_TOPIC_REGISTER_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_IMPORT_FILE_PROCESS_BEAT_PRODUCER_FREQUENCY=10 \
  REGISTRY_CELERY_BEAT_IMPORT_FILE_PROCESS_BEAT_PRODUCER_NO_OF_TASKS=3000 \
  REGISTRY_CELERY_BEAT_COMPLETION_SCORE_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_CHANGE_REQUEST_BEAT_PRODUCER_ENABLED=false \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_INTAKE_FORMS_VS_INTAKE_FORMS_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_INTAKE_FORMS_VS_REGISTER_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_DEDUPLICATION_REGISTER_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_ALLOCATION_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_FUNCTIONAL_ID_UPDATION_BEAT_PRODUCER_ENABLED=false \
  REGISTRY_CELERY_BEAT_IMPORT_FILE_PROCESS_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_INGEST_DATA_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_INGEST_DATA_CLASSIFICATION_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_INGEST_DATA_TRANSFORMATION_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_INTAKE_FORM_REGISTER_INGEST_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_OUTGEST_DATA_PUBLISH_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_OUTGEST_DATA_TRANSFORMATION_BEAT_PRODUCER_ENABLED=true \
  REGISTRY_CELERY_BEAT_OUTGEST_TOPIC_REGISTER_BEAT_PRODUCER_ENABLED=false \
  REGISTRY_CELERY_BEAT_SCORE_COMPUTE_BEAT_PRODUCER_ENABLED=true
kubectl -n "$NS" set env deploy/farmer-registry-celery-worker \
  REGISTRY_CELERY_WORKERS_CHANGE_REQUEST_INGEST_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_COMPLETION_SCORE_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_DEDUPLICATION_CHANGE_REQUEST_WORKER_ENABLED=false \
  REGISTRY_CELERY_WORKERS_DEDUPLICATION_INTAKE_FORMS_VS_INTAKE_FORMS_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_DEDUPLICATION_INTAKE_FORMS_VS_REGISTER_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_DEDUPLICATION_REGISTER_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_FUNCTIONAL_ID_ALLOCATION_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_FUNCTIONAL_ID_UPDATION_WORKER_ENABLED=false \
  REGISTRY_CELERY_WORKERS_IMPORT_FILE_PROCESS_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_INGEST_DATA_CLASSIFICATION_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_INGEST_DATA_TRANSFORMATION_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_INGEST_DATA_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_INTAKE_FORM_REGISTER_INGEST_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_OUTGEST_DATA_PUBLISH_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_OUTGEST_DATA_TRANSFORMATION_WORKER_ENABLED=true \
  REGISTRY_CELERY_WORKERS_OUTGEST_TOPIC_REGISTER_WORKER_ENABLED=false \
  REGISTRY_CELERY_WORKERS_SCORE_COMPUTE_WORKER_ENABLED=true

echo "Clearing the worker queue. This Redis rejects FLUSHDB."
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
        - |
          redis-cli -h farmer-registry-redis-master -n 0 DEL registry_worker_queue unacked unacked_index unacked_mutex
          echo "queue_after \$(redis-cli -h farmer-registry-redis-master -n 0 LLEN registry_worker_queue)"
          echo "unacked_after \$(redis-cli -h farmer-registry-redis-master -n 0 HLEN unacked)"
          echo "unacked_index_after \$(redis-cli -h farmer-registry-redis-master -n 0 ZCARD unacked_index)"
EOF
for _ in $(seq 1 30); do
  phase="$(kubectl -n "$NS" get pod redis-clear -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "$phase" == "Succeeded" || "$phase" == "Failed" ]] && break
  sleep 2
done
kubectl -n "$NS" logs pod/redis-clear
kubectl -n "$NS" delete pod redis-clear --wait=false >/dev/null
[[ "$phase" == "Succeeded" ]] || { echo "redis-clear did not finish cleanly" >&2; exit 1; }

echo "Starting workers=${WORKERS}. Beat stays at 0 until every case is pinned."
kubectl -n "$NS" scale deploy/farmer-registry-celery-worker --replicas="$WORKERS"
wait_celery_ready "$WORKERS" ' ready\.' "Workers" 'celery-worker'

echo "Pinning each blend case to its isolated backlog. import_file_process keeps ${IMPORT_FILES} files."
{
  cat "$ROOT/sql/case_defs.sql"
  echo "CREATE TEMP TABLE celery_blend_size (name text PRIMARY KEY, keep_size int NOT NULL);"
  echo "INSERT INTO celery_blend_size (name, keep_size) VALUES"
  sep=""
  for item in "${BLEND_CASES[@]}"; do
    name="${item%%:*}"
    size="${item##*:}"
    printf '%s\n' "${sep}  ('${name}', ${size})"
    sep=","
  done
  echo ";"
  cat "$ROOT/sql/blend_pin.sql"
} | "$ROOT/psql.sh" celery-pin

echo "Starting beat"
kubectl -n "$NS" scale deploy/farmer-registry-celery-beat-producer --replicas=1
wait_celery_ready 1 'beat: Starting|Sent task to ' "Beat" 'celery-beat-producer'

sql=""
for item in "${BLEND_CASES[@]}"; do
  name="${item%%:*}"
  piece="$(case_sql "$name" "__MARK__")"
  if [[ -z "$sql" ]]; then
    sql="$piece"
  else
    sql="${sql} UNION ALL ${piece}"
  fi
done
sql="${sql} ORDER BY 2"

collect_dir="$(mktemp -d)"
printf '%s\n' "$sql" > "$collect_dir/query.sql"
cat > "$collect_dir/collect.sh" << EOF
#!/bin/sh
set -eu
OUT=/csv/blend-workers-${WORKERS}.csv
mkdir -p /csv
echo "mark_min,case,pending,in_progress,done" > "\$OUT"
start=\$(date +%s)
mark=0
while true; do
  target=\$((start + mark * 60))
  now=\$(date +%s)
  if [ "\$target" -gt "\$now" ]; then
    sleep \$((target - now))
  fi
  query=\$(sed "s/__MARK__/\${mark}/g" /script/query.sql)
  rows=\$(printf '%s\\n' "\$query" | psql -v ON_ERROR_STOP=1 -At -F, -f -)
  printf '%s\\n' "\$rows" >> "\$OUT"
  if printf '%s\\n' "\$rows" | awk -F, 'NF < 5 { next } \$3 != "0" || \$4 != "0" { bad = 1 } END { exit (bad ? 0 : 1) }'; then
    mark=\$((mark + 1))
  else
    break
  fi
done
echo "COLLECTOR_FINISHED" > /csv/status
while true; do sleep 3600; done
EOF

kubectl -n "$NS" delete pod celery-collect --ignore-not-found --wait=false >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  kubectl -n "$NS" get pod celery-collect >/dev/null 2>&1 || break
  sleep 1
done
kubectl -n "$NS" create configmap celery-blend-collect \
  --from-file="$collect_dir/collect.sh" \
  --from-file="$collect_dir/query.sql" \
  --dry-run=client -o yaml | kubectl -n "$NS" apply -f -
rm -rf "$collect_dir"

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
      command: ["sh", "/script/collect.sh"]
      volumeMounts:
        - name: script
          mountPath: /script
        - name: csv
          mountPath: /csv
  volumes:
    - name: script
      configMap:
        name: celery-blend-collect
        defaultMode: 0755
    - name: csv
      emptyDir: {}
EOF
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

echo "Collection is running in pod celery-collect. Beat and workers stay up."
echo "Copy the CSV to the laptop with:"
echo "kubectl -n ${NS} cp celery-collect:/csv/blend-workers-${WORKERS}.csv results/pod-${WORKERS}/blend/blend-workers-${WORKERS}.csv"
echo "Scale beat and workers to 0 after you have the file."

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
[[ "${left:-0}" -eq 0 ]] || { echo "Beat or worker pods are still running. Not clearing Redis." >&2; exit 1; }

OUT="$ROOT/../results/pod-${WORKERS}/${CASE}/${CASE}-workers-${WORKERS}-size-${SIZE}.csv"
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
      if kubectl -n "$NS" logs "$name" --tail=400 2>/dev/null | grep -q "$needle"; then
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

echo "Putting the previous cohort back to PENDING and removing its result rows"
case "$CASE" in
  dedup_register) RESULT_TABLE=deduplication_register_results; RESULT_COL=change_request_id ;;
  dedup_change_request) RESULT_TABLE=deduplication_change_request_results; RESULT_COL=change_request_id ;;
  dedup_intake_vs_register) RESULT_TABLE=dedup_results_intake_forms_vs_register; RESULT_COL=submission_id ;;
  dedup_intake_vs_intake) RESULT_TABLE=dedup_results_intake_forms_vs_intake_forms; RESULT_COL=submission_id ;;
  *) RESULT_TABLE=""; RESULT_COL="" ;;
esac
RESULT_SQL=""
if [[ -n "$RESULT_TABLE" ]]; then
  RESULT_SQL="
    DELETE FROM ${RESULT_TABLE}
     WHERE CAST(${RESULT_COL} AS text) IN (SELECT row_id FROM celery_perf_cohort);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;"
fi
# A previous ingest already wrote these ids into the live register. Give the
# intake rows new ids instead of deleting from the 50M register tables.
INGEST_SQL=""
if [[ "$CASE" == "intake_register_ingest" ]]; then
  INGEST_SQL="
    CREATE TEMP TABLE perf_id_remap ON COMMIT DROP AS
    SELECT DISTINCT x.internal_record_id AS old_id, gen_random_uuid()::text AS new_id
      FROM (
        SELECT internal_record_id FROM g2p_intake_form_farmers
         WHERE submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
        UNION ALL
        SELECT internal_record_id FROM g2p_intake_form_lands
         WHERE submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
        UNION ALL
        SELECT internal_record_id FROM g2p_intake_form_crops
         WHERE submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
        UNION ALL
        SELECT internal_record_id FROM g2p_intake_form_livestocks
         WHERE submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
        UNION ALL
        SELECT internal_record_id FROM g2p_intake_form_farm_inputs
         WHERE submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
        UNION ALL
        SELECT internal_record_id FROM g2p_intake_form_membership_details
         WHERE submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
      ) x
     WHERE x.internal_record_id IS NOT NULL;

    UPDATE g2p_intake_form_farmers f
       SET internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.internal_record_id = m.old_id;
    UPDATE g2p_intake_form_lands f
       SET internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.internal_record_id = m.old_id;
    UPDATE g2p_intake_form_crops f
       SET internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.internal_record_id = m.old_id;
    UPDATE g2p_intake_form_livestocks f
       SET internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.internal_record_id = m.old_id;
    UPDATE g2p_intake_form_farm_inputs f
       SET internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.internal_record_id = m.old_id;
    UPDATE g2p_intake_form_membership_details f
       SET internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.internal_record_id = m.old_id;

    UPDATE g2p_intake_form_farmers f
       SET link_internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.link_internal_record_id = m.old_id;
    UPDATE g2p_intake_form_lands f
       SET link_internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.link_internal_record_id = m.old_id;
    UPDATE g2p_intake_form_crops f
       SET link_internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.link_internal_record_id = m.old_id;
    UPDATE g2p_intake_form_livestocks f
       SET link_internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.link_internal_record_id = m.old_id;
    UPDATE g2p_intake_form_farm_inputs f
       SET link_internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.link_internal_record_id = m.old_id;
    UPDATE g2p_intake_form_membership_details f
       SET link_internal_record_id = m.new_id
      FROM perf_id_remap m
     WHERE f.submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort)
       AND f.link_internal_record_id = m.old_id;

    UPDATE g2p_intake_form_submissions
       SET register_ingest_process_attempts = 0,
           register_ingest_process_last_error_code = NULL
     WHERE submission_id IN (SELECT row_id::uuid FROM celery_perf_cohort);"
fi
kubectl -n "$NS" exec celery-collect -- psql -v ON_ERROR_STOP=1 -c "
DO \$\$
DECLARE
  reset_count bigint := 0;
  deleted_count bigint := 0;
BEGIN
  IF to_regclass('public.celery_perf_cohort') IS NULL THEN
    RAISE NOTICE 'no previous cohort';
    RETURN;
  END IF;
  ${INGEST_SQL}
  UPDATE ${TABLE}
     SET ${COL} = 'PENDING'
   WHERE CAST(${PK} AS text) IN (SELECT row_id FROM celery_perf_cohort)
     AND ${COL} IS DISTINCT FROM 'PENDING';
  GET DIAGNOSTICS reset_count = ROW_COUNT;
  ${RESULT_SQL}
  RAISE NOTICE 'reset % cohort rows to PENDING, deleted % result rows', reset_count, deleted_count;
END \$\$;
"

echo "Restoring any previous pin while beat and workers are stopped"
"$ROOT/restore-hold.sh"

echo "Clearing the worker queue and messages already handed to a worker. This Redis rejects FLUSHDB."
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
          echo "queue_before \$(redis-cli -h farmer-registry-redis-master -n 0 LLEN registry_worker_queue)"
          echo "unacked_before \$(redis-cli -h farmer-registry-redis-master -n 0 HLEN unacked)"
          echo "unacked_index_before \$(redis-cli -h farmer-registry-redis-master -n 0 ZCARD unacked_index)"
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

echo "Starting workers=${WORKERS}. Beat stays at 0 until the rows are seeded."
kubectl -n "$NS" scale deploy/farmer-registry-celery-worker --replicas="$WORKERS"
wait_celery_ready "$WORKERS" ' ready\.' "Workers" 'celery-worker'

echo "Keeping ${SIZE} ${CASE} rows now that the workers are ready"
"$ROOT/pin-case.sh" "$CASE" "$SIZE"

echo "Starting beat"
kubectl -n "$NS" scale deploy/farmer-registry-celery-beat-producer --replicas=1
wait_celery_ready 1 'beat: Starting' "Beat" 'celery-beat-producer'

echo "mark_min,pending,in_progress,done" | tee "$OUT"
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
            COUNT(*) FILTER (WHERE ${COL} IN ('PROCESSED','COMPLETED') AND (${EXTRA}))
     FROM ${TABLE}
     WHERE ${PK}::text IN (SELECT row_id FROM celery_perf_cohort)")"
  IFS=',' read -r _mark _pending _in_progress _done <<< "$row"
  echo "$row" | tee -a "$OUT"
  if [[ "${_pending}" -eq 0 && "${_in_progress}" -eq 0 ]]; then
    echo "Pending and in_progress are 0. Stopping collection."
    break
  fi
done

echo "COLLECTOR_FINISHED ${OUT}"
kubectl -n "$NS" scale deploy/farmer-registry-celery-beat-producer --replicas=0
kubectl -n "$NS" scale deploy/farmer-registry-celery-worker --replicas=0
kubectl -n "$NS" delete pod celery-collect --wait=false >/dev/null

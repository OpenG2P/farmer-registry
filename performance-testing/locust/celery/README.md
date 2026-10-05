# Celery backlog drain

Beat and workers are the pods already in the cluster. This directory adds one
more pod, `celery-collector`, that only reads Postgres and Redis. It does not
scale anything. You scale beat and workers, and you copy the CSV off the
collector.

One case at a time. One collector Job at a time.

## Cases

| `CASE` | Done status |
|---|---|
| `functional_id_allocation` | `id_allocation_status = COMPLETED` |
| `dedup_register` | `deduplication_register_status = COMPLETED` |
| `dedup_change_request` | `deduplication_change_request_status = COMPLETED` |
| `dedup_intake_vs_register` | `deduplication_status_vs_register = COMPLETED` |
| `dedup_intake_vs_intake` | `deduplication_status_vs_intake_forms = COMPLETED` |
| `intake_register_ingest` | `register_ingest_process_status = PROCESSED` |

Dedup is four producers. A change request defaults both dedup columns to
`PENDING`. Leave the sibling column off `PENDING` or the workers are shared.

Beat stays at **1** replica. The chart runs `worker --beat` with no leader
lock, so a second beat pod enqueues the schedule twice.

The chart releases **4** rows per tick (dedup every 30s, the others every 20s
unless overridden). That is a few hundred rows in 30 minutes. Raise
`REGISTRY_CELERY_BEAT_NO_OF_TASKS_TO_PROCESS` on the beat deployment, and set
`TASKS_PER_TICK` in the Job to the same number, before comparing 1, 2, and 3
worker pods. The collector prints the 30-minute enqueue ceiling and will not
start when the eligible row count is not `SIZE`.

## Build once

From this directory:

```bash
docker build -f k8s/Dockerfile -t vin0dkhichar/celery-backlog-collector:latest .
docker push vin0dkhichar/celery-backlog-collector:latest
```

## One case, one worker count

Beat and worker deployments are already in `perftest`. Names follow the chart
(`celery-beat-producer`, `celery-worker`); confirm with
`kubectl -n perftest get deploy`.

1. Scale both to 0. Only this case's rows are eligible.

```bash
kubectl -n perftest scale deploy/<beat> --replicas=0
kubectl -n perftest scale deploy/<worker> --replicas=0
```

2. Edit `k8s/collector-job.yaml`: `CASE`, `SIZE`, `WORKERS`. `WORKERS` is a
   label written into the CSV. It must match the replica count you scale to
   in step 5.

3. Start the collector and wait until it is armed. It is still idle here.

```bash
kubectl -n perftest delete job celery-collector --ignore-not-found
kubectl -n perftest apply -f k8s/collector-job.yaml
kubectl -n perftest logs -l app=celery-collector -f
```

Wait for `COLLECTOR_ARMED`. If preflight exits, the cohort size does not match
`SIZE`, or a sibling status is also `PENDING`.

4. Scale workers, then beat. The clock starts when the first row leaves
   `PENDING`, not when the pod started.

```bash
kubectl -n perftest scale deploy/<worker> --replicas=1
kubectl -n perftest scale deploy/<beat> --replicas=1
```

5. Leave them running. The log prints a row at 0, 5, 10, 15, 20, 25, and 30
   minutes. `done_delta` is rows that reached the done status since the arm.
   After `COLLECTOR_FINISHED` the container sleeps so the file can be copied:

```bash
POD=$(kubectl -n perftest get pod -l app=celery-collector -o jsonpath='{.items[0].metadata.name}')
kubectl -n perftest cp "$POD:/results/dedup_register/workers-1/size-10000.csv" ./dedup_register-workers-1.csv
```

Change the path to the `CASE`, `WORKERS`, and `SIZE` you set. Then delete the
Job. Scale beat and workers back to 0 before the next case.

Repeat the same case at workers 2 and workers 3 with a **new** cohort each
time. Then move to the next `CASE`. Do not set processed intake or allocation
rows back to `PENDING` to refill: ingest inserts register rows again, and
allocation calls the id generator again.

`redis_depth` near 0 with `done_delta` stuck at the beat ceiling means the
tick size is the limit. A queue that stays deep means the worker pods are the
limit.

# Celery backlog drain

Beat stays at 1 replica. Worker pods are 1, then 2, then 3. One scenario at a
time. The scenario list, status columns, and how to read the CSV are in
[the test scenarios](../../../documentation/celery/test-scenarios.md).

From this directory, with `KUBECONFIG` pointed at the perftest cluster:

```bash
./k8s/populate.sh <scenario> <size>   # beat and workers must already be 0
./k8s/run.sh <1|2|3> <scenario> <size>
```

One pod and a 10k backlog, one example per scenario. Beat and workers must be
at 0 before populate. The 2-pod and 3-pod repeats are the same commands with
the first argument changed.

```bash
./k8s/populate.sh dedup_register 10000
./k8s/run.sh 1 dedup_register 10000

./k8s/populate.sh dedup_change_request 10000
./k8s/run.sh 1 dedup_change_request 10000

./k8s/populate.sh dedup_intake_vs_register 10000
./k8s/run.sh 1 dedup_intake_vs_register 10000

./k8s/populate.sh dedup_intake_vs_intake 10000
./k8s/run.sh 1 dedup_intake_vs_intake 10000

./k8s/populate.sh completion_score 10000
./k8s/run.sh 1 completion_score 10000

./k8s/populate.sh functional_id_allocation 10000
./k8s/run.sh 1 functional_id_allocation 10000

./k8s/populate.sh functional_id_updation 10000
./k8s/run.sh 1 functional_id_updation 10000

./k8s/populate.sh score_compute 10000
./k8s/run.sh 1 score_compute 10000

./k8s/populate.sh ingest_data_classification 10000
./k8s/run.sh 1 ingest_data_classification 10000

./k8s/populate.sh ingest_data_transformation 10000
./k8s/run.sh 1 ingest_data_transformation 10000

./k8s/populate.sh ingest_data 10000
./k8s/run.sh 1 ingest_data 10000

./k8s/populate.sh change_request_ingest 10000
./k8s/run.sh 1 change_request_ingest 10000

./k8s/populate.sh intake_register_ingest 10000
./k8s/run.sh 1 intake_register_ingest 10000

./k8s/populate.sh outgest_data_transformation 10000
./k8s/run.sh 1 outgest_data_transformation 10000

./k8s/populate.sh outgest_data_publish 10000
./k8s/run.sh 1 outgest_data_publish 10000
```

`import_file_process` uses 10000 as the records in each CSV. One pod has two
processes, so this example queues 2 files:

```bash
IMPORT_FILES=2 ./k8s/populate.sh import_file_process 10000
./k8s/run.sh 1 import_file_process 2
```

`outgest_topic_register` is not in that list. A 10k backlog cannot exist for
it; the reason is below.

`./k8s/run.sh` parks every other scenario, pins the backlog, starts the
workers, starts beat, and writes one CSV row per minute until `pending` and
`in_progress` are 0, or until minute 30. The file is
`results/pod-<workers>/<scenario>/<scenario>-workers-<workers>-size-<size>.csv`.

If `./k8s/run.sh` stops after the pods are already running, do not start it
again. `./k8s/collect.sh <workers> <scenario> <size>` only appends the CSV.

Each isolated run enables one beat producer and one worker and disables the
rest. A set `REGISTRY_CELERY_BEAT_<PRODUCER>_NO_OF_TASKS` is the claim size
for that producer. A worker pod is `--concurrency=2`, so one pod has two
processes.

`outgest_topic_register` is not in the 1, 2, 3 worker series. A topic is
unique on `(data_model_id, register_id)`. This database has one data model
and 9 registers, so 9 topics is the maximum. Each task is a single WebSub
register call, and that count does not grow with the farmer backlog, so extra
worker pods do not show a drain or a scaling limit.

`import_file_process` is one CSV per task, and that task stays on one process
until the file finishes. A second pod cannot shorten the same file, so it is
not in the 2-pod and 3-pod series. The 1-pod example above uses two files
because that pod has two processes. The CSV counts records ingested, not
queue rows.

`k8s/collector-job.yaml` is the older collector. `./k8s/run.sh` does not use
that image.

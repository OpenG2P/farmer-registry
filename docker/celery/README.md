Both celery codebases (celery-workers and celery-beat-producers), plus the
`run_celery.py` startup wrapper, live in the registry-platform **base** image
`openg2p/openg2p-registry-celery-base`. Farmer's `docker/celery/Dockerfile` only
extends that base with the farmer domain model — it no longer installs celery
itself.

Because both codebases are present in the base, we select which application to
run at startup via environment variables. `run_celery.py` (inherited from the
base) reads them:

1. Run as a Worker (default):

   ```
   CELERY_APP: openg2p_registry_celery_workers.main.celery_app
   CELERY_OPTS: worker --loglevel=info
   ```

2. Run as a Beat producer:

   ```
   CELERY_APP: openg2p_registry_celery_beat_producers.main.celery_app
   CELERY_OPTS: worker --beat --loglevel=info --schedule=/tmp/celery-beat-schedule.db
   ```

These are set per-deployment in the Helm values (celeryWorker / celeryBeatProducer).

# Farmer Registry — Celery image (workers + beat).
#
# Thin extension of the registry-platform celery base image (see
# docker/staff-portal-api/Dockerfile for the full rationale). Adds only the
# farmer domain model; both celery packages, the run_celery.py wrapper, the
# CELERY_* ENV defaults and the CMD are inherited from the base. A single image
# runs as worker or beat, selected at runtime via CELERY_APP.
#
# Build context = repo root (so farmer-extension/ is reachable).
ARG RP_VERSION=develop
FROM openg2p/openg2p-registry-celery-base:${RP_VERSION}

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

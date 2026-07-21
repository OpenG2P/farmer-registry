# Farmer Registry — Partner API image.
#
# Thin extension of the registry-platform base image (see
# docker/staff-portal-api/Dockerfile for the full rationale). Adds only the
# farmer domain model; ENV defaults and the migrate+gunicorn CMD are inherited.
#
# Build context = repo root (so farmer-extension/ is reachable).
ARG RP_VERSION=0.0.0-g2p-5383.272
FROM openg2p/openg2p-registry-partner-api-base:${RP_VERSION}

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

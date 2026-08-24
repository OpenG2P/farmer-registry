# Farmer Registry — Agent Portal API image.
#
# Under the inverted build model the registry-platform publishes the base image
# (platform code + fastapi-common/iam-core runtime + entrypoint/CMD/ENV). This
# image only adds the farmer domain model on top: the farmer-extension is pip-
# installed under its own import name (openg2p_registry_farmer_extension) and
# selected at runtime by REGISTRY_EXTENSION_MODULE (Option C). ENV defaults and
# the migrate+gunicorn CMD are inherited from the base.
#
# This image is NOT optional once the agent portal is enabled. agent-portal-api
# runs the same create-table migration as staff-api, so on the RP base image it
# would create the register tables in the REFERENCE extension's shape. Both
# extensions declare the same table names with different columns, so whichever
# service starts first decides the shape — and when agent-portal-api wins,
# db-seed dies on `column "household_head" ... does not exist` and the whole
# release fails. Setting REGISTRY_EXTENSION_MODULE on the base image is not a
# substitute: the farmer extension is not installed there, so the pod would
# only crash-loop on ModuleNotFoundError.
#
# RP_VERSION pins the openg2p-registry base image tag. Keep it in lockstep with
# the openg2p-registry chart dependency pinned in helm/openg2p-farmer-registry/Chart.yaml.
#
# Build context = repo root (so farmer-extension/ is reachable).
ARG RP_VERSION=0.0.0-develop.414
FROM registry.gitlab.com/openg2p/registry/registry-platform/agent-portal-api:${RP_VERSION}

# Option C: select farmer's domain model (coexists with the base image's
# reference extension; env picks farmer, no uninstall needed).
ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

# Farmer Registry — Staff Portal API image.
#
# Under the inverted build model the registry-platform publishes the base image
# (platform code + fastapi-common/iam-core runtime + entrypoint/CMD/ENV). This
# image only adds the farmer domain model on top: the farmer-extension wheel is
# aliased (see farmer-extension/pyproject.toml [tool.hatch.build.targets.wheel.sources])
# onto the import name `openg2p_registry_extensions`, which the platform resolves
# from site-packages at runtime. ENV defaults and the migrate+gunicorn CMD are
# inherited from the base.
#
# RP_VERSION pins the base image tag. Defaults to `develop`; CI resolves it to a
# released base version and stamps it as an org.openg2p.pin.RP_VERSION label.
#
# Build context = repo root (so farmer-extension/ is reachable).
ARG RP_VERSION=develop
FROM openg2p/openg2p-registry-staff-portal-api-base:${RP_VERSION}

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

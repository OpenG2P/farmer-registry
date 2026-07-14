FROM python:3.12.11-alpine3.22

# Git refs for the OpenG2P packages this image installs. Defaults track the
# moving `develop` branches. In CI the central pipeline (openg2p-packaging @v1)
# resolves each of these to a commit SHA BEFORE the build, passes it as the
# build-arg, and records it as an `org.openg2p.pin.<arg>` OCI image label — so a
# built image is traceable to the exact source commits and is reproducible.
# Locally you can pin explicitly, e.g. --build-arg REGISTRY_PLATFORM_REF=<sha>.
ARG REGISTRY_PLATFORM_REF=develop
ARG FASTAPI_COMMON_REF=develop
ARG IAM_CORE_REF=develop

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libmagic

WORKDIR /app

# Farmer extension — this repo's working tree (build context = repo root).
COPY farmer-extension/ /app/farmer-extension/

# Install the platform packages from their git refs plus the local extension in
# one resolution pass, then drop the build toolchain.
RUN pip install --no-cache-dir \
      "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-common" \
      "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-auth" \
      "git+https://github.com/openg2p/openg2p-iam-service@${IAM_CORE_REF}#subdirectory=iam-core" \
      "git+https://github.com/openg2p/registry-platform@${REGISTRY_PLATFORM_REF}#subdirectory=core/openg2p-registry-core" \
      "git+https://github.com/openg2p/registry-platform@${REGISTRY_PLATFORM_REF}#subdirectory=apis/openg2p-registry-staff-portal-api" \
      /app/farmer-extension \
 && apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1
ENV STAFF_PORTAL_WORKER_TYPE=gunicorn
ENV STAFF_PORTAL_HOST=0.0.0.0
ENV STAFF_PORTAL_PORT=8000
# Default worker count kept low (3) for predictable memory; the Helm chart
# overrides this per-deployment via STAFF_PORTAL_NO_OF_WORKERS in envVars.
ENV STAFF_PORTAL_NO_OF_WORKERS=3

# Use module path for migrate and Gunicorn WSGI app
CMD python3 -m openg2p_registry_staff_portal_api.main migrate; \
    ${STAFF_PORTAL_WORKER_TYPE} "openg2p_registry_staff_portal_api.main:app" --workers ${STAFF_PORTAL_NO_OF_WORKERS} --worker-class uvicorn.workers.UvicornWorker --bind ${STAFF_PORTAL_HOST}:${STAFF_PORTAL_PORT}

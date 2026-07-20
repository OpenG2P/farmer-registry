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
 && apk add --no-cache bash git gettext libpq-dev libffi-dev openssl-dev

WORKDIR /app

# Farmer extension — this repo's working tree (build context = repo root).
COPY farmer-extension/ /app/farmer-extension/

# Both celery components (workers + beat producers) are installed so the single
# image can run as worker or beat, selected at runtime via CELERY_APP.
RUN pip install --no-cache-dir \
      "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-common" \
      "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-auth" \
      "git+https://github.com/openg2p/iam-service@${IAM_CORE_REF}#subdirectory=iam-core" \
      "git+https://github.com/openg2p/registry-platform@${REGISTRY_PLATFORM_REF}#subdirectory=core/openg2p-registry-core" \
      "git+https://github.com/openg2p/registry-platform@${REGISTRY_PLATFORM_REF}#subdirectory=celery/openg2p-registry-celery-beat-producers" \
      "git+https://github.com/openg2p/registry-platform@${REGISTRY_PLATFORM_REF}#subdirectory=celery/openg2p-registry-celery-workers" \
      /app/farmer-extension \
 && apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1
ENV CELERY_APP=openg2p_registry_celery_workers.main.celery_app
ENV CELERY_OPTS="worker --loglevel=info"
ENV CELERY_IMPORTS=""

# Build context = repo root.
COPY docker/celery/run_celery.py /app/run_celery.py

# Always use the python wrapper to handle imports and startup
CMD ["python3", "/app/run_celery.py"]

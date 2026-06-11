# Farmer Registry DB-seed image.
#
# Small Postgres-client image that ships the extension's SQL seed scripts
# (meta_data, awe_meta_data, optional sample_data), flat Jinja templates, and
# at container-run time applies SQL against Postgres and optionally uploads
# templates to MinIO.
#
# Build context = repo root (so that farmer-extension/ and docker/db-seed/ are
# both reachable).

ARG EXTENSION_FOLDER=farmer-extension

FROM postgres:16-alpine

ARG EXTENSION_FOLDER
ARG GIT_COMMIT=dev
ARG BUILD_TIME=dev

ENV GIT_COMMIT=${GIT_COMMIT} \
    BUILD_TIME=${BUILD_TIME} \
    EXTENSION_FOLDER=${EXTENSION_FOLDER}

RUN apk add --no-cache python3 py3-pip gettext

COPY docker/db-seed/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Copy seed SQL scripts and flat templates from the extension source tree.
COPY ${EXTENSION_FOLDER}/src/ /tmp/ext-src/

RUN mkdir -p /seed/meta_data /seed/awe_meta_data /seed/sample_data /seed/templates && \
    find /tmp/ext-src -maxdepth 2 -type d \( -name meta_data \) | while read d; do \
      cp -r "$d"/* /seed/meta_data/ 2>/dev/null || true; \
    done && \
    find /tmp/ext-src -maxdepth 2 -type d -name awe_meta_data | while read d; do \
      cp -r "$d"/* /seed/awe_meta_data/ 2>/dev/null || true; \
    done && \
    find /tmp/ext-src -maxdepth 2 -type d -name sample_data | while read d; do \
      cp -r "$d"/* /seed/sample_data/ 2>/dev/null || true; \
    done && \
    find /tmp/ext-src -maxdepth 2 -type d -name templates | while read d; do \
      find "$d" -maxdepth 1 -type f -name '*.j2' -exec cp {} /seed/templates/ \; ; \
    done && \
    rm -rf /tmp/ext-src

COPY docker/db-seed/entrypoint.sh /seed/entrypoint.sh
COPY docker/db-seed/upload_templates.py /seed/upload_templates.py
RUN chmod +x /seed/entrypoint.sh /seed/upload_templates.py

ENTRYPOINT ["/seed/entrypoint.sh"]

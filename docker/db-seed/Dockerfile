# Farmer Registry DB-seed image.
#
# Small Postgres-client image that ships the extension's SQL seed scripts
# (meta_data + optional sample data) and, at container-run time, applies
# them against a target Postgres via the entrypoint script.
#
# Build context = repo root (so that farmer-extension/ and docker/db-seed/ are
# both reachable). Based on the pattern from openg2p-registry-gen2-extensions;
# the farmer extension keeps the source folder name `meta_data/`.

ARG EXTENSION_FOLDER=farmer-extension

FROM postgres:16-alpine

ARG EXTENSION_FOLDER
ARG GIT_COMMIT=dev
ARG BUILD_TIME=dev

ENV GIT_COMMIT=${GIT_COMMIT} \
    BUILD_TIME=${BUILD_TIME} \
    EXTENSION_FOLDER=${EXTENSION_FOLDER}

# Copy seed SQL scripts from the extension source tree:
#   meta_data/ — register definitions, schemas, tabs, sections, attributes, registry-config
#   sample_data/    — demo rows (households, farmers, supporting tables)
COPY ${EXTENSION_FOLDER}/src/ /tmp/ext-src/

# The Python package folder inside src/ varies, so use `find` to locate the
# meta_data/ and sample_data/ folders wherever they live under src/.
# We also accept meta_data/ as a fallback so this image can be reused for
# extensions that follow the NSR naming convention.
RUN mkdir -p /seed/meta_data /seed/sample_data && \
    find /tmp/ext-src -maxdepth 2 -type d \( -name meta_data \) | while read d; do \
      cp -r "$d"/* /seed/meta_data/ 2>/dev/null || true; \
    done && \
    find /tmp/ext-src -maxdepth 2 -type d -name sample_data | while read d; do \
      cp -r "$d"/* /seed/sample_data/ 2>/dev/null || true; \
    done && \
    rm -rf /tmp/ext-src

COPY docker/db-seed/entrypoint.sh /seed/entrypoint.sh
RUN chmod +x /seed/entrypoint.sh

ENTRYPOINT ["/seed/entrypoint.sh"]

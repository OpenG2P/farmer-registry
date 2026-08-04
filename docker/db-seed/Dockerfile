# Farmer Registry — DB-seed image.
#
# Thin extension of the registry-platform db-seed base image. The base ships all
# the generic seeding MACHINERY (entrypoint.sh, load/upload scripts, the shared
# openg2p-data clone). This image adds ONLY farmer's seed content: the SQL
# metadata, AWE metadata and Jinja templates carried by the farmer-extension,
# plus the farmer sub-table sample JSON. The entrypoint (inherited) reads
# /seed/* at container-run time; behaviour is toggled entirely via env from the
# Helm Job.
#
# Build context = repo root (so farmer-extension/ and docker/db-seed/ are both
# reachable).
ARG RP_VERSION=0.0.0-develop.343
FROM registry.gitlab.com/openg2p/registry/registry-platform/db-seed:${RP_VERSION}

# The RP db-seed image ships the reference registry's seed; clear it so only
# farmer's seed is applied.
RUN rm -rf /seed/meta_data/* /seed/awe_meta_data/* /seed/templates/* /seed/seed-data/*

COPY farmer-extension/src/openg2p_registry_farmer_extension/meta_data/     /seed/meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data/ /seed/awe_meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/templates/     /seed/templates/
COPY docker/db-seed/seed-data/                                             /seed/seed-data/

# Analytics seed, distinct from the demo fixture above.
#   seed-data/*.json + the inherited load_sample_data.py  -> the ~500-row smoke set
#                                                            (dbSeed.loadSampleData)
#   generate_fr_bulk_sample.py                            -> volume for the charts
#                                                            (analytics.bulkSample)
# Both write the same tables, so the generator refuses to run on a non-empty
# register rather than colliding with the fixture. The reporting views are
# farmer's own schema and ship here rather than in the base image.
COPY docker/db-seed/generate_fr_bulk_sample.py /seed/generate_fr_bulk_sample.py
COPY docker/db-seed/reporting_views.sql        /seed/reporting_views.sql
RUN chmod +x /seed/generate_fr_bulk_sample.py

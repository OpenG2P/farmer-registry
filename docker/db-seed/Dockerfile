# Farmer Registry — DB-seed image.
#
# Thin extension of the registry-platform db-seed base image. The base ships the
# GENERIC seeding machinery (entrypoint.sh, load_geo_data.py,
# load_attributes_from_mds.py, sync_geo_widgets.py, upload_templates.py, the
# shared openg2p-data clone). This image adds farmer's own content and loaders.
#
# WHY THE SAMPLE LOADERS LIVE HERE
#   load_sample_data.py and upload_images.py are written against the FARMER
#   schema — they INSERT into g2p_register_farmers/crops/lands/... and read
#   farmers.json, crops.json, lands.json. Those tables are declared by
#   farmer-extension and those files ship in this image, so neither the platform
#   nor any other variant can run them: NSR ships its own pair, and the platform
#   installs with loadSampleData=false and no seed-data at all. They used to sit
#   in the base image, which meant a farmer-shaped loader every non-farmer
#   registry had to override — and a farmer id bug (FR-IND) that surfaced as a
#   platform failure. The entrypoint keeps the HOOK; the variant supplies the
#   loader.
#
# The entrypoint (inherited) reads /seed/* at container-run time; behaviour is
# toggled entirely via env from the Helm Job.
#
# Build context = repo root (so farmer-extension/ and docker/db-seed/ are both
# reachable).
ARG RP_VERSION=0.0.0-develop.430
FROM openg2p/openg2p-registry-db-seed:${RP_VERSION}

# The RP db-seed image ships the reference registry's seed; clear it so only
# farmer's seed is applied.
RUN rm -rf /seed/meta_data/* /seed/awe_meta_data/* /seed/templates/* /seed/seed-data/*

COPY farmer-extension/src/openg2p_registry_farmer_extension/meta_data/     /seed/meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data/ /seed/awe_meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/templates/     /seed/templates/
COPY docker/db-seed/seed-data/                                             /seed/seed-data/

# Farmer's domain loaders — see "WHY THE SAMPLE LOADERS LIVE HERE" above. The
# base image no longer carries these; without them LOAD_SAMPLE_DATA/LOAD_IMAGES
# have nothing to run and the entrypoint says so.
COPY docker/db-seed/load_sample_data.py /seed/load_sample_data.py
COPY docker/db-seed/upload_images.py    /seed/upload_images.py
RUN chmod +x /seed/load_sample_data.py /seed/upload_images.py

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
# What the platform's reporting generator cannot infer: which views are
# hand-written, and which column names are organisations rather than people.
COPY docker/db-seed/reporting.yaml            /seed/reporting.yaml
RUN chmod +x /seed/generate_fr_bulk_sample.py

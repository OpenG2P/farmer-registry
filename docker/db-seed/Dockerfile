# Farmer Registry — DB-seed image.
#
# Thin extension of the registry-platform db-seed base image. The base ships the
# GENERIC seeding machinery (entrypoint.sh, load_geo_data.py, sync_geo_widgets.py,
# upload_templates.py, the shared openg2p-data clone). This image adds farmer's
# own content and loaders.
#
# WHY THE SAMPLE LOADERS LIVE HERE
#   load_sample_data.py and upload_images.py are written against the FARMER
#   schema — they INSERT into g2p_register_farmers/crops/lands/... and read
#   farmers.json, crops.json, lands.json. Those tables are declared by
#   farmer-extension and those files ship in this image, so neither the platform
#   nor any other variant can run them. The entrypoint keeps the HOOK; the
#   variant supplies the loader.
#
# The entrypoint (inherited) reads /seed/* at container-run time; behaviour is
# toggled entirely via env from the Helm Job.
#
# Build context = repo root (so farmer-extension/ and docker/db-seed/ are both
# reachable).
ARG RP_VERSION=0.0.0-develop.296
FROM openg2p/openg2p-registry-db-seed:${RP_VERSION}

# The RP db-seed image ships the reference registry's seed; clear it so only
# farmer's seed is applied.
RUN rm -rf /seed/meta_data/* /seed/awe_meta_data/* /seed/templates/* /seed/seed-data/*

COPY farmer-extension/src/openg2p_registry_farmer_extension/meta_data/     /seed/meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data/ /seed/awe_meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/templates/     /seed/templates/
COPY docker/db-seed/seed-data/                                             /seed/seed-data/

# Farmer's domain loaders. Without them LOAD_SAMPLE_DATA/LOAD_IMAGES have
# nothing to run and the inherited entrypoint fails closed.
COPY docker/db-seed/load_sample_data.py    /seed/load_sample_data.py
COPY docker/db-seed/upload_images.py       /seed/upload_images.py
RUN chmod +x /seed/load_sample_data.py /seed/upload_images.py

COPY docker/db-seed/generate_fr_bulk_sample.py /seed/generate_fr_bulk_sample.py
RUN chmod +x /seed/generate_fr_bulk_sample.py

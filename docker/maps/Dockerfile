# Farmer Registry — Maps content for G2P Insights.
#
# Same split the db-seed image uses: the platform ships the MACHINERY, this
# image adds the Farmer Registry's CONTENT.
#
#   openg2p-insights-evidence-builder   Evidence toolchain, node_modules, the
#                                       country-pack boundary sync, the build
#                                       script, and the `registry` connection
#   this image                          this registry's queries and its map page
#
# Why the content lives here and not in Insights: what a map DRAWS belongs to a
# registry. These queries read fr_rpt_farmer and fr_rpt_crop and plot land
# tenure and input use — none of which exists in a social registry, whose maps
# plot poverty and enrolment instead. Insights installed beside a different
# registry needs that registry's queries, exactly as Superset needs its
# dashboards. Keeping them in the platform would have made every Insights
# install silently assume one registry.
#
# The Insights chart runs this image as a Job after install and on a schedule:
# it extracts the SQL against the live registry into parquet, builds the static
# site, and publishes it to the volume the serving pods read.
#
#   insightMaps.build.image.repository = <this image>
#   insightMaps.build.readyView        = fr_rpt_farmer
#   insightMaps.build.refreshViews     = fr_rpt_farmer,fr_rpt_land
#
# Build context = repo root (so docker/maps/ is reachable).
# Pinned to a published build, not a floating tag — the same convention the
# db-seed image uses for its registry-platform base.
ARG INSIGHTS_VERSION=0.0.0-develop.50
FROM registry.gitlab.com/openg2p/g2p-insights/openg2p-insights-evidence-builder:${INSIGHTS_VERSION}

# Replace the reference content wholesale rather than merging: a leftover
# reference query would run against this registry's database and fail the build,
# or worse succeed and put a meaningless panel on the page.
# Fail the BUILD if the base is the wrong stage.
#
# openg2p-insights-evidence-builder must be the `builder` target: the Evidence
# toolchain plus /usr/local/bin/build-into. Until the packaging CI honoured the
# `target` field it published the SERVING stage under this name — no toolchain —
# and the mistake only surfaced in the cluster, as `exec: build-into: not found`
# in a Job nobody watches, after a green install. Catch it here, where the error
# names the cause and nothing is published.
#
# If this fires, the pin above predates that fix: move it to the first
# g2p-insights build published after it.
RUN test -x /usr/local/bin/build-into || { \
      echo "ERROR: base image has no /usr/local/bin/build-into — it is the serving" >&2; \
      echo "       stage, not 'builder'. Bump INSIGHTS_VERSION to a build made after" >&2; \
      echo "       the packaging CI started passing --target." >&2; \
      exit 1; }

USER 0
RUN rm -f /app/sources/registry/*.sql /app/pages/*.md

COPY docker/maps/sources/ /app/sources/registry/
COPY docker/maps/pages/   /app/pages/

# sources/registry/connection.yaml is NOT copied — it comes from the base image
# and is the same for every registry: "the registry's database", with host and
# credentials supplied per environment at build time.
USER 1000

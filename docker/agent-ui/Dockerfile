# Farmer Registry — Agent Portal UI image.
#
# Same steps as a local build. The image has no .app/ yet, so npm install clones
# agent-ui (deps.json) and applies overrides/. npm run build finds .app/ already
# present, skips the clone, applies overrides/ again, then builds Next.
#
#   docker build -f docker/agent-ui/Dockerfile \
#     -t openg2p/openg2p-farmer-registry-agent-ui:local .

FROM node:20-alpine AS builder

RUN apk add --no-cache git bash

WORKDIR /open/farmer-registry/ui/agent-ui

COPY ui/agent-ui/package.json ui/agent-ui/.npmrc ui/agent-ui/deps.json ./
COPY ui/agent-ui/scripts ./scripts
COPY ui/agent-ui/overrides ./overrides

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install
RUN npm run build \
 && mkdir -p /out \
 && cp -a .app/.next/standalone/. /out/ \
 && cp -a .app/public /out/public \
 && mkdir -p /out/.next \
 && cp -a .app/.next/static /out/.next/static

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /out ./

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]

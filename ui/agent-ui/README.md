# Farmer Agent Portal UI

Extended agent-ui app (the agent portal) for the farmer registry. The upstream agent-ui is cloned into `.app/` from `deps.json`. `overrides/` is copied on top.

The clone runs only when `.app/` is missing. `npm run dev`, `npm run build`, and `npm start` still apply `overrides/` so the current overlay is what Next serves.

Notes:

- Do not change anything inside `.app/`. It is generated and replaced.
- Keep the same folder structure in `overrides/` as agent-ui has inside `.app/`. 

For example, these overrides replace the same paths inside `.app/`:

| `overrides/` | replaces |
|---|---|
| `src/components/AppShell.tsx` | `.app/src/components/AppShell.tsx` |
| `src/app/issue/page.tsx` | `.app/src/app/issue/page.tsx` |

| Path | Role |
|------|------|
| `deps.json` | Git pin (`repo` / `ref` / `path`) |
| `overrides/` | Farmer files copied onto the same paths in `.app/` |
| `scripts/` | Clone if needed, apply overrides, install `.app` dependencies |
| `.app/` | Generated app (gitignored; do not edit) |
| `.npmrc` | `package-lock=false` — wrapper has no lockfile; app lock is `.app/package-lock.json` |

## Commands

```bash
cd farmer-registry/ui/agent-ui
npm install            # clone only if .app/ is missing, apply overrides, install deps
npm run dev            # apply overrides, skip clone, start Next
npm run build          # apply overrides, skip clone, build Next
npm start              # apply overrides, skip clone, start the production server
npm run reset          # delete .app/ and clone again
```

## Docker

The image has no `.app/`, so `npm install` clones once. `npm run build` then skips the clone and applies `overrides/` before the Next build.

```bash
cd farmer-registry
docker build -f docker/agent-ui/Dockerfile \
  -t openg2p/openg2p-farmer-registry-agent-ui:local .
```

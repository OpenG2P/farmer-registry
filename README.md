# Farmer Registry

An installable **Farmer Registry** built as a thin extension of the OpenG2P
[registry platform](https://github.com/OpenG2P/registry-platform). Under the
inverted build model the platform publishes the runnable base images and the
`openg2p-registry` Helm chart; this repo adds **only** the farmer domain on top.

## What this repo owns

| Path | Purpose |
|---|---|
| `farmer-extension/` | The farmer domain package — models, schemas, services, seed metadata (registers, AWE policy, DCI templates) |
| `docker/` | Thin Dockerfiles (`FROM openg2p/openg2p-registry-*` + `pip install farmer-extension`) selected at runtime by `REGISTRY_EXTENSION_MODULE` (Option C) |
| `helm/openg2p-farmer-registry/` | A thin wrapper chart: pins `openg2p-registry` as a dependency and supplies the farmer values overlay (no templates) |
| `test/sanity/` | The farmer **field-specific** sanity tests (Set 2); the harness + generic tests are inherited from the platform sanity image |

The `openg2p-registry` base image tag (`RP_VERSION` in each Dockerfile) and the
chart dependency version in `helm/openg2p-farmer-registry/Chart.yaml` are **hardcoded and
pinned together**. The farmer images and the wrapper chart are versioned in
lockstep by CI (one version per commit).

To see which version it would pick, run `./scripts/bump-rp-version.sh -n` (dry-run,
writes nothing); `-h` prints help. To apply, run `./scripts/bump-rp-version.sh`
(latest published version) or `./scripts/bump-rp-version.sh <version>` — it updates
the Dockerfiles and the chart dependency together, so they can never drift. A CI
check (`test/test_rp_pin_lockstep.py`) fails the build if they ever do.

## Deploy

```bash
helm repo add openg2p https://openg2p.github.io/openg2p-helm
helm dependency build ./helm/openg2p-farmer-registry
helm install farmer-registry ./helm/openg2p-farmer-registry \
  --set global.registryHostname=farmer-registry.example.org
```

Set `registry.sanity.runE2e=true` to run the end-to-end sanity suite after install.

See the deployment & extension docs at [docs.openg2p.org](https://docs.openg2p.org).

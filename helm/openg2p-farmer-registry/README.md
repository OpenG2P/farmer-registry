# openg2p-farmer-registry

Thin wrapper Helm chart for the **OpenG2P Farmer Registry**.

This chart does not define templates of its own. It depends on the OpenG2P
Registry Gen 2 base chart and supplies only the Farmer-Registry-specific
overrides:

1. Docker image names for the five Farmer Registry components
2. ID Generator `idTypes` — `farmer` and `household`

Everything else (deployments, services, ingresses, keycloak, postgres,
rabbitmq, helper jobs, …) comes from the base chart.

```
openg2p-registry (0.0.0-develop, base)    +    openg2p-farmer-registry (0.0.0-develop, wrapper)
        │                                              │
        └─────────────────  =  Farmer Registry install  ┘
```

## Versioning

Branch-name-equals-version convention:

| Branch | `Chart.yaml.version` | Depends on base chart |
|---|---|---|
| `develop` | `0.0.0-develop` | `0.0.0-develop` |
| `1.0.0` (release tag branch, future) | `1.0.0` | `1.0.0` |

When cutting a release, both `version` and the base chart `dependencies[0].version`
drop the `-develop` suffix together.

## What it overrides

### Images (five Farmer Registry services)

| Component | Image (built by this repo) |
|---|---|
| staffPortalApi | `openg2p/openg2p-farmer-registry-staff-portal-api:develop` |
| partnerApi | `openg2p/openg2p-farmer-registry-partner-api:develop` |
| staffPortalUi | `openg2p/openg2p-farmer-registry-staff-portal-ui:develop` |
| celeryWorker / celeryBeat | `openg2p/openg2p-farmer-registry-celery:develop` *(same image — mode picked by env vars)* |
| dbSeed | `openg2p/openg2p-farmer-registry-db-seed:develop` |

### ID Generator `idTypes`

The base chart's `idTypes` map already matches what the Farmer Registry needs:

```yaml
idTypes:
  farmer:    { idLength: 12 }
  household: { idLength: 10 }
```

We declare the same map explicitly in this wrapper for clarity.

## Installing

### From this repo (dev / CI)

```bash
cd helm/openg2p-farmer-registry
helm dependency update
helm install farmer-registry . \
  --namespace openg2p-farmer-registry \
  --create-namespace \
  --set openg2p-registry.global.domain=farmer.example.com
```

### From the published Helm repo (once released)

```bash
helm repo add openg2p https://openg2p.github.io/openg2p-helm
helm repo update
helm install farmer-registry openg2p/openg2p-farmer-registry \
  --version 0.0.0-develop \
  --namespace openg2p-farmer-registry \
  --create-namespace
```

### With sample data (dev / test only)

```bash
helm install farmer-registry . \
  --set openg2p-registry.dbSeed.loadSampleData=true
```

Loads the demo households, farmers, lands, crops, livestock, farm inputs,
and supporting-table demo rows from `farmer-extension/src/.../sample_data/`
into the database.

## Upgrading

When the base chart releases a new version, bump the dependency in
`Chart.yaml`:

```yaml
dependencies:
  - name: openg2p-registry
    version: 1.0.0-develop      # was 0.0.0-develop
```

then run `helm dependency update`. For breaking changes, bump this
wrapper's major version too.

## Rancher catalog

The chart ships a `questions.yaml` for Rancher UI installs with fields for:

- Base domain + namespace
- Per-image tag overrides
- DB-seeder toggle (and sample-data toggle)
- ID-type informational note

Advanced users should edit `values.yaml` directly.

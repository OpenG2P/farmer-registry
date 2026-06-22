# Locust load-test assets (starter)

Production-shaped starter for the Farmer Registry load tests. The auth flow,
task structure, blended weights, and id parameterisation are ready; the request
**bodies** are marked `TODO` and must be filled from the registry-platform API
schema/OpenAPI before a real run.

## Files
- `common.py` — config (env vars) + Keycloak OIDC token cache (per simulated user).
- `locustfile.py` — task set implementing the blended mix (reads 70 / writes 20 / DCI 10).

## Install
```bash
pip install locust requests
```

## Configure (env vars)
```bash
export STAFF_API_BASE=http://<release>-staff-portal-api      # in-cluster ClusterIP
export PARTNER_API_BASE=http://<release>-partner-api
export KEYCLOAK_BASE=https://keycloak.<ns>.openg2p.org
export KEYCLOAK_REALM=staff
export OIDC_CLIENT_ID=fr-staff-portal      # = chart global.authClientId
export OIDC_CLIENT_SECRET=...              # if confidential client
export OIDC_USERNAME=...  OIDC_PASSWORD=...
export SEED_MANIFEST=seed_manifest.json    # from the bulk seeder
```

## Run

**Phase 1 — single endpoint capacity** (use `--tags` to isolate; ramp to find max):
```bash
locust -f locustfile.py --headless -u 300 -r 10 -t 15m \
       --host "$STAFF_API_BASE" --tags search --csv results/p1_search
```
Repeat with `--tags record_read`, `--tags dedup`, `--tags write`, `--tags dci`.

**Blended capacity / soak** (all tasks):
```bash
# soak: 80% of measured max for 8h
locust -f locustfile.py --headless -u <80pct_users> -r 10 -t 8h \
       --host "$STAFF_API_BASE" --csv results/soak
```

## Running in-cluster
Build a tiny image (python + locust + these files) and run it as a Job/Deployment
in the namespace so the generator hits the service ClusterIP directly (isolates
the microservice from the RP/ingress). Mount the seed manifest via ConfigMap.

## Notes
- Stats are grouped by logical endpoint via the `name=` argument, so URLs with
  ids don't explode the report.
- For an **open-model** (constant arrival rate) capacity measurement, swap
  `between()` think-time for a constant-pacing/throughput strategy and document
  which model produced each figure.
- Locust CSVs feed directly into the templates in `../templates/`.

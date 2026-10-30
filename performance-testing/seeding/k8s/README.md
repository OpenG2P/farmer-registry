# Kubernetes-based Parallel Seeding

**Canonical command list, 2-pod 10M flow, and indexing notes:**
[`../README.md`](../README.md).

This directory contains Kubernetes resources for running the farmer-registry seeding scripts in parallel across multiple pods to handle large data volumes efficiently.

## Architecture

The seeding system has been modified to support parallel execution across multiple Kubernetes pods:

- **Pod-specific ID ranges**: Each pod is assigned a unique range of functional IDs to prevent duplicates
- **Load balancing**: Farmers are distributed evenly across pods
- **Independent execution**: Each pod runs independently and writes directly to the database
- **Manifest merging**: After completion, individual pod manifests can be merged into a combined manifest

## Configuration

### Data Tiers and Pod Allocation

| Tier      | Total Farmers | Default Pods | Farmers per Pod |
|-----------|---------------|--------------|-----------------|
| smoke     | 10,000        | 1            | 10,000          |
| primary   | 10,000,000    | 10           | 1,000,000       |
| stretch   | 50,000,000    | 15           | 3,333,333       |
| stress    | 100,000,000   | 20           | 5,000,000       |

You can override the default pod count using the `--pods` parameter.

## Quick Start

### 1. Build and Push Docker Image

```bash
cd k8s
./build_and_push.sh
```

Or with custom image name/tag:

```bash
IMAGE_NAME=my-registry/farmer-seeding IMAGE_TAG=v1.0.0 ./build_and_push.sh
```

### 2. Generate Kubernetes Job Manifests

Generate job manifests for a specific tier:

```bash
python3 generate_jobs.py --tier primary --pods 2 --workers 4
```

This creates:
- Individual job files: `seeding-primary-pod-0.yaml`, `seeding-primary-pod-1.yaml`
- `kustomization.yaml` and `kustomization-primary.yaml`

`kubectl apply -k` needs a **directory**, not a file. Do not pass `kustomization-primary.yaml`.

### 3. Deploy Jobs

From this `k8s/` directory, into the farmer-registry namespace:

```bash
kubectl apply -k jobs -n perftest
```

### 4. Monitor Progress

```bash
kubectl get jobs -n perftest -l app=farmer-registry-seeding -w
kubectl logs -n perftest -l app=farmer-registry-seeding --tail=50 -f --prefix
```

### 5. Cleanup

```bash
kubectl delete jobs -n perftest -l app=farmer-registry-seeding
# or: kubectl delete -k jobs -n perftest
```

## Advanced Usage

### Custom Configuration

Generate jobs with custom resource allocation:

```bash
python3 generate_jobs.py \
  --tier primary --pods 2 --workers 4 \
  --image vin0dkhichar/farmer-registry-seeding:v3 \
  --pg-host 172.29.2.191 \
  --cpu-request 250m --cpu-limit 4 \
  --memory-request 1Gi --memory-limit 8Gi
```

### Merging Manifests

After parallel seeding completes, merge the individual pod manifests:

```bash
python3 merge_manifests.py --tier primary --pods 2
```

This creates a combined manifest file `seed_manifest_primary_combined.json`.

## Script Parameters

### generate_jobs.py

- `--tier`: Data volume tier (smoke, primary, stretch, stress)
- `--pods`: Number of pods (overrides tier default)
- `--workers`: COPY processes inside each pod (use 4 with `--pods 2`)
- `--output-dir`: Output directory for manifests (default: k8s/jobs)
- `--image`: Docker image name
- `--pg-host` / `--pg-database` / `--pg-user` / `--db-secret`: Postgres connection
- `--cpu-request/--cpu-limit`: CPU allocation per pod
- `--memory-request/--memory-limit`: Memory allocation per pod

### merge_manifests.py

- `--tier`: Data volume tier
- `--pods`: Number of pods that were used
- `--output-dir`: Directory containing manifest files (default: .)

## Running Locally with Pod Parameters

You can also test the pod-specific ID generation locally:

```bash
# Test pod 0 of 10
python run.py --tier primary --pod-index 0 --total-pods 10

# Test pod 1 of 10
python run.py --tier primary --pod-index 1 --total-pods 10
```

## ID Allocation Strategy

The system uses a pod-specific ID allocation strategy to prevent duplicates:

1. **Farmer IDs**: Each pod gets a range of `(total_farmers / total_pods) + 1000` IDs
2. **Household IDs**: Each pod gets a range of roughly 1/3 the Farmer ID range
3. **Other tables**: Use smaller, pod-specific ranges

The `+ 1000` buffer ensures no overlap even with uneven distribution.

## Database Requirements

- PostgreSQL database must be accessible from the Kubernetes cluster
- Schema and metadata must be pre-loaded (run the standard db-seed job first)
- Sufficient storage and I/O capacity for the target data volume
- Connection pool configured for concurrent writes

## Troubleshooting

### Jobs Fail to Start

Check pod logs for database connection issues:

```bash
kubectl logs -l app=farmer-registry-seeding --tail=50
```

### Duplicate IDs

If you suspect duplicate IDs, check:

1. All pods used different `--pod-index` values
2. The `--total-pods` parameter was consistent across all pods
3. The target farmer count was the same for all pods

### Uneven Distribution

For uneven distribution, the last pod gets any remainder farmers. This is intentional and handled automatically.

## Performance Considerations

- **2 pods for 10M**: `--pods 2 --workers 4` with CPU limit 4 / memory 8Gi per pod.
  That is 8 COPY writers without extra Jobs. Rebuild the image after pulling these changes.
- **Network**: Run pods close to the database (same cluster/region)
- **Batch size**: Default is 50,000 (`SEED_BATCH_SIZE`). Do not raise it with `--workers 4`.
- **Indexes**: automatic. Last finishing pod rebuilds; no manual `CREATE INDEX` unless a pod dies mid-rebuild. See [`../README.md`](../README.md).

## Example Workflow

Complete workflow for 10M farmer test:

See [`../README.md`](../README.md) for the full copy-paste command list (build, generate, apply `-k jobs`, logs, copy manifests, merge, verify SQL, cleanup).
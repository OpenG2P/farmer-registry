#!/usr/bin/env python3
"""Generate Kubernetes Job manifests for parallel seeding execution.

This script creates Kubernetes Job YAML files that run the seeding script
in parallel across multiple pods, with each pod assigned a unique ID range
to prevent duplicates.

Usage:
    python generate_jobs.py --tier primary --pods 10
    python generate_jobs.py --tier stress --pods 20
"""

import argparse
import glob
import os
import sys
import yaml

# Data tier configurations
DATA_VOLUME_TIERS = {
    "smoke": {"farmers": 10_000, "pods": 1},
    "primary": {"farmers": 10_000_000, "pods": 10},
    "stretch": {"farmers": 50_000_000, "pods": 15},
    "stress": {"farmers": 100_000_000, "pods": 20},
}

# Default configuration - can be overridden
DEFAULT_IMAGE = "vin0dkhichar/farmer-registry-seeding:performance-test"
DEFAULT_PGHOST = "commons-postgresql"
DEFAULT_PGPORT = "5432"
DEFAULT_PGDATABASE = "farmer_registry"
DEFAULT_PGUSER = "farmer_registry_user"
DEFAULT_DB_SECRET = "farmer-registry"
DEFAULT_DB_SECRET_KEY = "farmer-registry-db-user"
DEFAULT_CPU_REQUEST = "500m"
DEFAULT_CPU_LIMIT = "2"
DEFAULT_MEMORY_REQUEST = "1Gi"
DEFAULT_MEMORY_LIMIT = "4Gi"
DEFAULT_BACKOFF_LIMIT = 4
DEFAULT_TTL_SECONDS = 86400  # 24 hours


def generate_job_yaml(tier: str, pod_index: int, total_pods: int, config: dict) -> dict:
    """Generate a Kubernetes Job manifest for a single pod."""
    
    job_name = f"seeding-{tier}-pod-{pod_index}"
    
    job_spec = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "labels": {
                "app": "farmer-registry-seeding",
                "tier": tier,
                "pod-index": str(pod_index),
            }
        },
        "spec": {
            "backoffLimit": config.get("backoff_limit", DEFAULT_BACKOFF_LIMIT),
            "ttlSecondsAfterFinished": config.get("ttl_seconds", DEFAULT_TTL_SECONDS),
            "template": {
                "metadata": {
                    "labels": {
                        "app": "farmer-registry-seeding",
                        "tier": tier,
                        "pod-index": str(pod_index),
                    }
                },
                "spec": {
                    "restartPolicy": "OnFailure",
                    "containers": [
                        {
                            "name": "seeding",
                            "image": config.get("image", DEFAULT_IMAGE),
                            "imagePullPolicy": "Always",
                            "command": [
                                "python",
                                "run.py",
                                "--tier", tier,
                                "--pod-index", str(pod_index),
                                "--total-pods", str(total_pods),
                                "--workers", str(config.get("workers", 1)),
                            ],
                            "env": [
                                {
                                    "name": "PGHOST",
                                    "value": config.get("pg_host", DEFAULT_PGHOST),
                                },
                                {
                                    "name": "PGPORT",
                                    "value": config.get("pg_port", DEFAULT_PGPORT),
                                },
                                {
                                    "name": "PGDATABASE",
                                    "value": config.get("pg_database", DEFAULT_PGDATABASE),
                                },
                                {
                                    "name": "PGUSER",
                                    "value": config.get("pg_user", DEFAULT_PGUSER),
                                },
                                {
                                    "name": "PGPASSWORD",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": config.get("db_secret", DEFAULT_DB_SECRET),
                                            "key": config.get("db_secret_key", DEFAULT_DB_SECRET_KEY),
                                        }
                                    },
                                },
                                {
                                    "name": "SEED_DEFER_INDEXES",
                                    "value": "true",
                                },
                                {
                                    "name": "SEED_WORKERS",
                                    "value": str(config.get("workers", 1)),
                                },
                                {
                                    "name": "PYTHONUNBUFFERED",
                                    "value": "1",
                                },
                                {
                                    "name": "SEED_BATCH_SIZE",
                                    "value": "50000",
                                },
                            ],
                            "resources": {
                                "requests": {
                                    "cpu": config.get("cpu_request", DEFAULT_CPU_REQUEST),
                                    "memory": config.get("memory_request", DEFAULT_MEMORY_REQUEST),
                                },
                                "limits": {
                                    "cpu": config.get("cpu_limit", DEFAULT_CPU_LIMIT),
                                    "memory": config.get("memory_limit", DEFAULT_MEMORY_LIMIT),
                                },
                            },
                        }
                    ],
                }
            },
        },
    }
    
    return job_spec


def generate_all_jobs(tier: str, num_pods: int, config: dict, output_dir: str):
    """Generate Kubernetes Job manifests for all pods."""
    
    os.makedirs(output_dir, exist_ok=True)

    keep = {f"seeding-{tier}-pod-{i}.yaml" for i in range(num_pods)}
    for stale in glob.glob(os.path.join(output_dir, f"seeding-{tier}-pod-*.yaml")):
        if os.path.basename(stale) not in keep:
            os.remove(stale)
            print(f"  Removed stale: {stale}")

    print(f"Generating {num_pods} Job manifests for tier '{tier}'")
    
    for pod_index in range(num_pods):
        job_spec = generate_job_yaml(tier, pod_index, num_pods, config)
        
        # Write individual job file
        job_file = os.path.join(output_dir, f"seeding-{tier}-pod-{pod_index}.yaml")
        with open(job_file, "w") as f:
            yaml.dump(job_spec, f, default_flow_style=False)
        
        print(f"  Created: {job_file}")
    
    # Create a kustomization.yaml for easy deployment
    kustomization = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": [f"seeding-{tier}-pod-{i}.yaml" for i in range(num_pods)],
    }
    
    kustomization_file = os.path.join(output_dir, f"kustomization-{tier}.yaml")
    kustomization_default = os.path.join(output_dir, "kustomization.yaml")
    for path in (kustomization_file, kustomization_default):
        with open(path, "w") as f:
            yaml.dump(kustomization, f, default_flow_style=False)

    print(f"Created kustomization: {kustomization_file}")
    print(f"\nTo deploy all jobs:")
    print(f"  kubectl apply -k {output_dir}")
    print(f"\nTo delete all jobs:")
    print(f"  kubectl delete jobs -l app=farmer-registry-seeding")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Kubernetes Job manifests for parallel seeding"
    )
    parser.add_argument(
        "--tier",
        choices=list(DATA_VOLUME_TIERS.keys()),
        required=True,
        help="Data volume tier"
    )
    parser.add_argument(
        "--pods",
        type=int,
        help="Number of pods (overrides default for tier)"
    )
    parser.add_argument(
        "--output-dir",
        default="k8s/jobs",
        help="Output directory for generated manifests"
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help="Docker image for seeding container"
    )
    parser.add_argument(
        "--pg-host",
        default=DEFAULT_PGHOST,
        help="PostgreSQL host"
    )
    parser.add_argument(
        "--pg-port",
        default=DEFAULT_PGPORT,
        help="PostgreSQL port"
    )
    parser.add_argument(
        "--pg-database",
        default=DEFAULT_PGDATABASE,
        help="PostgreSQL database name"
    )
    parser.add_argument(
        "--pg-user",
        default=DEFAULT_PGUSER,
        help="PostgreSQL user"
    )
    parser.add_argument(
        "--db-secret",
        default=DEFAULT_DB_SECRET,
        help="Kubernetes secret name for database password"
    )
    parser.add_argument(
        "--db-secret-key",
        default=DEFAULT_DB_SECRET_KEY,
        help="Key in the secret for database password"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Generator/COPY processes inside each pod (use 4 with --pods 2)",
    )
    parser.add_argument(
        "--cpu-request",
        default=DEFAULT_CPU_REQUEST,
        help="CPU request per pod"
    )
    parser.add_argument(
        "--cpu-limit",
        default=DEFAULT_CPU_LIMIT,
        help="CPU limit per pod"
    )
    parser.add_argument(
        "--memory-request",
        default=DEFAULT_MEMORY_REQUEST,
        help="Memory request per pod"
    )
    parser.add_argument(
        "--memory-limit",
        default=DEFAULT_MEMORY_LIMIT,
        help="Memory limit per pod"
    )
    
    args = parser.parse_args()
    
    # Determine number of pods
    tier_config = DATA_VOLUME_TIERS[args.tier]
    num_pods = args.pods if args.pods else tier_config["pods"]
    
    # Build configuration
    config = {
        "image": args.image,
        "pg_host": args.pg_host,
        "pg_port": args.pg_port,
        "pg_database": args.pg_database,
        "pg_user": args.pg_user,
        "db_secret": args.db_secret,
        "db_secret_key": args.db_secret_key,
        "cpu_request": args.cpu_request,
        "cpu_limit": args.cpu_limit,
        "memory_request": args.memory_request,
        "memory_limit": args.memory_limit,
        "workers": args.workers,
    }
    
    # Generate jobs
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", args.output_dir)
    generate_all_jobs(args.tier, num_pods, config, output_dir)


if __name__ == "__main__":
    main()
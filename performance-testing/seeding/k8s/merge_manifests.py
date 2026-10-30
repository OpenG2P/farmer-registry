#!/usr/bin/env python3
"""Merge seed manifests from multiple pods into a single manifest.

After running parallel seeding jobs, each pod generates its own manifest file.
This script merges them into a single combined manifest for testing.

Usage:
    python merge_manifests.py --tier primary --pods 10
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def merge_manifests(tier: str, total_pods: int, output_dir: str):
    """Merge manifest files from all pods into a single manifest."""
    
    # Find all manifest files for this tier
    manifest_files = []
    for name in sorted(os.listdir(output_dir)):
        if name.startswith("seed_manifest_pod") and name.endswith(".json"):
            manifest_files.append(os.path.join(output_dir, name))
    if not manifest_files:
        for pod_index in range(total_pods):
            manifest_file = os.path.join(output_dir, f"seed_manifest_pod{pod_index}.json")
            if os.path.exists(manifest_file):
                manifest_files.append(manifest_file)
            else:
                print(f"Warning: Manifest file not found: {manifest_file}")
    
    if not manifest_files:
        print(f"Error: No manifest files found for tier '{tier}' with {total_pods} pods")
        sys.exit(1)
    
    print(f"Found {len(manifest_files)} manifest files to merge")
    
    # Merge all manifests
    combined_record_ids = []
    combined_household_ids = []
    search_terms = []
    data_volume = tier
    
    for manifest_file in manifest_files:
        print(f"  Processing: {manifest_file}")
        with open(manifest_file, "r") as f:
            manifest = json.load(f)
            
            combined_record_ids.extend(manifest.get("record_ids", []))
            combined_household_ids.extend(manifest.get("household_ids", []))
            
            search_terms.extend(manifest.get("search_terms") or [])
            
            # Validate data volume matches
            if manifest.get("data_volume") != data_volume:
                print(f"Warning: Data volume mismatch in {manifest_file}")
    
    # Remove duplicates (if any)
    combined_record_ids = list(set(combined_record_ids))
    combined_household_ids = list(set(combined_household_ids))
    search_terms = sorted(set(search_terms))
    
    # Create combined manifest
    combined_manifest = {
        "record_ids": combined_record_ids,
        "search_terms": search_terms,
        "household_ids": combined_household_ids,
        "data_volume": data_volume,
        "total_pods": total_pods,
        "merged_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Write combined manifest
    output_file = os.path.join(output_dir, f"seed_manifest_{tier}_combined.json")
    with open(output_file, "w") as f:
        json.dump(combined_manifest, f, indent=2)
    
    print(f"\nCombined manifest written to: {output_file}")
    print(f"  Total record_ids: {len(combined_record_ids)}")
    print(f"  Total household_ids: {len(combined_household_ids)}")
    print(f"  Total search_terms: {len(search_terms)}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge seed manifests from multiple pods"
    )
    parser.add_argument(
        "--tier",
        required=True,
        help="Data volume tier"
    )
    parser.add_argument(
        "--pods",
        type=int,
        required=True,
        help="Number of pods that were used"
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory containing manifest files"
    )
    
    args = parser.parse_args()
    
    merge_manifests(args.tier, args.pods, args.output_dir)


if __name__ == "__main__":
    main()
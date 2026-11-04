#!/usr/bin/env python3
"""Test disjoint functional_record_id blocks across pods."""

import sys

sys.path.insert(0, ".")

from id_scheme import assign_functional_id, init_pod_id_scheme


def test_id_allocation(total_farmers: int, total_pods: int, samples: int = 5000):
    print(f"Testing ID blocks: {total_farmers} farmers, {total_pods} pods, {samples} samples/pod")
    farmer_ids: set[str] = set()
    household_ids: set[str] = set()
    default_ids: set[str] = set()

    for pod_index in range(total_pods):
        init_pod_id_scheme(pod_index, total_pods, total_farmers)
        pod_farmers = [assign_functional_id("Farmer") for _ in range(samples)]
        pod_households = [assign_functional_id("Household") for _ in range(samples)]
        pod_defaults = [assign_functional_id("Crop") for _ in range(samples)]

        if len(set(pod_farmers)) != samples:
            print(f"ERROR: duplicate Farmer ids inside pod {pod_index}")
            return False
        overlap_f = farmer_ids.intersection(pod_farmers)
        overlap_h = household_ids.intersection(pod_households)
        overlap_d = default_ids.intersection(pod_defaults)
        if overlap_f or overlap_h or overlap_d:
            print(f"ERROR: cross-pod collision pod={pod_index} f={len(overlap_f)} h={len(overlap_h)} d={len(overlap_d)}")
            return False
        farmer_ids.update(pod_farmers)
        household_ids.update(pod_households)
        default_ids.update(pod_defaults)
        print(
            f"  pod {pod_index}: Farmer {pod_farmers[0]}..{pod_farmers[-1]} "
            f"Household {pod_households[0]}..{pod_households[-1]} "
            f"DEFAULT {pod_defaults[0]}..{pod_defaults[-1]}"
        )

    print(
        f"OK: {len(farmer_ids)} farmer / {len(household_ids)} household / "
        f"{len(default_ids)} default ids, no collisions"
    )
    return True


if __name__ == "__main__":
    ok = test_id_allocation(50_000_000, 5)
    sys.exit(0 if ok else 1)

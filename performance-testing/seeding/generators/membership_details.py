"""Generates g2p_register_membership_details rows. Links to a Farmer."""

import random

from common import base_register_fields, fake, join_search_text

FARMER_CLUSTER_ROLES = ["LEAD", "DEPUTY", "SECRETARY", "ACCOUNTANT", "MEMBER"]

SEARCH_TEXT_FIELDS = ["primary_cooperative_name", "cooperative_union_name", "farmer_cluster_role"]


def generate(farmer_row: dict) -> dict:
    row = base_register_fields()
    row["link_internal_record_id"] = farmer_row["internal_record_id"]

    is_primary = random.random() < 0.6
    is_union = random.random() < 0.3
    is_cluster = random.random() < 0.4
    primary_cooperative_name = f"{fake.city()} Farmers Cooperative" if is_primary else None
    cooperative_union_name = f"{fake.city()} Union" if is_union else None

    row.update({
        "is_primary_cooperative_member": is_primary,
        "primary_cooperative_name": primary_cooperative_name,
        "is_cooperative_union_member": is_union,
        "cooperative_union_name": cooperative_union_name,
        "is_farmer_cluster_member": is_cluster,
        "farmer_cluster_role": random.choice(FARMER_CLUSTER_ROLES) if is_cluster else None,
    })

    row["record_name"] = " ".join(
        p for p in (primary_cooperative_name, cooperative_union_name) if p
    ).strip() or None
    row["search_text"] = join_search_text(row, SEARCH_TEXT_FIELDS)
    return row

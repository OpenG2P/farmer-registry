"""Generates g2p_register_farm_inputs rows. Links to a Farmer."""

import random

from common import base_register_fields, join_search_text

WATER_SOURCES = ["RAINFED", "IRRIGATION_GW", "IRRIGATION_SURFACE", "WELL", "WATER_HARVESTING", "SURFACE_WATER"]

SEARCH_TEXT_FIELDS = ["water_source"]


def generate(farmer_row: dict) -> dict:
    row = base_register_fields()
    row["link_internal_record_id"] = farmer_row["internal_record_id"]

    water_source = random.choice(WATER_SOURCES)
    row.update({
        "fertilizer_use": random.random() < 0.6,
        "pesticide_use": random.random() < 0.4,
        "insecticide_use": random.random() < 0.3,
        "improved_seed_use": random.random() < 0.5,
        "water_source": water_source,
        "access_to_machinery": random.random() < 0.3,
        "access_to_finance": random.random() < 0.35,
    })

    row["record_name"] = water_source
    row["search_text"] = join_search_text(row, SEARCH_TEXT_FIELDS)
    return row

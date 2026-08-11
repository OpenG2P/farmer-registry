"""Generates g2p_register_lands rows. Links to a Farmer."""

import random

from common import base_register_fields, join_search_text, random_geo

LAND_OWNERSHIP_TYPES = ["OWNER", "TENANT", "CROP_SHARE"]
LAND_SIZE_UNITS = ["HECTARE", "ACRE", "SQUARE_METER", "SQUARE_KM", "SQUARE_FOOT", "SQUARE_YARD"]
CURRENT_LAND_USES = ["AGRICULTURAL", "RESIDENTIAL", "GRAZING", "FOREST"]
FARMING_TYPES = ["CROP", "LIVESTOCK", "MIXED", "AQUACULTURE", "AGROFORESTRY"]
SHAPE_TYPES = ["POINT", "POLYGON"]

SEARCH_TEXT_FIELDS = [
    "land_ownership_type", "land_size", "unit", "current_land_use",
    "farming_type", "means_of_acquisition", "latitude", "longitude",
    "altitude", "plus_code", "address_line_1", "address_line_2",
    "postal_code", "country_code", "shape_type",
]


def generate(farmer_row: dict) -> dict:
    row = base_register_fields()
    row["link_internal_record_id"] = farmer_row["internal_record_id"]

    row.update(random_geo())
    current_land_use = random.choice(CURRENT_LAND_USES)
    land_size = str(round(random.uniform(0.5, 20.0), 2))
    unit = random.choice(LAND_SIZE_UNITS)
    row.update({
        "land_ownership_type": random.choice(LAND_OWNERSHIP_TYPES),
        "certificate_storage_id": None,
        "land_size": land_size,
        "unit": unit,
        "soil_fertility": random.choice(["LOW", "MEDIUM", "HIGH"]),
        "current_land_use": current_land_use,
        "farming_type": random.choice(FARMING_TYPES),
        "year_of_acquisition": random.randint(1980, 2025),
        "means_of_acquisition": random.choice(["INHERITED", "PURCHASED", "LEASED", "GOVERNMENT_ALLOCATION"]),
        "shape_type": random.choice(SHAPE_TYPES),
        "shape_coordinates_json": None,
    })

    row["record_name"] = " ".join(
        p for p in (land_size, unit, current_land_use) if p
    ).strip() or None
    row["search_text"] = join_search_text(row, SEARCH_TEXT_FIELDS)
    return row

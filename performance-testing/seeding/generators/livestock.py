"""Generates g2p_register_livestocks rows. Links to a Farmer."""

import random

from common import base_register_fields, join_search_text

# livestock_type/breed are attribute-lookup fields in the app; these are
# plausible seed values, not a fixed enum.
LIVESTOCK_TYPES = {
    "CATTLE": ["BORAN", "FRIESIAN", "ZEBU", "ANKOLE"],
    "GOAT": ["BOER", "GALLA", "TOGGENBURG"],
    "SHEEP": ["DORPER", "MERINO", "RED_MAASAI"],
    "POULTRY": ["KIENYEJI", "BROILER", "LAYER"],
    "PIG": ["LARGE_WHITE", "LANDRACE"],
}
LIVESTOCK_SYSTEMS = ["NOMADIC_PASTORAL", "SEMI_NOMADIC", "SEDENTARY_PASTORAL", "MIXED", "INDUSTRIAL"]

SEARCH_TEXT_FIELDS = ["livestock_type", "breed", "head_count", "livestock_system"]


def generate(farmer_row: dict) -> dict:
    row = base_register_fields()
    row["link_internal_record_id"] = farmer_row["internal_record_id"]

    livestock_type = random.choice(list(LIVESTOCK_TYPES))
    breed = random.choice(LIVESTOCK_TYPES[livestock_type])
    row.update({
        "livestock_type": livestock_type,
        "breed": breed,
        "head_count": random.randint(1, 50),
        "livestock_system": random.choice(LIVESTOCK_SYSTEMS),
    })

    row["record_name"] = " ".join(p for p in (livestock_type, breed) if p).strip() or None
    row["search_text"] = join_search_text(row, SEARCH_TEXT_FIELDS)
    return row

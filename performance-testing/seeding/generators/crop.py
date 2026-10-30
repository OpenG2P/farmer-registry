"""Generates g2p_register_crops rows. Links to a Land."""

import random

from common import base_register_fields, fake, join_search_text

# commodity is an attribute-lookup field in the app (configured per
# deployment), not a fixed enum -- this list is just plausible seed content.
COMMODITIES = ["MAIZE", "WHEAT", "RICE", "BEANS", "CASSAVA", "SORGHUM", "MILLET", "COFFEE", "TEA", "COTTON"]
SEASONS = ["LONG_RAINS", "SHORT_RAINS", "DRY_SEASON"]
END_USES = ["FOOD_HUMAN_CONSUMPTION", "FEED_ANIMALS", "BIOFUELS_NONFOOD", "OTHER"]

SEARCH_TEXT_FIELDS = ["commodity", "season", "end_use"]


def generate(land_row: dict) -> dict:
    row = base_register_fields()
    row["link_internal_record_id"] = land_row["internal_record_id"]

    commodity = random.choice(COMMODITIES)
    season = random.choice(SEASONS)
    row.update({
        "commodity": commodity,
        "planted_date": fake.date_between(start_date="-2y", end_date="today"),
        "season": season,
        "end_use": random.choice(END_USES),
    })

    row["record_name"] = " ".join(p for p in (commodity, season) if p).strip() or None
    row["search_text"] = join_search_text(row, SEARCH_TEXT_FIELDS)
    return row

"""Generates g2p_register_household_members rows. Links to a Household."""

import random

from common import base_register_fields, join_search_text, random_geo, random_person_fields

SEARCH_TEXT_FIELDS = [
    "first_name", "last_name", "foundational_id", "middle_name", "given_name",
    "gender", "birth_date", "marital_status", "occupation", "education_level",
    "latitude", "longitude", "altitude", "plus_code", "address_line_1",
    "address_line_2", "postal_code", "country_code", "is_disabled",
]


def generate(household_row: dict) -> dict:
    row = base_register_fields()
    row["link_internal_record_id"] = household_row["internal_record_id"]

    row.update(random_person_fields())
    row.update(random_geo())
    row["is_disabled"] = random.random() < 0.08

    row["record_name"] = " ".join(
        p for p in (row["first_name"], row["last_name"]) if p
    ).strip() or None
    row["search_text"] = join_search_text(row, SEARCH_TEXT_FIELDS)
    return row

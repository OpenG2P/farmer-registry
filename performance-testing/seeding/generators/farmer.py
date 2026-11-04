"""Generates g2p_register_farmers rows.

Every row's first_name has one search anchor spliced in (search_anchors.py),
assigned round-robin across the fixed anchor pool -- see README.md
"Search-text anchors" for why. search_text is built from the *reduced* field
list agreed for the perf-testing dataset (config.FARMER_SEARCH_TEXT_FIELDS),
not the production construct_search_text()'s full ~22-field list.
"""

import random

from common import base_register_fields, fake, join_search_text, random_geo, random_person_fields
from config import FARMER_SEARCH_TEXT_FIELDS
from id_scheme import assign_functional_id
from search_anchors import embed_anchor, next_anchor

DISABILITY_TYPES = ["VISION", "HEARING", "MOBILITY", "COGNITION", "SELF_CARE", "COMMUNICATION"]
DISABILITY_SEVERITIES = ["NO_DIFFICULTY", "SOME_DIFFICULTY", "A_LOT_OF_DIFFICULTY", "CANNOT_DO_AT_ALL"]
SOURCES_OF_INCOME = ["CROP_PRODUCTION", "LIVESTOCK_PRODUCTION", "GOVERNMENT_NGO_SUPPORT", "OTHERS"]
LANGUAGES_SPOKEN = ["ENGLISH", "HINDI", "SPANISH", "FRENCH"]

REGISTER_MNEMONIC = "Farmer"


def generate(household_row: dict, anchors: list[str]) -> dict:
    row = base_register_fields()
    row["functional_record_id"] = assign_functional_id(REGISTER_MNEMONIC)
    row["link_internal_record_id"] = household_row["internal_record_id"]

    row.update(random_person_fields())
    row["first_name"] = embed_anchor(row["first_name"], next_anchor(anchors))
    row.update(random_geo())

    disabled = random.random() < 0.1
    row.update({
        "estimated_age": random.randint(18, 85),
        "has_personal_phone": random.random() < 0.7,
        "disabled": disabled,
        "disability_type": random.choice(DISABILITY_TYPES) if disabled else None,
        "disability_severity": random.choice(DISABILITY_SEVERITIES) if disabled else None,
        "source_of_income": random.choice(SOURCES_OF_INCOME),
        "source_of_income_other": None,
        "language_spoken": random.choice(LANGUAGES_SPOKEN),
        "national_id_masked": fake.numerify("***###" + "####"),
    })

    row["record_name"] = " ".join(
        p for p in (row["first_name"], row["last_name"]) if p
    ).strip() or None
    row["search_text"] = join_search_text(row, FARMER_SEARCH_TEXT_FIELDS)
    return row

"""Generates g2p_register_households rows. Root of the generation DAG --
every Farmer links up to one Household via link_internal_record_id.

search_text/record_name field lists mirror the real
G2PRegisterDomainServiceHousehold (construct_search_text/construct_record_name)
unchanged -- only Farmer's list was trimmed per the perf-testing decision.
"""

import random

from common import base_register_fields, fake, join_search_text, random_geo
from id_scheme import assign_functional_id

SEARCH_TEXT_FIELDS = [
    "functional_record_id", "record_name", "household_head",
    "latitude", "longitude", "altitude", "plus_code",
    "address_line_1", "address_line_2", "postal_code", "country_code",
]

REGISTER_MNEMONIC = "Household"


def generate() -> dict:
    row = base_register_fields()
    row["functional_record_id"] = assign_functional_id(REGISTER_MNEMONIC)

    household_head = fake.name()
    female = random.randint(0, 3)
    male = random.randint(0, 3)
    children = random.randint(0, min(4, female + male))

    row.update(random_geo())
    row.update({
        "household_head": household_head,
        "size_of_group": female + male,
        "number_of_children": children,
        "number_of_female_members": female,
        "number_of_male_members": male,
        "other_land_owner": random.random() < 0.15,
    })

    row["record_name"] = " ".join(
        p for p in (household_head, row["functional_record_id"]) if p
    ).strip() or None
    row["search_text"] = join_search_text(row, SEARCH_TEXT_FIELDS)
    return row

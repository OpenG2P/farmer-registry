"""Section metadata + payload construction for the farmer_ingestion_intake flow.

Kept separate from intake_create_locustfile.py so the business logic of
building section payloads and randomizing one attribute per invocation can be
read (and tested) independently of the actual HTTP calls.

Section order/section_id come dynamically from
`/intake-form-metadata/render_intake_form` at run time (filtered to one
tab_id). What that endpoint does NOT return — section_register_id, and a
sensible "standard" payload per section — is fixed seed data (from
g2p_register_sections.sql / the G2PFarmer* ORM models), so it's hardcoded
here the same way REGISTER_FARMER is hardcoded in shared/config.py.
"""
from __future__ import annotations

import copy
import random
from datetime import date
from typing import Any, Optional

from shared.config import HOUSEHOLD_IDS, REGISTER_FARMER, SEARCH_TERMS

HOUSEHOLD_LOOKUP_SECTION_ID = "farmer_household_lookup_section_01"
PERSONAL_IDENTIFICATION_SECTION_ID = "farmer_farmer_personal_identification_section_01"

BIRTH_DATE = "1990-01-01"

FIRST_NAMES = ["Amina", "Fatuma", "Hana", "Tigist", "Selam", "Abebe", "Kebede", "Meron", "Almaz", "Girma"]
MIDDLE_NAMES = ["", "Alemu", "Tesfaye", "Worku", "Getachew"]
LAST_NAMES = ["Bekele", "Alemu", "Tesfaye", "Worku", "Girma", "Haile", "Desta", "Kebede"]


def _age_from_birth_date(birth_date: str) -> int:
    born = date.fromisoformat(birth_date)
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _embed_search_term(base_name: str) -> str:
    """Splices a random seed_manifest.json search_term into base_name at a
    random position -- mirrors performance-testing/seeding/search_anchors.py
    embed_anchor(), so intake-created farmers are findable by the same
    anchors cr_read_and_approve/intake_read_and_approve/register_read search
    for. Unlike seeding's round-robin assignment (spreading a fixed farmer
    count evenly across anchors), each call here picks independently at
    random -- there's no fixed total to spread evenly over a live run.
    """
    anchor = random.choice(SEARCH_TERMS)
    position = random.randint(0, len(base_name))
    return base_name[:position] + anchor + base_name[position:]


def _random_name() -> tuple[str, str, str]:
    first_name = _embed_search_term(random.choice(FIRST_NAMES))
    return first_name, random.choice(MIDDLE_NAMES), random.choice(LAST_NAMES)

# section_register_id + a standard (baseline) payload per section, keyed by
# the section_id returned by get_all_sections. `is_list` sections still get a
# single-record list — enough to exercise the write path in a load test.
SECTION_DEFS: dict[str, dict[str, Any]] = {
    HOUSEHOLD_LOOKUP_SECTION_ID: {
        "section_register_id": REGISTER_FARMER,
        "is_list": False,
        "standard_payload": {
            "link_internal_record_id": "",
        },
    },
    PERSONAL_IDENTIFICATION_SECTION_ID: {
        "section_register_id": REGISTER_FARMER,
        "is_list": False,
        "standard_payload": {
            "first_name": "Amina",
            "middle_name": "",
            "last_name": "Bekele",
            "birth_date": BIRTH_DATE,
            "estimated_age": _age_from_birth_date(BIRTH_DATE),
            "gender": "FEMALE",
            "marital_status": "MARRIED",
            "education_level": "BASIC",
        },
    },
    "farmer_farmer_socio_economic_and_health_section_04": {
        "section_register_id": REGISTER_FARMER,
        "is_list": False,
        "standard_payload": {
            "disabled": False,
            "disability_type": "VISION",
            "disability_severity": "NO_DIFFICULTY",
            "source_of_income": "CROP_PRODUCTION",
            "has_personal_phone": True,
            "source_of_income_other": "",
            "language_spoken": "ENGLISH",
        },
    },
    "farmer_farmer_location_section_03": {
        "section_register_id": REGISTER_FARMER,
        "is_list": False,
        "standard_payload": {
            "address_line_1": "Kebele 05, House 12",
            "postal_code": "1000",
            "country_code": "ET",
            "region": "Oromia",
            "district": "Adama",
            "locality": "Adama Town",
            "latitude": "8.54",
            "longitude": "39.27",
            "altitude": "1712",
        },
    },
    "farmer_farm_farm_details_section_01": {
        "section_register_id": "493153d5-07ef-4743-8efd-07f4099772b9",
        "is_list": True,
        "standard_payload": {
            "land_ownership_type": "OWNER",
            "certificate_storage_id": "",
            "land_size": "2.5",
            "unit": "HECTARE",
            "soil_fertility": "MEDIUM",
            "current_land_use": "AGRICULTURAL",
            "farming_type": "CROP",
            "year_of_acquisition": 2015,
            "means_of_acquisition": "INHERITANCE",
        },
    },
    "farmer_crop_crop_details_section_01": {
        "section_register_id": "5fa096f8-ffdc-4b0a-ab16-9ca386c23310",
        "is_list": True,
        "standard_payload": {
            "commodity": "MAIZE",
            "planted_date": "2026-03-01",
            "season": "KHARIF",
            "end_use": "FOOD_HUMAN_CONSUMPTION",
        },
    },
    "farmer_farm_input_farm_input_details_section_01": {
        "section_register_id": "18df8370-3e9a-493f-aa27-fc1b9e05629c",
        "is_list": True,
        "standard_payload": {
            "fertilizer_use": True,
            "pesticide_use": False,
            "insecticide_use": False,
            "improved_seed_use": True,
            "access_to_machinery": False,
            "access_to_finance": True,
            "water_source": "RAINFED",
        },
    },
    "farmer_membership_membership_details_01": {
        "section_register_id": "495f251c-83a5-4025-a307-1925712c9d0b",
        "is_list": False,
        "standard_payload": {
            "is_primary_cooperative_member": True,
            "primary_cooperative_name": "Adama Farmers Cooperative",
            "is_cooperative_union_member": False,
            "cooperative_union_name": "",
            "is_farmer_cluster_member": False,
            "farmer_cluster_role": "",
        },
    },
    "farmer_livestock_livestock_details_section_01": {
        "section_register_id": "4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb",
        "is_list": True,
        "standard_payload": {
            "livestock_type": "CATTLE",
            "breed": "LOCAL",
            "head_count": 3,
            "livestock_system": "MIXED",
        },
    },
}

# One of these 9 attributes is randomized per invocation; everything else in
# its section keeps the standard_payload value. Maps attribute -> (owning
# section_id, random-value generator).
RANDOMIZABLE_ATTRIBUTES: dict[str, tuple[str, "Any"]] = {
    # birth_date stays fixed at BIRTH_DATE, and the platform requires
    # estimated_age to be consistent with birth_date within one year, so the
    # randomized value must stay within that window rather than picking any
    # age independently.
    "estimated_age": (
        "farmer_farmer_personal_identification_section_01",
        lambda: _age_from_birth_date(BIRTH_DATE) + random.choice([-1, 0, 1]),
    ),
    "education_level": (
        "farmer_farmer_personal_identification_section_01",
        lambda: random.choice(["ILLITERATE", "CAN_READ_AND_WRITE", "BASIC", "INTERMEDIARY", "HIGHER_EDUCATION"]),
    ),
    "has_personal_phone": (
        "farmer_farmer_socio_economic_and_health_section_04",
        lambda: random.choice([True, False]),
    ),
    "disabled": (
        "farmer_farmer_socio_economic_and_health_section_04",
        lambda: random.choice([True, False]),
    ),
    "disability_type": (
        "farmer_farmer_socio_economic_and_health_section_04",
        lambda: random.choice(["VISION", "HEARING", "MOBILITY", "COGNITION", "SELF_CARE", "COMMUNICATION"]),
    ),
    "disability_severity": (
        "farmer_farmer_socio_economic_and_health_section_04",
        lambda: random.choice(["NO_DIFFICULTY", "SOME_DIFFICULTY", "A_LOT_OF_DIFFICULTY", "CANNOT_DO_AT_ALL"]),
    ),
    "source_of_income": (
        "farmer_farmer_socio_economic_and_health_section_04",
        lambda: random.choice(["CROP_PRODUCTION", "LIVESTOCK_PRODUCTION", "GOVERNMENT_NGO_SUPPORT", "OTHERS"]),
    ),
    "source_of_income_other": (
        "farmer_farmer_socio_economic_and_health_section_04",
        lambda: random.choice(["Remittances", "Small trade", "Casual labor", "Handicrafts"]),
    ),
    "language_spoken": (
        "farmer_farmer_socio_economic_and_health_section_04",
        lambda: random.choice(["ENGLISH", "HINDI", "SPANISH", "FRENCH"]),
    ),
}


def choose_random_attribute_override() -> tuple[str, str, Any]:
    """Pick one of the 9 randomizable attributes and a random value for it.

    Returns (attribute_name, owning_section_id, value).
    """
    attribute_name = random.choice(list(RANDOMIZABLE_ATTRIBUTES.keys()))
    section_id, value_factory = RANDOMIZABLE_ATTRIBUTES[attribute_name]
    return attribute_name, section_id, value_factory()


def build_section_payload(
    section_id: str, attribute_name: str, section_with_override: str, value: Any, household_id: str
) -> dict:
    """This section's own fields, with the chosen attribute override applied if it's this section's turn.

    Does not include fields carried over from other sections — see
    merge_with_accumulated for that.
    """
    payload = copy.deepcopy(SECTION_DEFS[section_id]["standard_payload"])
    if section_id == section_with_override:
        payload[attribute_name] = value
    if section_id == HOUSEHOLD_LOOKUP_SECTION_ID:
        payload["link_internal_record_id"] = household_id
    if section_id == PERSONAL_IDENTIFICATION_SECTION_ID:
        payload["first_name"], payload["middle_name"], payload["last_name"] = _random_name()
    return payload


def merge_with_accumulated(section_register_id: str, own_payload: dict, accumulated_by_register: dict) -> dict:
    """Merge this section's own fields on top of everything already saved for its shared register row.

    farmer_household_lookup_section_01, farmer_farmer_personal_identification_section_01,
    farmer_farmer_socio_economic_and_health_section_04, and farmer_farmer_location_section_03
    all have section_register_id == REGISTER_FARMER — one underlying row. The save endpoint
    does not preserve a section's fields when a later section on the same row is saved
    without them, so each call must resend the full accumulated field set for that row, not
    just its own fields. accumulated_by_register is mutated so later sections in the same
    invocation see this section's fields too.
    """
    merged = {**accumulated_by_register.get(section_register_id, {}), **own_payload}
    accumulated_by_register[section_register_id] = merged
    return merged


def choose_household_id() -> str:
    """Pick one Household internal_record_id at random, for one invocation's household lookup."""
    return random.choice(HOUSEHOLD_IDS)


def extract_tab_sections(render_response_json: dict, tab_id: str) -> list[dict]:
    """This tab's sections, sorted ascending by section_order, from render_intake_form.

    Each section dict is IntakeFormRenderedSectionData -- it inherits
    G2PRegisterSectionData, so section_id/documents_required/etc. all come
    from this one call; no separate register-section-metadata lookup needed.
    """
    payload = (render_response_json or {}).get("response_body", {}).get("response_payload") or {}
    tabs = payload.get("tabs") or []
    tab = next((t for t in tabs if t.get("tab_id") == tab_id), None)
    if not tab:
        return []
    return sorted(tab.get("sections") or [], key=lambda section: section["section_order"])


def extract_submission_id(save_response_json: dict) -> Optional[str]:
    payload = (save_response_json or {}).get("response_body", {}).get("response_payload") or {}
    return payload.get("submission_id")


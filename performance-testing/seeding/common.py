"""Shared helpers for every generator: fields every G2PRegister table has
(internal_record_id, created_by, timestamps, record_status, ...), plus the
search_text join logic all tables use.

These fields are normally populated by SQLAlchemy ORM defaults/event
listeners (see README.md: "Why search_text is generator-computed"). Bulk
COPY bypasses the ORM entirely, so every generator sets them explicitly here.
"""

import random
import uuid
from datetime import datetime, timedelta

from faker import Faker

from config import RANDOM_SEED

random.seed(RANDOM_SEED)
fake = Faker()
Faker.seed(RANDOM_SEED)

STAFF_USERS = [f"staff-{i}@openg2p.org" for i in range(1, 21)]


def new_internal_record_id() -> str:
    return str(uuid.uuid4())


def past_datetime(max_days_ago: int = 730) -> datetime:
    return datetime.now() - timedelta(
        days=random.randint(0, max_days_ago),
        seconds=random.randint(0, 86_400),
    )


# Keys returned by base_register_fields() plus search_text -- i.e. every
# column that lives on G2PRegister itself. Everything else in a generated
# row dict is domain-specific (G2PPerson/G2PGeo/table-specific fields) and,
# per the model definitions, has the *same column name* on the live table
# and its *_history twin. generators/history.py uses this split to copy
# domain fields across unchanged while remapping the base fields (which do
# NOT share names/shape with G2PRegisterHistory).
BASE_FIELD_KEYS = {
    "internal_record_id", "functional_record_id", "link_internal_record_id",
    "link_foundational_id", "record_name", "record_image_document_id",
    "created_by", "created_at", "last_approved_at", "last_approved_by",
    "search_text", "record_status", "record_status_reason",
}


def base_register_fields() -> dict:
    created_at = past_datetime()
    return {
        "internal_record_id": new_internal_record_id(),
        "functional_record_id": None,  # filled by id_scheme.assign_functional_id
        "link_internal_record_id": None,  # filled by caller once parent is known
        "link_foundational_id": None,
        "record_name": None,  # filled by caller from name/label fields
        "record_image_document_id": None,
        "created_by": random.choice(STAFF_USERS),
        "created_at": created_at,
        "last_approved_at": created_at,
        "last_approved_by": random.choice(STAFF_USERS),
        "search_text": None,  # filled by caller via join_search_text
        "record_status": "ACTIVE",
        "record_status_reason": None,
    }


def join_search_text(row: dict, fields: list[str]) -> str | None:
    parts = (str(row.get(key) or "").strip() for key in fields)
    joined = " ".join(part for part in parts if part).strip()
    return joined or None


# Mirrors of the real StrEnum values (registry-platform .../models/enum.py,
# farmer-extension .../models/enums.py). Hardcoded rather than imported so
# this generator has no runtime dependency on either app package being
# installed. Keep in sync if those enums change.
GENDERS = ["MALE", "FEMALE", "OTHERS", "UNKNOWN"]
MARITAL_STATUSES = ["SINGLE", "MARRIED", "DIVORCED", "WIDOWED", "SEPARATED", "UNKNOWN"]
EDUCATION_LEVELS = ["ILLITERATE", "CAN_READ_AND_WRITE", "BASIC", "INTERMEDIARY", "HIGHER_EDUCATION"]
LANGUAGES_SPOKEN = ["ENGLISH", "HINDI", "SPANISH", "FRENCH"]

GEO_COUNTRIES = ["KE", "UG", "TZ", "RW", "ET", "GH", "NG"]


def random_person_fields() -> dict:
    gender = random.choice(GENDERS)
    first_name = fake.first_name_male() if gender == "MALE" else fake.first_name_female()
    return {
        # Not globally unique on purpose (no unique constraint on this
        # column, and fake.unique's in-memory tracking doesn't scale to
        # 100M rows) -- a 10-digit space also leaves room for the odd
        # collision, which is realistic fodder for dedup-endpoint testing.
        "foundational_id": fake.numerify("NID##########"),
        "first_name": first_name,
        "middle_name": fake.first_name() if random.random() < 0.3 else None,
        "last_name": fake.last_name(),
        "given_name": None,
        "prefix": None,
        "suffix": None,
        "gender": gender,
        "birth_date": fake.date_of_birth(minimum_age=18, maximum_age=85),
        "phone_numbers": [fake.msisdn()],
        "emails": None,
        "marital_status": random.choice(MARITAL_STATUSES),
        "occupation": "Farmer",
        "income_level": None,
        "language_code": "en",
        "education_level": random.choice(EDUCATION_LEVELS),
        "registration_date": fake.date_between(start_date="-5y", end_date="today"),
    }


def random_geo() -> dict:
    return {
        "latitude": str(round(random.uniform(-4.0, 15.0), 6)),
        "longitude": str(round(random.uniform(29.0, 41.0), 6)),
        "altitude": str(random.randint(0, 2500)),
        "plus_code": fake.bothify("????+???").upper(),
        "address_line_1": fake.street_address(),
        "address_line_2": fake.secondary_address(),
        "postal_code": fake.postcode(),
        "country_code": random.choice(GEO_COUNTRIES),
        # geo_lowest_level_value_id / geo_code_hierarchy_json intentionally
        # left unset: in the app these are populated by an ORM @validates
        # hook that calls out to master-data-db per write, which bulk
        # seeding does not replicate. See README "Known simplifications".
    }

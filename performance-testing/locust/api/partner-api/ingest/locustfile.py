"""Partner ingest performance case.

POST /partner/ingest_data?data_model=IMPORT_FARMER_CSV

A request passes when response_header.response_status is SUCCESS.
Each call uses a new message id and foundational id so rows do not collide.
The ingest signature check is still commented out in the service. The
signature field is present because the model reads it from the JSON.
"""

from __future__ import annotations

import logging
import os
import random
import uuid
from datetime import date, timedelta

from locust import HttpUser, constant, tag, task
from shared.slo_shape import SLOStepRampShape

_log = logging.getLogger("locust")


class PartnerIngestRampShape(SLOStepRampShape):
    """4 users, then +4 every 30s. Stop adding users when a step's successful
    RPS does not rise. Also freeze at 1.85 cores or p99 over 1000ms for two
    windows. Then soak at the last user count that still raised RPS."""

    warmup_users = 4
    freeze_when_rps_flat = True

HOST = os.environ.get(
    "PARTNER_API_BASE",
    "https://partner-farmer-registry.perftest.openg2p.org",
)
DATA_MODEL = os.environ.get("INGEST_DATA_MODEL", "IMPORT_FARMER_CSV")

# Enums and other coded attributes stay fixed. Names, dates, ids, and
# addresses change on every request.
FIRST = [
    "Adam", "Meera", "Ravi", "Asha", "Joseph", "Priya", "Omar", "Leila",
    "Anita", "Bhavna", "Chandra", "Deepak", "Esha", "Farid", "Gita", "Hari",
    "Indira", "Jamal", "Kavita", "Lakshmi", "Mohan", "Nalini", "Omkar", "Padma",
    "Qasim", "Rekha", "Sanjay", "Tara", "Uma", "Vikram", "Wasim", "Yasmin",
]
LAST = [
    "Woods", "Brown", "Sharma", "Khan", "Patel", "Singh", "Nguyen", "Diallo",
    "Iyer", "Reddy", "Nair", "Gupta", "Joshi", "Mehta", "Das", "Rao",
    "Kumar", "Devi", "Ali", "Hassan", "Owusu", "Mensah", "Abebe", "Bekele",
]
MIDDLES = ["", "Kumar", "Devi", "Lal", "Bai", "Singh", "Raj", ""]
STREETS = ["Farm Road", "Canal Lane", "Market Street", "Tank Bund", "Field Path", "Well Road"]
PLACES = ["Sikar", "Jaipur", "Pune", "Nairobi", "Kampala", "Dhaka", "Accra", "Lusaka"]


def _digits(length: int) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def _birth() -> str:
    day = date(1950, 1, 1) + timedelta(days=random.randint(0, 20000))
    return day.isoformat()


def farmer_body() -> dict:
    message_id = uuid.uuid4().hex
    first = random.choice(FIRST)
    middle = random.choice(MIDDLES)
    last = random.choice(LAST)
    member_first = random.choice(FIRST)
    place = random.choice(PLACES)
    street = random.choice(STREETS)
    house_no = random.randint(1, 400)
    postal = _digits(6)
    foundational_id = _digits(16)
    address = f"{house_no} {street}"
    return {
        "headers": {
            "message_id": message_id,
            "sender_id": "Staff Portal",
            "signature": "test",
        },
        "body": {
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "gender": "MALE",
            "marital_status": "MARRIED",
            "birth_date": _birth(),
            "estimated_age": None,
            "foundational_id": foundational_id,
            "education_level": "BASIC",
            "has_personal_phone": True,
            "disabled": False,
            "disability_type": "",
            "disability_severity": "",
            "source_of_income": "SOI_CROP_PRODUCTION",
            "source_of_income_other": "",
            "language_spoken": "ENGLISH",
            "national_id_masked": foundational_id,
            "address_line_1": address,
            "address_line_2": "",
            "locality": place,
            "postal_code": postal,
            "country_code": "IN",
            "latitude": None,
            "longitude": None,
            "registration_date": "2026-09-20",
            "household": {
                "household_head": f"{first} {last}",
                "size_of_group": 3,
                "number_of_children": 1,
                "number_of_female_members": 1,
                "number_of_male_members": 2,
                "other_land_owner": False,
                "address_line_1": address,
                "locality": place,
                "postal_code": postal,
                "country_code": "IN",
                "household_member": [
                    {
                        "first_name": member_first,
                        "last_name": last,
                        "gender": "FEMALE",
                        "birth_date": _birth(),
                        "is_disabled": False,
                        "foundational_id": _digits(16),
                    }
                ],
                "score": [{"score_type": "POVERTY", "computed_score": 1.35}],
            },
            "membership_details": {
                "is_primary_cooperative_member": True,
                "primary_cooperative_name": "Raghunath Producer Group",
                "is_cooperative_union_member": False,
                "cooperative_union_name": None,
                "is_farmer_cluster_member": True,
                "farmer_cluster_role": "LEAD",
            },
            "land": [
                {
                    "record_name": f"Land Plot {house_no}",
                    "land_ownership_type": "OWNER",
                    "land_size": f"{random.uniform(0.4, 5.0):.2f}",
                    "unit": "HECTARE",
                    "soil_fertility": "MEDIUM",
                    "current_land_use": "AGRICULTURAL",
                    "farming_type": "MIXED",
                    "year_of_acquisition": 2014,
                    "means_of_acquisition": "INHERITANCE",
                    "address_line_1": address,
                    "locality": place,
                    "postal_code": postal,
                    "country_code": "IN",
                    "crop": [
                        {
                            "commodity": "WHEAT",
                            "season": "WINTER",
                            "planted_date": "2025-11-10",
                            "end_use": "FOOD_HUMAN_CONSUMPTION",
                        }
                    ],
                    "livestock": [
                        {
                            "livestock_type": "GOAT",
                            "breed": "IMPROVED",
                            "head_count": random.randint(1, 40),
                            "livestock_system": "SEMI_NOMADIC",
                        }
                    ],
                    "farm_inputs": [
                        {
                            "fertilizer_use": True,
                            "pesticide_use": False,
                            "insecticide_use": False,
                            "improved_seed_use": True,
                            "water_source": "GROUNDWATER",
                            "access_to_machinery": True,
                            "access_to_finance": False,
                        }
                    ],
                }
            ],
        },
    }


class PartnerIngestUser(HttpUser):
    host = HOST
    wait_time = constant(0)

    @tag("ingest")
    @task
    def ingest_farmer(self):
        with self.client.post(
            f"/partner/ingest_data?data_model={DATA_MODEL}",
            json=farmer_body(),
            name="ingest",
            catch_response=True,
        ) as response:
            _log.info("ingest %s %s", response.status_code, response.text)
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                payload = response.json()
            except ValueError:
                response.failure("response is not JSON")
                return
            if payload.get("errors"):
                response.failure(str(payload["errors"])[:300])
                return
            status = ((payload.get("response_header") or {}).get("response_status"))
            if status != "SUCCESS":
                header = payload.get("response_header") or {}
                response.failure(
                    f"status={status} {header.get('response_error_code')} {header.get('response_error_message')}"
                )

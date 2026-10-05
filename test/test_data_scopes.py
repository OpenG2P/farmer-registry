"""The Farmer Registry's data scope catalogue (meta_data/data-scopes/) against its models and sections.

Publishes the shipped catalogue with the registry platform's data scope service
on a disposable PostgreSQL loaded with this extension's register definitions and
sections, then renders a farmer record filtered to a consent's scopes through
the outgoing DCI template. Skipped when the registry platform is not installed
or no database is reachable:

    docker run -d --name fr-pg -e POSTGRES_PASSWORD=postgres -p 55432:5432 postgres:16
    docker exec fr-pg psql -U postgres -c "create database fr_test"
    FR_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/fr_test pytest test/test_data_scopes.py
"""

import asyncio
import importlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("openg2p_registry_core")

EXTENSION = Path(__file__).resolve().parents[1] / "farmer-extension/src/openg2p_registry_farmer_extension"
META = EXTENSION / "meta_data"
DB_URL = os.environ.get("FR_TEST_DB_URL", "postgresql+asyncpg://postgres:postgres@localhost:55432/fr_test")
CONTROLLER = "farmer-registry"

EXPECTED_SCOPES = {
    "farmer_identifiers", "personal_details", "contact", "location", "main_crops", "socio_economic_and_health",
    "land", "land_location", "livestock", "farm_inputs", "memberships", "household", "household_location",
    "household_members", "poverty_score",
}

# The sample use case's Farmer Registry grant (Open Agri Stack composite, loan-profile).
LOAN_PROFILE_GRANT = [
    "farmer_identifiers", "personal_details", "household_location", "land", "land_location", "main_crops"]

FARMER = {
    "internal_record_id": "i-1", "functional_record_id": "FR-000000000123", "foundational_id": "1234567890123456",
    "first_name": "Abebe", "middle_name": "K", "last_name": "Bekele", "gender": "MALE", "birth_date": "1980-01-01",
    "phone_numbers": [{"number": "+251911000000"}], "has_personal_phone": True, "disabled": True,
    "disability_type": "VISUAL", "main_crops": ["CROP_TEFF"], "latitude": 9.1, "longitude": 38.7,
    "land": [{"internal_record_id": "l-1", "functional_record_id": "LAND-1-1", "land_size": 1.5, "unit": "H",
              "land_ownership_type": "OWNER", "latitude": 9.2, "longitude": 38.8,
              "livestock": [{"livestock_type": "CATTLE", "head_count": 3}]}],
    "household": {"internal_record_id": "h-1", "functional_record_id": "HH-1", "address_line_2": "Sheno",
                  "latitude": 9.3, "longitude": 38.9, "size_of_group": 5,
                  "household_member": [{"first_name": "Almaz", "last_name": "Bekele", "gender": "FEMALE"}],
                  "score": [{"score_type": "poverty", "computed_score": 42}]},
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def published():
    sys.modules["openg2p_registry_extensions"] = importlib.import_module("openg2p_registry_farmer_extension")
    sys.modules["openg2p_registry_extensions.register_domain.models"] = importlib.import_module(
        "openg2p_registry_farmer_extension.register_domain.models")
    from openg2p_fastapi_common.context import dbengine
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from openg2p_registry_core.config import Settings
    from openg2p_registry_core.models import (
        G2PDataScope, G2PDataScopeVersion, G2PRegisterDefinition, G2PRegisterSection,
    )
    from openg2p_registry_core.services import G2PDataScopeService

    async def prepare():
        engine = create_async_engine(DB_URL)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
        except Exception:
            await engine.dispose()
            return None
        dbengine.set(engine)
        for model in (G2PRegisterDefinition, G2PRegisterSection, G2PDataScope, G2PDataScopeVersion):
            await model.create_migrate()
        async with engine.begin() as conn:
            raw = (await conn.get_raw_connection()).driver_connection  # asyncpg: multi-statement like psql
            for name in ("g2p_register_definitions.sql", "g2p_register_sections.sql"):
                await raw.execute((META / "register-metadata" / name).read_text())
        return engine

    config = Settings.get_config(strict=False)
    saved = (config.consent_data_controller, config.data_scopes_catalogue_path)
    loop = asyncio.new_event_loop()
    engine = loop.run_until_complete(prepare())
    if engine is None:
        pytest.skip(f"PostgreSQL not reachable at {DB_URL}")
    config.consent_data_controller = CONTROLLER
    config.data_scopes_catalogue_path = ""  # the extension's own meta_data/data-scopes
    service = G2PDataScopeService()
    loop.run_until_complete(service.ensure_guards())
    outcome = loop.run_until_complete(service.sync())
    try:
        yield loop, service, outcome
    finally:
        config.consent_data_controller, config.data_scopes_catalogue_path = saved
        loop.run_until_complete(engine.dispose())
        loop.close()


def test_the_catalogue_publishes_against_the_farmer_models_and_sections(published):
    loop, service, outcome = published
    assert service.catalogue_dir() == META / "data-scopes"
    # Only the named scopes: no default one-per-section scopes (headers, documents,
    # ID authentication, intake-only and duplicate Household sections are not shared).
    assert outcome == {name: "created" for name in EXPECTED_SCOPES}
    listed = {s["scope_id"]: s for s in loop.run_until_complete(service.list_scopes())}
    assert set(listed) == {f"{CONTROLLER}.{name}" for name in EXPECTED_SCOPES}

    def fields(name):
        return set(listed[f"{CONTROLLER}.{name}"]["versions"][-1]["resolved_fields"])

    # The farmer ID another registry looks the farmer up by is in its own small scope.
    assert "Farmer.functional_record_id" in fields("farmer_identifiers")
    assert {"Farmer.first_name", "Farmer.last_name", "Farmer.birth_date"} <= fields("personal_details")
    assert "Farmer.phone_numbers" in fields("contact")
    assert not any("phone" in f for f in fields("personal_details"))
    assert not any(f.startswith("Land.") and "lat" in f for f in fields("land"))
    assert "Score.*" in fields("poverty_score")
    assert set(loop.run_until_complete(service.sync()).values()) == {"unchanged"}


def test_a_farmer_record_renders_only_the_consented_scopes(published):
    loop, service, _ = published
    from openg2p_registry_core.helpers.template_helper import template_environment

    allowed = loop.run_until_complete(service.resolve(
        [f"{CONTROLLER}.{name}" for name in LOAN_PROFILE_GRANT], datetime.utcnow() + timedelta(seconds=1)))
    nested = loop.run_until_complete(service.nested_keys())
    filtered = allowed.filter_register_record(FARMER, "Farmer", nested)
    template = template_environment().from_string((EXTENSION / "templates/openg2p_farmer_to_dci.json.j2").read_text())
    record = json.loads(template.render(expanded=filtered))
    rendered = json.dumps(record)

    # What the loan-profile use case maps: the Farmer ID (the Crop Sown Registry
    # query reads it), name, sex, birth date, household place, parcels, main crops.
    person = record["farmer_personal_details"]
    identifiers = {i["identifier_type"]: i["identifier_value"] for i in person["member_identifier"]}
    assert identifiers == {"UIN": "1234567890123456", "FARMER_ID": "FR-000000000123"}
    assert person["demographic_info"]["name"]["given_name"] == "Abebe"
    assert person["demographic_info"]["sex"] == "male" and person["demographic_info"]["birth_date"] == "1980-01-01"
    assert record["family_details"]["place"]["name"] == "Sheno"
    assert record["family_details"]["place"]["geo"]["latitude"] == 9.3
    assert record["main_crops"] == ["CROP_TEFF"]
    [parcel] = record["farm_details"]
    assert parcel["land_size"] == 1.5 and parcel["land_tenure"] == "Owned"
    assert parcel["place"]["geo"]["latitude"] == 9.2

    # Not consented: contact, disability, household members, poverty score, livestock.
    assert "+251911000000" not in rendered and "VISUAL" not in rendered
    assert record["family_details"]["member_list"] == [] and record["family_details"]["poverty_score"] is None
    assert parcel["farming_activities"][0]["animal_production"] == []

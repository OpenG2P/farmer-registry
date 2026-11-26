"""The sample herds: the country pack's sample animals (openg2p-data samples/animals.json), counted per herd.

The Livestock Registry loads the same file one animal at a time, so the two
registries must agree on every sample farmer's livestock. Needs openg2p-data
beside this repository (or OPENG2P_DATA_DIR) and psycopg2 (the loader imports it):

    OPENG2P_DATA_DIR=../openg2p-data pytest test/test_sample_herds.py
"""

import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LOADER = REPO / "docker/db-seed/load_sample_data.py"
DATA = Path(os.environ.get("OPENG2P_DATA_DIR") or REPO.parent / "openg2p-data")
PACK = DATA / "packs" / "ETH"


def _loader():
    pytest.importorskip("psycopg2", reason="the loader imports psycopg2 (pip install psycopg2-binary)")
    spec = importlib.util.spec_from_file_location("fr_load_sample_data", LOADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _codes(attribute_id: str) -> set:
    for path in (PACK / "domains").glob("*/*.json"):
        doc = json.loads(path.read_text())
        if doc.get("attribute_id") == attribute_id:
            return {v["value_id"] for v in doc["values"]}
    raise AssertionError(f"{attribute_id} is not in the ETH pack")


@pytest.fixture(scope="module")
def pack():
    if not (PACK / "samples" / "animals.json").is_file():
        pytest.skip("openg2p-data with samples/animals.json is not beside this repo (set OPENG2P_DATA_DIR)")
    people = json.loads((PACK / "samples" / "individuals.json").read_text())
    animals = json.loads((PACK / "samples" / "animals.json").read_text())
    return people, animals


def _herds(loader, people, animals):
    ind_by_id = {p["individual_id"]: {"internal_record_id": p["individual_id"],
                                      "functional_record_id": p["individual_id"]} for p in people}
    # Each person's lands, numbered as number_sample_lands numbers them.
    lands = [{"internal_record_id": f"land-{p}-{k}", "functional_record_id": f"LAND-{p[-4:]}-{k}",
              "link_internal_record_id": p} for p in ind_by_id for k in (1, 2, 11)]
    return loader.sample_herds(animals, ind_by_id, lands)


def test_herds_count_the_livestock_registrys_animals(pack):
    loader = _loader()
    people, animals = pack
    herds = _herds(loader, people, animals)
    # Per farmer and species, the herds' head count is the number of the farmer's animals.
    by_herd = Counter()
    for h in herds:
        owner = "ETH-IND-" + h["functional_record_id"].split("-")[1]
        by_herd[(owner, h["livestock_type"])] += h["head_count"]
    assert by_herd == Counter((a["owner_individual_id"], a["species"]) for a in animals)
    assert sum(h["head_count"] for h in herds) == len(animals)
    # Every herd is on its owner's first land, with a unique fixed ID.
    for h in herds:
        number = h["functional_record_id"].split("-")[1]
        assert h["link_internal_record_id"] == f"land-ETH-IND-{number}-1"
    assert len({h["functional_record_id"] for h in herds}) == len(herds)
    assert len({h["internal_record_id"] for h in herds}) == len(herds)


def test_herds_use_master_datas_codes(pack):
    loader = _loader()
    people, animals = pack
    herds = _herds(loader, people, animals)
    assert {h["livestock_type"] for h in herds} <= _codes("LIVESTOCK_TYPE")
    assert {h["breed"] for h in herds} <= _codes("LIVESTOCK_BREED")
    assert {h["livestock_system"] for h in herds} <= _codes("LIVESTOCK_SYSTEM")
    assert all(h["record_name"] and h["record_name"][0].isupper() for h in herds)


def test_an_owner_master_data_does_not_hold_is_refused(pack):
    loader = _loader()
    people, animals = pack
    with pytest.raises(loader.SampleDataError, match="not one of Master Data's sample people"):
        _herds(loader, [p for p in people if p["individual_id"] != animals[0]["owner_individual_id"]], animals)


def test_bulk_livestock_uses_master_datas_codes():
    """The bulk generator's invented herds also carry the lists' codes, not labels."""
    if not PACK.is_dir():
        pytest.skip("openg2p-data is not beside this repo (set OPENG2P_DATA_DIR)")
    import ast

    source = (REPO / "docker/db-seed/generate_fr_bulk_sample.py").read_text()
    consts = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(source).body
              if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
              and n.targets[0].id in ("LIVESTOCK_TYPE", "LIVESTOCK_BREED", "LIVESTOCK_SYSTEM")}
    assert {c for c, _ in consts["LIVESTOCK_TYPE"]} <= _codes("LIVESTOCK_TYPE")
    assert set(consts["LIVESTOCK_BREED"]) <= _codes("LIVESTOCK_BREED")
    assert {c for c, _ in consts["LIVESTOCK_SYSTEM"]} <= _codes("LIVESTOCK_SYSTEM")

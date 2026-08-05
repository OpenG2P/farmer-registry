#!/usr/bin/env python3
"""Load sample data into the Farmer Registry Postgres.

Reads:
- /openg2p-data/demography/{individuals,households}.csv (shared core + geo)
- /seed/seed-data/*.json (farmer sub-tables, shipped in the db-seed image)

Mapping:
- every individual -> g2p_register_farmers (reuses the individual UUID)
- every individual with a household_id -> g2p_register_household_members
- households.csv -> g2p_register_households (farmer column set)
- lands/crops/livestocks/farm_inputs/membership_details -> respective tables
- scores.json -> g2p_register_scores
- completion-score computation queue seeded for Farmer + Household registers
"""

import csv
import json
import os
import sys
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json


def to_json(value):
    return None if value is None else Json(value)


SEEDER = "seeder"
CREATED_AT = "2026-04-01 00:00:00"

OPENG2P_DATA_DIR = Path(os.environ.get("OPENG2P_DATA_DIR", "/openg2p-data"))
DEMO_DIR = OPENG2P_DATA_DIR / "demography"
FARMER_DATA_DIR = Path(os.environ.get("FARMER_SEED_DATA_DIR", "/seed/seed-data"))

JSON_COLUMNS_INDIVIDUAL = {"phone_numbers"}
JSON_COLUMNS_HOUSEHOLD = set()

# Geo is carried in the seed files as plain names (country..village); the id the
# registry stores has to be derived from them.
#
# It is RESOLVED against master-data rather than computed, because only
# master-data knows what its own ids are. Seeded from a country pack — now the
# default — a unit's id is its P-code, so master-data holds "XK01010101" while
# the slug-path this used to compute, "kamuntu/jasiri/baraka/umani/bimaka",
# matches nothing. Nothing errors either: the names in geo_code_hierarchy_json
# still read correctly, so reports that unpack geo positionally look right, and
# the only symptom is that these records never appear on a map.
#
# Resolution walks the name chain through parent links rather than matching
# names globally, since a village name repeats under different wards.
#
# The slug-path remains as the fallback for when master-data is unreachable, is
# empty, or was seeded by the legacy loader (load_geo_data.py + geo.csv), whose
# ids ARE slug-paths. So this works against either style and never does worse
# than before; whichever path was taken is reported at the end.
GEO_LEVELS = ["country", "region", "district", "ward", "village"]


def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


# (parent_level_value_id or "", lowercased name) -> level_value_id, read once
# from master-data. Empty when master-data is unreachable or unseeded, which is
# what puts every lookup on the slug-path fallback.
_GEO_INDEX: dict = {}
_GEO_STATS = {"resolved": 0, "fallback": 0, "unresolved_examples": []}


def load_geo_index() -> dict:
    """Index master-data's units by (parent id, name) so a name chain resolves.

    Best effort on purpose. A missing MD_PG* env, an unreachable database or an
    empty table all mean the same thing here — no ids to resolve against — and
    none of them should stop sample data loading, which worked without any of
    this before.
    """
    host = os.environ.get("MD_PGHOST")
    dbname = os.environ.get("MD_PGDATABASE")
    if not host or not dbname:
        print("[load-sample-data] MD_PG* not set — geo ids fall back to slug-paths.")
        return {}
    try:
        conn = psycopg2.connect(
            host=host,
            port=os.environ.get("MD_PGPORT", "5432"),
            dbname=dbname,
            user=os.environ.get("MD_PGUSER", ""),
            password=os.environ.get("MD_PGPASSWORD", ""),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[load-sample-data] master-data unreachable ({exc}) — geo ids fall back to slug-paths.")
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select level_value_id, level_value_mnemonic, coalesce(parent_level_value_id, '')"
                "  from g2p_geo_level_values"
            )
            index = {(parent, name.strip().lower()): vid for vid, name, parent in cur.fetchall()}
    except Exception as exc:  # noqa: BLE001
        print(f"[load-sample-data] could not read master-data geo ({exc}) — slug-paths.")
        return {}
    finally:
        conn.close()
    print(f"[load-sample-data] master-data geo: {len(index)} units available for resolution.")
    return index


def load_geo_chain_by_id() -> dict:
    """level_value_id -> (level_mnemonic, name, parent_id), for walking upwards.

    This is what makes the loader country-agnostic. A record carries the id of
    the one unit it sits in; every level above it — and how many there are, and
    what they are called — is read from master-data rather than assumed. The
    five names this file used to hard-code, country/region/district/ward/village,
    describe Kamuntu and nothing else: Ethiopia has four levels and calls the
    middle ones zone and woreda.
    """
    host = os.environ.get("MD_PGHOST")
    dbname = os.environ.get("MD_PGDATABASE")
    if not host or not dbname:
        return {}
    try:
        conn = psycopg2.connect(
            host=host, port=os.environ.get("MD_PGPORT", "5432"), dbname=dbname,
            user=os.environ.get("MD_PGUSER", ""), password=os.environ.get("MD_PGPASSWORD", ""),
        )
    except Exception:  # noqa: BLE001
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute("select level_id, level_mnemonic from g2p_geo_levels")
            mnemonic = dict(cur.fetchall())
            cur.execute("select level_value_id, level_id, level_value_mnemonic,"
                        " parent_level_value_id from g2p_geo_level_values")
            return {
                vid: (mnemonic.get(lid, lid), name, parent)
                for vid, lid, name, parent in cur.fetchall()
            }
    except Exception:  # noqa: BLE001
        return {}
    finally:
        conn.close()


_GEO_BY_ID: dict = {}


def hierarchy_from_pcode(pcode: str) -> dict:
    """Walk a unit's ancestry in master-data, root first."""
    chain = []
    seen, cur = set(), pcode
    while cur and cur in _GEO_BY_ID and cur not in seen:
        seen.add(cur)
        level, name, parent = _GEO_BY_ID[cur]
        chain.append({"level_mnemonic": level, "level_value_mnemonic": name,
                      "level_value_id": cur})
        cur = parent
    chain.reverse()
    return {"hierarchy": chain}


def resolve_geo_chain(rec: dict) -> list:
    """Resolve country..village names to master-data's own ids, or [] if any
    link is missing. Partial resolution is deliberately not returned: half a
    chain produces a hierarchy whose upper levels join and whose lower ones do
    not, which is harder to notice than none of it joining."""
    if not _GEO_INDEX:
        return []
    ids, parent = [], ""
    for level in GEO_LEVELS:
        name = str(rec.get(level) or "").strip().lower()
        found = _GEO_INDEX.get((parent, name))
        if not found:
            return []
        ids.append(found)
        parent = found
    return ids


def geo_ids(rec: dict) -> list:
    """One id per level — master-data's where they resolve, slug-paths where not."""
    resolved = resolve_geo_chain(rec)
    if resolved:
        _GEO_STATS["resolved"] += 1
        return resolved
    _GEO_STATS["fallback"] += 1
    if len(_GEO_STATS["unresolved_examples"]) < 3:
        _GEO_STATS["unresolved_examples"].append(
            "/".join(str(rec.get(level) or "") for level in GEO_LEVELS)
        )
    return ["/".join(_slug(rec[GEO_LEVELS[i]]) for i in range(depth + 1))
            for depth in range(len(GEO_LEVELS))]


def geo_lowest_id(rec: dict) -> str:
    """The id of the record's lowest geo unit."""
    # A record sourced from master-data already knows exactly where it is; only
    # the CSV needs its names resolved.
    if rec.get("geo_pcode"):
        return rec["geo_pcode"]
    return geo_ids(rec)[-1]


def geo_hierarchy_dict(rec: dict) -> dict:
    """Build geo_code_hierarchy_json from the name columns, matching the shape
    registry-core's G2PGeoHierarchyService produces at runtime."""
    if rec.get("geo_pcode"):
        return hierarchy_from_pcode(rec["geo_pcode"])
    ids = geo_ids(rec)
    return {
        "hierarchy": [
            {
                "level_mnemonic": level,
                "level_value_mnemonic": rec[level],
                "level_value_id": ids[depth],
            }
            for depth, level in enumerate(GEO_LEVELS)
        ]
    }


def geo_hierarchy(rec: dict):
    return to_json(geo_hierarchy_dict(rec))


def _address_line(parts) -> str:
    """One line from the pack's address parts.

    The pack's address.json declares how a country composes these properly; that
    lives in master-data's country, not here, and sample data does not warrant
    fetching it. Joining the values keeps the information rather than inventing
    a street.
    """
    if not parts:
        return ""
    return ", ".join(str(v) for v in parts.values() if v)


def load_people_from_mds() -> tuple:
    """The country's sample people, from master-data.

    Returns (individuals, households) in the same dict shape the CSV produces,
    so every insert below is unchanged — or ([], []) when master-data carries no
    samples, which is its default.

    These people belong to the country, not to this registry: master-data is
    where the country is declared, so its samples are the ones that match the
    geography and the code lists. What a registry adds on top is its own fields.
    """
    host = os.environ.get("MD_PGHOST")
    dbname = os.environ.get("MD_PGDATABASE")
    if not host or not dbname:
        return [], []
    try:
        conn = psycopg2.connect(
            host=host, port=os.environ.get("MD_PGPORT", "5432"), dbname=dbname,
            user=os.environ.get("MD_PGUSER", ""), password=os.environ.get("MD_PGPASSWORD", ""),
        )
    except Exception:  # noqa: BLE001
        return [], []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for table in ("g2p_sample_individuals", "g2p_sample_households"):
                cur.execute("select to_regclass(%s)", (f"public.{table}",))
                if cur.fetchone()["to_regclass"] is None:
                    return [], []
            cur.execute("select * from g2p_sample_individuals order by individual_id")
            inds = [dict(r) for r in cur.fetchall()]
            cur.execute("select * from g2p_sample_households order by household_id")
            hhs = [dict(r) for r in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        print(f"[load-sample-data] could not read master-data samples ({exc}).")
        return [], []
    finally:
        conn.close()

    if not inds:
        return [], []

    head_of = {h["household_id"]: h.get("head_individual_id") for h in hhs}
    by_hh = {}
    for i in inds:
        by_hh.setdefault(i.get("household_id"), []).append(i)

    individuals = []
    for i in inds:
        # The registry's columns are first/middle/last. A pack that names people
        # as given name + father's name maps onto first + last; middle stays
        # empty rather than being filled with something the country does not use.
        individuals.append({
            "internal_record_id": i["individual_id"],
            "functional_record_id": i["individual_id"],
            "household_id": i.get("household_id"),
            "full_name": i.get("full_name"),
            "first_name": i.get("given_name"),
            "middle_name": None,
            "last_name": i.get("fathers_name"),
            "given_name": i.get("given_name"),
            "gender": i.get("gender"),
            # Only a birth year is carried; a made-up day and month would read as
            # a precision the sample does not have.
            "birth_date": f"{i['birth_year']}-01-01" if i.get("birth_year") else None,
            "estimated_age": i.get("age"),
            "marital_status": i.get("marital_status"),
            "education_level": i.get("education_level"),
            "foundational_id": i.get("national_id"),
            "foundational_id_masked": None,
            "phone_numbers": ([{"type": "personal", "number": i["phone"], "is_primary": True}]
                              if i.get("phone") else None),
            "emails": None,
            "language_code": None,
            "latitude": i.get("latitude"), "longitude": i.get("longitude"),
            "altitude": None, "plus_code": None,
            "address_line_1": _address_line(i.get("address_parts")),
            "address_line_2": "",
            "postal_code": None,
            "country_code": i.get("country"),
            "geo_pcode": i.get("geo_pcode"),
        })

    households = []
    for h in hhs:
        members = by_hh.get(h["household_id"], [])
        head = next((m for m in members if m["individual_id"] == head_of.get(h["household_id"])), None)
        adults = [m for m in members if (m.get("age") or 0) >= 18]
        households.append({
            "internal_record_id": h["household_id"],
            "functional_record_id": h["household_id"],
            # Registries differ in what they store about a household; supplying
            # the union costs nothing, since each takes only the keys it asks for.
            "head_individual_id": h.get("head_individual_id"),
            "headship_type": h.get("headship_type"),
            "size_adults": len(adults),
            "size_elderly": sum(1 for m in members if (m.get("age") or 0) >= 60),
            "head_name": (head or {}).get("full_name") or "",
            "size_total": h.get("size_total") or len(members),
            "size_children_u5": 0, "size_school_age": 0,
            "number_of_female_members": sum(1 for m in members if m.get("gender") == "FEMALE"),
            "number_of_male_members": sum(1 for m in members if m.get("gender") == "MALE"),
            "latitude": h.get("latitude"), "longitude": h.get("longitude"),
            "altitude": None, "plus_code": None,
            "address_line_1": _address_line(h.get("address_parts")),
            "address_line_2": "",
            "postal_code": None,
            "country_code": h.get("country"),
            "geo_pcode": h.get("geo_pcode"),
        })

    print(f"[load-sample-data] master-data samples: {len(individuals)} individuals, "
          f"{len(households)} households (country={inds[0].get('country')}).")
    return individuals, households


# ── Attaching the registry's own sample rows to the loaded people ───────────
#
# The sub-table fixtures (land, crops, housing, programmes, vulnerability) link
# to the id space of the demography CSV — i0001, h001. Once people come from
# master-data those ids are ETH-IND-0001 and ETH-HH-001, and every one of those
# rows links to a record that does not exist. Nothing errors: the insert has no
# foreign key to violate, so they land as orphans and the registry comes up with
# farmers who own no land and households with no housing data.
#
# So the links are remapped onto whoever was actually loaded.

_REMAP_STATS = {}


def build_link_remap(individuals: list, households: list, fixture_rows: dict) -> dict:
    """old link id -> loaded record id.

    Distinct old ids are mapped in sorted order onto the loaded records, cycling
    when there are fewer people than the fixtures assume — the country pack
    carries a couple of dozen samples where the CSV carried five hundred, and
    dropping the surplus would empty most of the form.

    Person ids and household ids are mapped separately: a row linking to a
    household must not be handed a person.
    """
    ind_ids = [i["internal_record_id"] for i in individuals]
    hh_ids = [h["internal_record_id"] for h in households]
    if not ind_ids and not hh_ids:
        return {}

    # Ids the fixtures define themselves. A crop links to its parcel, and a
    # parcel is a fixture row, not a person — remapping that link would move the
    # crop onto a farmer and lose the parcel. Only links pointing OUT of the
    # fixture set name people or households.
    fixture_own_ids = {
        r["internal_record_id"]
        for rows in fixture_rows.values()
        for r in rows
        if r.get("internal_record_id")
    }

    old_person, old_household = set(), set()
    for rows in fixture_rows.values():
        for r in rows:
            link = r.get("link_internal_record_id")
            if not link or link in fixture_own_ids:
                continue
            # The fixtures' own convention, and the only signal available for
            # the rest: an id starting 'h' is a household, anything else a person.
            (old_household if str(link).startswith("h") else old_person).add(link)

    # An id that already names a loaded record maps to itself. That makes this a
    # strict no-op on the CSV path, where the fixtures and the people share an id
    # space — rather than relying on the two happening to be in the same order.
    loaded = set(ind_ids) | set(hh_ids)
    remap = {}
    for old_set, new_ids in ((sorted(old_person), ind_ids), (sorted(old_household), hh_ids)):
        if not new_ids:
            continue
        unmatched = [o for o in old_set if o not in loaded]
        for old in old_set:
            if old in loaded:
                remap[old] = old
        for index, old in enumerate(unmatched):
            remap[old] = new_ids[index % len(new_ids)]
    return remap


def remap_links(table: str, rows: list, remap: dict) -> list:
    """Repoint a fixture's links, and collapse it to one row per record when it
    was one row per record to begin with.

    Cycling turns 500 links into 21, so a table carrying exactly one row per
    person — housing, vulnerability — would otherwise give each of them a
    couple of dozen. Whether a table is one-per-record is read from the fixture
    rather than configured: if every original link appeared once, it is.
    """
    if not remap:
        return rows
    links = [r.get("link_internal_record_id") for r in rows if r.get("link_internal_record_id")]
    one_per_record = links and len(set(links)) == len(links)

    out, seen, unresolved = [], set(), 0
    for r in rows:
        link = r.get("link_internal_record_id")
        if link in remap:
            r = dict(r, link_internal_record_id=remap[link])
            if one_per_record:
                if r["link_internal_record_id"] in seen:
                    continue
                seen.add(r["link_internal_record_id"])
        elif link:
            # Points at another sub-table row rather than a person — a crop's
            # parcel. Those ids are internal to the fixture and stay valid.
            unresolved += 1
        out.append(r)

    _REMAP_STATS[table] = (len(rows), len(out), unresolved)
    return out


def report_link_remap() -> None:
    if not _REMAP_STATS:
        return
    for table, (before, after, unresolved) in sorted(_REMAP_STATS.items()):
        note = f"{table}: {before} fixture row(s) -> {after} attached"
        if before != after:
            note += " (one row per record; surplus dropped)"
        if unresolved:
            note += f", {unresolved} linked within the fixture"
        print(f"[load-sample-data]   {note}")


def report_geo_resolution() -> None:
    resolved, fallback = _GEO_STATS["resolved"], _GEO_STATS["fallback"]
    if not (resolved or fallback):
        return
    print(f"[load-sample-data] geo ids: {resolved} resolved against master-data, "
          f"{fallback} fell back to slug-paths.")
    if fallback:
        # Never silent: a fallback id joins to nothing when master-data was
        # seeded from a pack, and the only symptom is an empty map.
        print("[load-sample-data]   unresolved name chains, e.g. "
              + "; ".join(_GEO_STATS["unresolved_examples"]))
        print("[load-sample-data]   those records will not join to a boundary. "
              "Check the sample data's place names match the loaded country pack.")


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"[load-sample-data] Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def load_json(path: Path):
    if not path.is_file():
        print(f"[load-sample-data] Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def _read_csv_rows(path: Path, json_columns: set) -> list:
    if not path.is_file():
        print(f"[load-sample-data] Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(newline="", encoding="utf-8") as f:
        out = []
        for row in csv.DictReader(f):
            parsed = {}
            for k, v in row.items():
                if v == "":
                    parsed[k] = None
                elif k in json_columns:
                    parsed[k] = json.loads(v)
                else:
                    parsed[k] = v
            out.append(parsed)
        return out


def _as_int(v):
    return int(v) if v not in (None, "") else None


def _fr_id(ind: dict) -> str:
    """Farmer functional id from the individual's id -> FR-####.

    Take the LAST segment, not [1]. The docstring's `IND-####` was only ever the
    two-segment shape; Master Data's sample population is country-prefixed
    (`ETH-IND-0001`), where [1] is the literal 'IND' — so every farmer got the
    same `FR-IND`. The insert only carries `ON CONFLICT (internal_record_id)`,
    which does not cover the unique index on functional_record_id, so the second
    row aborted the transaction: db-seed failed with zero rows loaded, retried,
    and failed identically until BackoffLimitExceeded.
    """
    return "FR-" + ind["functional_record_id"].rsplit("-", 1)[-1]


def search_text_person(p: dict) -> str:
    parts = [
        p["functional_record_id"], p["full_name"],
        p.get("foundational_id") or "", p.get("gender") or "",
        p.get("birth_date") or "", p.get("marital_status") or "",
    ]
    return " ".join(x for x in parts if x)


def insert_farmers(cur, individuals: list, extras_by_id: dict) -> None:
    columns = [
        "internal_record_id", "functional_record_id",
        "link_internal_record_id", "link_foundational_id",
        "record_name", "record_image_document_id",
        "created_by", "created_at", "last_approved_at", "last_approved_by",
        "search_text", "record_status", "record_status_reason",
        "foundational_id", "first_name", "middle_name", "last_name",
        "given_name", "prefix", "suffix", "gender", "birth_date",
        "phone_numbers", "emails", "marital_status", "occupation",
        "income_level", "language_code", "registration_date",
        "latitude", "longitude", "altitude", "plus_code",
        "address_line_1", "address_line_2", "postal_code", "country_code",
        "geo_lowest_level_value_id", "geo_code_hierarchy_json",
        "estimated_age", "has_personal_phone", "disabled",
        "disability_type", "disability_severity",
        "source_of_income", "source_of_income_other",
        "language_spoken", "education_level", "national_id_masked",
    ]
    rows = []
    for ind in individuals:
        ex = extras_by_id.get(ind["internal_record_id"], {})
        rows.append(
            (
                ind["internal_record_id"], _fr_id(ind),
                ind.get("household_id"), None,
                ind["full_name"], None,
                SEEDER, CREATED_AT, CREATED_AT, SEEDER,
                search_text_person(ind), "ACTIVE", None,
                ind.get("foundational_id"), ind["first_name"],
                ind.get("middle_name"), ind["last_name"], ind["given_name"],
                None, None, ind["gender"], ind["birth_date"],
                to_json(ind.get("phone_numbers")),
                to_json([{"type": "personal", "address": ind["emails"], "is_primary": True}]
                        if ind.get("emails") else None),
                ind["marital_status"], None, None,
                ind.get("language_code"), "2026-04-01",
                ind["latitude"], ind["longitude"], ind["altitude"], ind["plus_code"],
                ind["address_line_1"], ind["address_line_2"],
                ind["postal_code"], ind["country_code"],
                geo_lowest_id(ind), geo_hierarchy(ind),
                _as_int(ind.get("estimated_age")), ex.get("has_personal_phone"),
                ex.get("disabled"), ex.get("disability_type"),
                ex.get("disability_severity"), ex.get("source_of_income"),
                ex.get("source_of_income_other"), ex.get("language_spoken"),
                ind.get("education_level"), ind.get("foundational_id_masked"),
            )
        )
    sql = (
        'INSERT INTO "public"."g2p_register_farmers" ('
        + ", ".join(f'"{c}"' for c in columns)
        + ") VALUES %s ON CONFLICT (\"internal_record_id\") DO NOTHING"
    )
    psycopg2.extras.execute_values(cur, sql, rows, template=None, page_size=200)
    print(f"[load-sample-data]   -> g2p_register_farmers: {len(rows)}")


def insert_households(cur, households: list) -> None:
    columns = [
        "internal_record_id", "functional_record_id",
        "link_internal_record_id", "link_foundational_id",
        "record_name", "record_image_document_id",
        "created_by", "created_at", "last_approved_at", "last_approved_by",
        "search_text", "record_status", "record_status_reason",
        "latitude", "longitude", "altitude", "plus_code",
        "address_line_1", "address_line_2", "postal_code", "country_code",
        "geo_lowest_level_value_id", "geo_code_hierarchy_json",
        "household_head", "size_of_group", "number_of_children",
        "number_of_female_members", "number_of_male_members", "other_land_owner",
    ]
    rows = []
    for hh in households:
        num_children = (_as_int(hh.get("size_children_u5")) or 0) + (
            _as_int(hh.get("size_school_age")) or 0
        )
        other_land_owner = "TRUE" if _seq(hh) % 3 == 0 else "FALSE"
        rows.append(
            (
                hh["internal_record_id"], hh["functional_record_id"],
                None, None,
                f"{hh['head_name']} {hh['functional_record_id']}", None,
                SEEDER, CREATED_AT, CREATED_AT, SEEDER,
                f"{hh['functional_record_id']} {hh['head_name']}", "ACTIVE", None,
                hh["latitude"], hh["longitude"], hh["altitude"], hh["plus_code"],
                hh["address_line_1"], hh["address_line_2"],
                hh["postal_code"], hh["country_code"],
                geo_lowest_id(hh), geo_hierarchy(hh),
                hh["head_name"], _as_int(hh.get("size_total")), num_children,
                _as_int(hh.get("number_of_female_members")),
                _as_int(hh.get("number_of_male_members")), other_land_owner,
            )
        )
    sql = (
        'INSERT INTO "public"."g2p_register_households" ('
        + ", ".join(f'"{c}"' for c in columns)
        + ") VALUES %s ON CONFLICT (\"internal_record_id\") DO NOTHING"
    )
    psycopg2.extras.execute_values(cur, sql, rows, template=None, page_size=200)
    print(f"[load-sample-data]   -> g2p_register_households: {len(rows)}")


def _seq(record: dict) -> int:
    # Last segment, for the same reason as _fr_id: on a country-prefixed id
    # (`ETH-HH-001`) index [1] is 'HH' and int() raises. This is only reached
    # after the farmers insert, which is why _fr_id failed first.
    return int(record["functional_record_id"].rsplit("-", 1)[-1])


def insert_household_members(cur, members: list, ind_by_id: dict) -> None:
    columns = [
        "internal_record_id", "functional_record_id",
        "link_internal_record_id", "link_foundational_id",
        "record_name", "record_image_document_id",
        "created_by", "created_at", "last_approved_at", "last_approved_by",
        "search_text", "record_status", "record_status_reason",
        "foundational_id", "first_name", "middle_name", "last_name",
        "given_name", "prefix", "suffix", "gender", "birth_date",
        "phone_numbers", "emails", "marital_status", "occupation",
        "income_level", "language_code", "education_level", "registration_date",
        "latitude", "longitude", "altitude", "plus_code",
        "address_line_1", "address_line_2", "postal_code", "country_code",
        "geo_lowest_level_value_id", "geo_code_hierarchy_json", "is_disabled",
    ]
    rows = []
    for m in members:
        ind = ind_by_id[m["member_individual_id"]]
        rows.append(
            (
                m["internal_record_id"], m["functional_record_id"],
                m["link_internal_record_id"], None,
                ind["full_name"], None,
                SEEDER, CREATED_AT, CREATED_AT, SEEDER,
                search_text_person(ind), "ACTIVE", None,
                ind.get("foundational_id"), ind["first_name"],
                ind.get("middle_name"), ind["last_name"], ind["given_name"],
                None, None, ind["gender"], ind["birth_date"],
                to_json(ind.get("phone_numbers")),
                to_json([{"type": "personal", "address": ind["emails"], "is_primary": True}]
                        if ind.get("emails") else None),
                ind["marital_status"], None, None,
                ind.get("language_code"), ind.get("education_level"), "2026-04-01",
                ind["latitude"], ind["longitude"], ind["altitude"], ind["plus_code"],
                ind["address_line_1"], ind["address_line_2"],
                ind["postal_code"], ind["country_code"],
                geo_lowest_id(ind), geo_hierarchy(ind),
                m.get("is_disabled"),
            )
        )
    sql = (
        'INSERT INTO "public"."g2p_register_household_members" ('
        + ", ".join(f'"{c}"' for c in columns)
        + ") VALUES %s ON CONFLICT (\"internal_record_id\") DO NOTHING"
    )
    psycopg2.extras.execute_values(cur, sql, rows, template=None, page_size=200)
    print(f"[load-sample-data]   -> g2p_register_household_members: {len(rows)}")


COMMON_COLUMNS = [
    "internal_record_id", "functional_record_id",
    "link_internal_record_id", "link_foundational_id",
    "record_name", "record_image_document_id",
    "created_by", "created_at", "last_approved_at", "last_approved_by",
    "search_text", "record_status", "record_status_reason",
]

# (table, json_file, extra_cols, json_cols)
SUB_TABLES = [
    (
        "g2p_register_lands", "lands.json",
        [
            "land_ownership_type", "certificate_storage_id", "land_size", "unit",
            "soil_fertility", "current_land_use", "farming_type",
            "year_of_acquisition", "means_of_acquisition",
            "latitude", "longitude", "altitude", "plus_code",
            "address_line_1", "address_line_2", "postal_code", "country_code",
            "geo_lowest_level_value_id", "geo_code_hierarchy_json",
            "shape_type", "shape_coordinates_json",
        ],
        {"geo_code_hierarchy_json", "shape_coordinates_json"},
    ),
    (
        "g2p_register_crops", "crops.json",
        ["commodity", "planted_date", "season", "end_use"],
        set(),
    ),
    (
        "g2p_register_livestocks", "livestocks.json",
        ["livestock_type", "breed", "head_count", "livestock_system"],
        set(),
    ),
    (
        "g2p_register_farm_inputs", "farm_inputs.json",
        [
            "fertilizer_use", "pesticide_use", "insecticide_use",
            "improved_seed_use", "water_source",
            "access_to_machinery", "access_to_finance",
        ],
        set(),
    ),
    (
        "g2p_register_membership_details", "membership_details.json",
        [
            "is_primary_cooperative_member", "primary_cooperative_name",
            "is_cooperative_union_member", "cooperative_union_name",
            "is_farmer_cluster_member", "farmer_cluster_role",
        ],
        set(),
    ),
]


def insert_sub_table(cur, table: str, rows_json: list, extra_cols: list, json_cols: set) -> None:
    if not rows_json:
        print(f"[load-sample-data]   -> {table}: 0 (empty)")
        return
    columns = COMMON_COLUMNS + extra_cols
    rows = []
    for r in rows_json:
        common = [
            r["internal_record_id"], r["functional_record_id"],
            r["link_internal_record_id"], r.get("link_foundational_id"),
            r["record_name"],
            r.get("record_image_document_id") or r.get("record_image_storage_id"),
            r.get("created_by", SEEDER), r.get("created_at", CREATED_AT),
            r.get("last_approved_at", CREATED_AT), r.get("last_approved_by", SEEDER),
            r["search_text"], r.get("record_status", "ACTIVE"),
            r.get("record_status_reason"),
        ]
        extras = [
            to_json(r.get(c)) if c in json_cols else r.get(c) for c in extra_cols
        ]
        rows.append(tuple(common + extras))
    sql = (
        f'INSERT INTO "public"."{table}" ('
        + ", ".join(f'"{c}"' for c in columns)
        + ") VALUES %s ON CONFLICT (\"internal_record_id\") DO NOTHING"
    )
    psycopg2.extras.execute_values(cur, sql, rows, template=None, page_size=200)
    print(f"[load-sample-data]   -> {table}: {len(rows)}")


def insert_scores(cur, scores: list) -> None:
    if not scores:
        return
    columns = [
        "internal_record_id", "register_id", "score_type", "score_definition_id",
        "link_internal_record_id", "triggered_by_cr_id", "triggered_by_submission_id",
        "computed_score", "computed_at",
    ]
    rows = [tuple(r.get(c) for c in columns) for r in scores]
    sql = (
        'INSERT INTO "public"."g2p_register_scores" ('
        + ", ".join(f'"{c}"' for c in columns)
        + ") VALUES %s ON CONFLICT (\"internal_record_id\") DO NOTHING"
    )
    psycopg2.extras.execute_values(cur, sql, rows, template=None, page_size=200)
    print(f"[load-sample-data]   -> g2p_register_scores: {len(rows)}")


# Stable namespace so re-running the seed produces the same queue_id per
# (register, record, section) — with ON CONFLICT DO NOTHING this makes the
# completion-score enqueue idempotent.
_QUEUE_NS = uuid.UUID("a1b2c3d4-0000-4000-8000-000000000002")


def get_register_id(cur, mnemonic: str):
    cur.execute(
        'SELECT register_id FROM "public"."g2p_register_definitions" '
        "WHERE register_mnemonic = %s",
        (mnemonic,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def qualifying_sections(cur, register_id: str) -> list:
    """Own-register sections plus list sections, EXCLUDING sections backed by a
    CORE_TABLE register (e.g. Score). The completion-score worker resolves a
    section's model as G2PRegister<section_register_mnemonic> from the extensions
    register_domain.models; CORE_TABLE registers have no such generated model, so
    enqueuing them makes the worker fail."""
    cur.execute(
        "SELECT s.section_id, s.section_register_id, s.is_list, d.register_purpose "
        'FROM "public"."g2p_register_sections" s '
        'LEFT JOIN "public"."g2p_register_definitions" d '
        "  ON d.register_id = s.section_register_id "
        "WHERE s.register_id = %s",
        (register_id,),
    )
    out = []
    for section_id, section_register_id, is_list, purpose in cur.fetchall():
        if section_register_id != register_id and not is_list:
            continue
        if purpose == "CORE_TABLE":
            continue
        out.append(section_id)
    return out


def enqueue_completion_scores(cur, register_id: str, record_ids: list) -> None:
    if not register_id:
        print("[load-sample-data]   -> completion-score queue: register not found, skipped")
        return
    sections = qualifying_sections(cur, register_id)
    if not sections:
        print(f"[load-sample-data]   -> completion-score queue ({register_id}): no sections")
        return
    rows = []
    for rid in record_ids:
        for sid in sections:
            queue_id = str(uuid.uuid5(_QUEUE_NS, f"{register_id}:{rid}:{sid}"))
            rows.append((queue_id, register_id, rid, sid, None, None, "PENDING", 0))
    columns = [
        "queue_id", "register_id", "internal_record_id", "section_id",
        "change_request_id", "submission_id",
        "compute_status", "compute_number_of_attempts",
    ]
    sql = (
        'INSERT INTO "public"."g2p_completion_score_computation_queue" ('
        + ", ".join(f'"{c}"' for c in columns)
        + ") VALUES %s ON CONFLICT (queue_id) DO NOTHING"
    )
    psycopg2.extras.execute_values(cur, sql, rows, template=None, page_size=500)
    print(
        f"[load-sample-data]   -> completion-score queue: {len(rows)} rows "
        f"({len(record_ids)} records x {len(sections)} sections)"
    )


def main() -> None:
    print("[load-sample-data] Starting…")
    print(f"[load-sample-data] OPENG2P_DATA_DIR = {OPENG2P_DATA_DIR}")
    print(f"[load-sample-data] FARMER_SEED_DATA_DIR = {FARMER_DATA_DIR}")

    # Before anything derives a geo id. Read once; every record resolves
    # against this rather than reopening master-data per row.
    global _GEO_INDEX, _GEO_BY_ID
    _GEO_INDEX = load_geo_index()
    _GEO_BY_ID = load_geo_chain_by_id()

    # People come from master-data when it carries the country's samples. The
    # CSV is the fallback, and it can only ever describe the one country whose
    # five level names its columns happen to be — which is why it is no longer
    # the primary source.
    individuals, households = load_people_from_mds()
    if not individuals:
        print("[load-sample-data] no samples in master-data — falling back to the "
              "demography CSV. Enable geoSeed.load.samples for a pack-coherent set.")
        individuals = _read_csv_rows(DEMO_DIR / "individuals.csv", JSON_COLUMNS_INDIVIDUAL)
        households = _read_csv_rows(DEMO_DIR / "households.csv", JSON_COLUMNS_HOUSEHOLD)
    ind_by_id = {i["internal_record_id"]: i for i in individuals}

    farmer_extras = {f["internal_record_id"]: f for f in load_json(FARMER_DATA_DIR / "farmers.json")}
    members = load_json(FARMER_DATA_DIR / "household_members.json")

    conn = psycopg2.connect(
        host=env("PGHOST"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=env("PGDATABASE"),
        user=env("PGUSER"),
        password=env("PGPASSWORD"),
    )
    conn.autocommit = False
    cur = conn.cursor()

    # Read every fixture first: the remap has to see all the links before it can
    # assign them, or two tables referring to the same person would disagree.
    fixtures = {fname: load_json(FARMER_DATA_DIR / fname) for _, fname, _, _ in SUB_TABLES}
    fixtures["scores.json"] = load_json(FARMER_DATA_DIR / "scores.json")
    fixtures["household_members.json"] = members
    remap = build_link_remap(individuals, households, fixtures)
    if remap:
        print(f"[load-sample-data] attaching fixture rows to {len(set(remap.values()))} "
              f"loaded record(s) ({len(remap)} fixture id(s) remapped):")

    try:
        insert_farmers(cur, individuals, farmer_extras)
        insert_households(cur, households)
        insert_household_members(
            cur, remap_links("g2p_register_household_members", members, remap), ind_by_id)
        for table, fname, extras, json_cols in SUB_TABLES:
            rows = remap_links(table, fixtures[fname], remap)
            if table == "g2p_register_lands":
                # lands.json carries geo as plain names; derive the DB id + JSON.
                for r in rows:
                    r["geo_lowest_level_value_id"] = geo_lowest_id(r)
                    r["geo_code_hierarchy_json"] = geo_hierarchy_dict(r)
            insert_sub_table(cur, table, rows, extras, json_cols)
        insert_scores(cur, remap_links("g2p_register_scores", fixtures["scores.json"], remap))

        # Seed completion-score computation queue for Farmer + Household records.
        enqueue_completion_scores(
            cur, get_register_id(cur, "Farmer"),
            [ind["internal_record_id"] for ind in individuals],
        )
        enqueue_completion_scores(
            cur, get_register_id(cur, "Household"),
            [hh["internal_record_id"] for hh in households],
        )

        conn.commit()
        report_link_remap()
        report_geo_resolution()
        print("[load-sample-data] Done.")
    except Exception as exc:
        conn.rollback()
        print(f"[load-sample-data] FAILED: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

"""Generates a *_history twin row for every live record (1:1, see run.py's
TableSink.write_live).

G2PRegisterHistory does NOT share column names/shape with G2PRegister for
the register-level fields (e.g. last_approved_at/last_approved_by on the
live row become approved_at/approved_by on history, and history adds
tab_id/section_id/change_request_source that live rows don't have). It DOES
share column names for every domain-specific field (Person/Geo/table
attributes), since e.g. G2PRegisterHistoryFarmer mixes in the same G2PFarmer
class G2PRegisterFarmer does. See common.BASE_FIELD_KEYS for the split.

tab_id/section_id are real metadata rows loaded by the platform's db-seed
job (dbSeed.enabled=true), NOT invented here -- load_tab_sections() reads
them back so history rows reference valid (tab_id, section_id) pairs.

Only Household and Farmer are UI-navigable registers with their own tabs.
Every other table (HouseholdMember, Land, Crop, Livestock, FarmInputs,
MembershipDetails) is surfaced as a *section embedded in* Household's or
Farmer's tabs, not as a register with tabs of its own -- a
g2p_register_sections row for one of these has section_register_id pointing
at the child table's own register_id, while its (owning) register_id points
at whichever of Household/Farmer displays it. Filtering on
section_register_id therefore finds the right tab/section pair uniformly for
both top-level registers (where section_register_id == register_id, i.e. the
register's "own data" section) and child tables (where it doesn't).
"""

import random
import uuid

from common import BASE_FIELD_KEYS, past_datetime

CHANGE_REQUEST_SOURCES = ["STAFF_PORTAL", "INTAKE_FORM", "PARTNER", "AGENT_PORTAL"]


def load_tab_sections(cursor, register_mnemonic: str) -> list[tuple[str, str]]:
    cursor.execute(
        "SELECT register_id FROM g2p_register_definitions WHERE register_mnemonic = %s",
        (register_mnemonic,),
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(
            f"No g2p_register_definitions row for mnemonic={register_mnemonic!r}. "
            "Run the platform's db-seed job (register/schema/tab/section metadata) first."
        )
    register_id = row[0]
    cursor.execute(
        """
        SELECT ts.tab_id, s.section_id
          FROM g2p_register_sections s
          JOIN g2p_register_ui_tab_sections ts ON ts.section_id = s.section_id
         WHERE s.section_register_id = %s
        """,
        (register_id,),
    )
    pairs = cursor.fetchall()
    if not pairs:
        raise RuntimeError(
            f"No g2p_register_ui_tab_sections rows for register_id={register_id!r} "
            f"(mnemonic={register_mnemonic!r})."
        )
    return [(tab_id, section_id) for tab_id, section_id in pairs]


def generate(live_row: dict, tab_sections: list[tuple[str, str]]) -> dict:
    tab_id, section_id = random.choice(tab_sections)
    domain_fields = {k: v for k, v in live_row.items() if k not in BASE_FIELD_KEYS}

    history_created_at = past_datetime(max_days_ago=30)
    row = dict(domain_fields)
    row.update({
        "history_record_id": str(uuid.uuid4()),
        "internal_record_id": live_row["internal_record_id"],
        "tab_id": tab_id,
        "section_id": section_id,
        # Required non-null by RecordHistoryData/VersionForDateData
        # (registry-platform's schemas/register_payload.py) -- a fabricated
        # id, since we don't write a matching g2p_register_change_requests
        # row. One per history row, not shared, so get_number_of_versions'
        # unique-change-request-id count reflects the actual edit count.
        "change_request_id": str(uuid.uuid4()),
        "submission_id": None,
        "change_request_source": random.choice(CHANGE_REQUEST_SOURCES),
        "is_primary_section": random.random() < 0.3,
        "functional_record_id": live_row["functional_record_id"],
        "link_internal_record_id": live_row["link_internal_record_id"],
        "link_foundational_id": live_row["link_foundational_id"],
        "record_name": live_row["record_name"],
        "record_image_document_id": live_row["record_image_document_id"],
        "record_status": live_row["record_status"],
        "record_status_reason": live_row["record_status_reason"],
        "created_by": live_row["created_by"],
        "created_at": history_created_at,
        "approved_by": live_row["last_approved_by"],
        "approved_at": live_row["last_approved_at"],
    })
    return row

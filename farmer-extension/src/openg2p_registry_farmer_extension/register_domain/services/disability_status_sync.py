"""Set farmer.disabled from the disability table.

One or more stored rows means disabled. An empty table means not disabled.
Intake writes the intake farmer. Change-request approval and ingest write the
live farmer after the table rows are already stored.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger("g2p-farmer-disability-status-sync")


def _link_id(row) -> str:
    if isinstance(row, dict):
        value = row.get("link_internal_record_id")
    else:
        value = getattr(row, "link_internal_record_id", None)
    return str(value or "").strip()


def disabled_from_rows(rows: list | None) -> bool:
    """True when the table has one or more records."""
    return len(rows or []) > 0


def rows_for_farmer(farmer_id: str, farmer_count: int, rows: list | None) -> list:
    """Rows that belong to one farmer.

    A link match always counts. While the link is still empty, a submission
    with a single farmer owns those unlinked rows.
    """
    rows = rows or []
    linked = [row for row in rows if _link_id(row) == farmer_id]
    if farmer_count != 1:
        return linked
    unlinked = [row for row in rows if not _link_id(row)]
    return linked + unlinked


def parent_ids_for_disability_change(
    subject_internal_record_id: str | None,
    records: list[dict] | None,
) -> list[str]:
    """Parent farmers touched by a disability change request.

    The change request subject is the farmer. Table ADD rows also carry
    link_internal_record_id; UPDATE and DELETE often do not.
    """
    parent_ids: list[str] = []
    seen: set[str] = set()

    def add(value) -> None:
        if value is None:
            return
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        parent_ids.append(normalized)

    add(subject_internal_record_id)
    for record in records or []:
        add(record.get("link_internal_record_id"))
    return parent_ids


async def sync_intake_farmers_disabled(session: AsyncSession, submission_id: str) -> None:
    """Set each intake farmer's disabled flag from that submission's table."""
    from ..models.farmer import G2PIntakeFormFarmer
    from ..models.farmer_disability import G2PIntakeFormFarmerDisability

    farmers = (
        await session.execute(
            select(G2PIntakeFormFarmer).where(
                G2PIntakeFormFarmer.submission_id == str(submission_id)
            )
        )
    ).scalars().all()
    if not farmers:
        return

    rows = (
        await session.execute(
            select(G2PIntakeFormFarmerDisability).where(
                G2PIntakeFormFarmerDisability.submission_id == str(submission_id)
            )
        )
    ).scalars().all()

    for farmer in farmers:
        matched = rows_for_farmer(str(farmer.internal_record_id), len(farmers), rows)
        farmer.disabled = disabled_from_rows(matched)
        session.add(farmer)
    await session.flush()
    _logger.info(
        "Set disabled from %s intake disability row(s) for submission %s",
        len(rows),
        submission_id,
    )


async def sync_register_disabled_from_live_rows(
    session: AsyncSession,
    farmer_internal_record_id: str,
) -> bool | None:
    """Set the live farmer from disability rows still stored for that farmer.

    Called after a disability change request is applied, or after a disability
    row is ingested, so a delete of the last row is already gone.
    """
    from ..models.farmer import G2PRegisterFarmer
    from ..models.farmer_disability import G2PRegisterFarmerDisability

    farmer = await session.get(G2PRegisterFarmer, farmer_internal_record_id)
    if not farmer:
        _logger.info(
            "No live farmer %s; skipping disabled sync",
            farmer_internal_record_id,
        )
        return None

    await session.flush()
    rows = (
        await session.execute(
            select(G2PRegisterFarmerDisability).where(
                G2PRegisterFarmerDisability.link_internal_record_id
                == farmer_internal_record_id
            )
        )
    ).scalars().all()
    farmer.disabled = disabled_from_rows(rows)
    session.add(farmer)
    await session.flush()
    _logger.info(
        "Set disabled=%s for farmer %s from %s live disability row(s)",
        farmer.disabled,
        farmer_internal_record_id,
        len(rows),
    )
    return farmer.disabled

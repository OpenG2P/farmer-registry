"""Crops, livestock and farm inputs hang off a Land row.

The platform only checks that a table ADD carries *some* link_internal_record_id;
the staff UI falls back to the farmer's own id when no parent land was picked,
and the row is then saved pointing at the farmer. Reject anything that is not a
known land (register row, or intake row while the form is still a draft).
"""

from openg2p_fastapi_common.context import dbengine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .domain_validation_utils import is_blank, validation_error


async def validate_land_link(records: list[dict], child_label: str) -> None:
    link_ids = {
        str(record.get("link_internal_record_id")).strip()
        for record in records
        if not is_blank(record.get("link_internal_record_id"))
    }
    if not link_ids:
        return

    from ..models.land import G2PIntakeFormLand, G2PRegisterLand

    session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
    async with session_maker() as session:
        found = set(
            (
                await session.scalars(
                    select(G2PRegisterLand.internal_record_id).where(
                        G2PRegisterLand.internal_record_id.in_(link_ids)
                    )
                )
            ).all()
        )
        missing = link_ids - found
        if missing:
            found_intake = set(
                (
                    await session.scalars(
                        select(G2PIntakeFormLand.internal_record_id).where(
                            G2PIntakeFormLand.internal_record_id.in_(missing)
                        )
                    )
                ).all()
            )
            missing -= found_intake
    if missing:
        validation_error(
            f"{child_label} rows must be attached to one of the farmer's lands "
            "(select the land in the row); not a land: " + ", ".join(sorted(missing))
        )

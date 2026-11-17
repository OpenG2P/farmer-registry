import logging

from openg2p_registry_core.services import G2PRegisterDomainService
from sqlalchemy.ext.asyncio import AsyncSession

from .disability_status_sync import (
    parent_ids_for_disability_change,
    sync_register_disabled_from_live_rows,
)
from .domain_validation_utils import fallback_record_name, validate_enum_values, validation_error

_logger = logging.getLogger("g2p-register-farmerdisability-service")


def _enum_fields() -> dict:
    from ..models.enums import DisabilitySeverityEnum, DisabilityTypeEnum

    return {
        "disability_domains": DisabilityTypeEnum,
        "disability_severity": DisabilitySeverityEnum,
    }


class G2PRegisterDomainServiceFarmerDisability(G2PRegisterDomainService):
    async def post_ingest(self, register_id: str, register_row, session: AsyncSession):
        link_internal_record_id = getattr(register_row, "link_internal_record_id", None)
        if not link_internal_record_id:
            return
        await sync_register_disabled_from_live_rows(session, str(link_internal_record_id))

    async def post_approve(self, change_request, session: AsyncSession):
        from openg2p_registry_core.models import G2PRegisterChangeRequestPayload

        payload_obj = await session.get(
            G2PRegisterChangeRequestPayload, change_request.change_request_id
        )
        records = payload_obj.change_payload if payload_obj else []
        parent_ids = parent_ids_for_disability_change(
            change_request.internal_record_id, records
        )
        for parent_id in parent_ids:
            await sync_register_disabled_from_live_rows(session, parent_id)

    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            if record.get("edit_action") == "DELETE":
                continue
            validate_enum_values(record, _enum_fields())
        self._validate_no_duplicate_disability_domain(records)

    def _validate_no_duplicate_disability_domain(self, records: list[dict]) -> None:
        seen: set[tuple[str, str]] = set()
        for record in records:
            if record.get("edit_action") == "DELETE":
                continue
            value = record.get("disability_domains")
            if value is None or str(value).strip() == "":
                continue
            parent = str(record.get("link_internal_record_id") or "").strip()
            key = (parent, str(value).strip())
            if key in seen:
                validation_error("Duplicate disability domain entries are not allowed")
            seen.add(key)

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for farmer disability")

        keys = ["functional_record_id", "disability_domains", "disability_severity"]
        search_text = []
        if extra:
            search_text.extend(
                str(value).strip() for value in extra if str(value).strip()
            )
        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing record name for farmer disability")

        keys = ["disability_domains", "disability_severity"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Disability")

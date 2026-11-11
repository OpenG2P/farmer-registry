import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import fallback_record_name, validate_enum_values, validation_error

_logger = logging.getLogger("g2p-register-farmerdisability-service")


def _enum_fields() -> dict:
    from ..models.enums import DisabilitySeverityEnum, DisabilityTypeEnum

    return {
        "disability_domains": DisabilityTypeEnum,
        "disability_severity": DisabilitySeverityEnum,
    }


class G2PRegisterDomainServiceFarmerDisability(G2PRegisterDomainService):
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

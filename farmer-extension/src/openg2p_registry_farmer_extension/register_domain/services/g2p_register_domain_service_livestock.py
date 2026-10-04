import logging

from openg2p_registry_core.services import G2PRegisterDomainService


from .land_link_validation import validate_land_link

from .domain_validation_utils import fallback_record_name, validate_enum_values, validation_error

_logger = logging.getLogger("g2p-register-domain-service")



def _enum_fields() -> dict:
    # Imported lazily: ..models imports these services at module level, so a
    # top-level import here would be circular whenever services load first.
    from ..models.enums import LivestockSystemEnum

    return {"livestock_system": LivestockSystemEnum}


class G2PRegisterDomainServiceLivestock(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            validate_enum_values(record, _enum_fields())
        self._validate_no_duplicate_livestock_type(records)
        await validate_land_link(records, "Livestock")

    def _validate_no_duplicate_livestock_type(self, records: list[dict]) -> None:
        seen: set[str] = set()
        for record in records:
            value = record.get("livestock_type")
            if value is None or str(value).strip() == "":
                continue
            normalized = str(value).strip()
            if normalized in seen:
                validation_error("Duplicate livestock_type entries are not allowed")
            seen.add(normalized)

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for livestock")

        keys = [
            "livestock_type",
            "breed",
            "head_count",
            "livestock_system",
        ]
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
        _logger.info("Constructing record name for livestock")

        keys = ["livestock_type", "breed"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Livestock")

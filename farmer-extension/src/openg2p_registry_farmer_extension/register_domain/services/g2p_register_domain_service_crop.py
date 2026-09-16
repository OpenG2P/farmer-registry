import logging
from datetime import date

from openg2p_registry_core.services import G2PRegisterDomainService


from .land_link_validation import validate_land_link

from .domain_validation_utils import fallback_record_name, parse_date, validate_enum_values, validation_error

_logger = logging.getLogger("g2p-register-domain-service")



def _enum_fields() -> dict:
    # Imported lazily: ..models imports these services at module level, so a
    # top-level import here would be circular whenever services load first.
    from ..models.enums import CropEndUseEnum

    return {"end_use": CropEndUseEnum}


class G2PRegisterDomainServiceCrop(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_planted_date(record)
            validate_enum_values(record, _enum_fields())
        self._validate_no_duplicate_commodity(records)
        await validate_land_link(records, "Crop")

    def _validate_planted_date(self, record: dict) -> None:
        planted_date = parse_date(record.get("planted_date"))
        if planted_date is not None and planted_date > date.today():
            validation_error("planted_date must not be in the future")

    def _validate_no_duplicate_commodity(self, records: list[dict]) -> None:
        seen: set[str] = set()
        for record in records:
            value = record.get("commodity")
            if value is None or str(value).strip() == "":
                continue
            normalized = str(value).strip()
            if normalized in seen:
                validation_error("Duplicate commodity entries are not allowed")
            seen.add(normalized)

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for crop")

        keys = [
            "commodity",
            "season",
            "end_use",
        ]
        search_text = []
        if extra:
            search_text.extend(str(item).strip() for item in extra if str(item).strip())
        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing record name for crop")

        keys = ["commodity", "season"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Crop")

import logging
from datetime import date

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import as_float, as_int, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceLand(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_land_size(record)
            self._validate_year_of_acquisition(record)

    def _validate_land_size(self, record: dict) -> None:
        land_size = as_float(record.get("land_size"))
        if land_size is not None and land_size <= 0:
            validation_error("land_size must be greater than zero when provided")

    def _validate_year_of_acquisition(self, record: dict) -> None:
        year = as_int(record.get("year_of_acquisition"))
        if year is not None and year > date.today().year:
            validation_error("year_of_acquisition must not be in the future")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for land")

        keys = [
            "land_ownership_type",
            "land_size",
            "unit",
            "current_land_use",
            "farming_type",
            "means_of_acquisition",
            "latitude",
            "longitude",
            "altitude",
            "plus_code",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "country_code",
            "shape_type",
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
        _logger.info("Constructing record name for land")

        keys = ["land_size", "unit", "current_land_use"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()

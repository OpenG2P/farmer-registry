import logging

from openg2p_fastapi_common.context import dbengine
from openg2p_registry_core.services import G2PRegisterDomainService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .domain_validation_utils import as_bool, as_int, fallback_record_name, is_blank, validation_error

_logger = logging.getLogger("g2p-register-domain-service")

# Fields the household intake / change request cannot be saved without. The UI
# marks the same widgets required; this is the server-side guarantee.
_REQUIRED_FIELDS = {
    "size_of_group": "Size of Group",
    "number_of_male_members": "Number of Male Members",
    "number_of_female_members": "Number of Female Members",
    "other_land_owner": "Other Land Owner",
}


_INFO_FIELDS = (
    "size_of_group",
    "number_of_male_members",
    "number_of_female_members",
    "number_of_children",
    "number_of_elderly_members",
    "other_land_owner",
)


class G2PRegisterDomainServiceHousehold(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            # The household register has several sections (information,
            # location). Only a payload that carries information fields is
            # held to the information rules; a location-only change request
            # must not be asked for Size of Group.
            if not any(field in record for field in _INFO_FIELDS):
                continue
            self._validate_required(record)
            self._validate_household_size(record)
            await self._validate_members_against_size(record)

    def _validate_required(self, record: dict) -> None:
        missing = [
            label
            for field, label in _REQUIRED_FIELDS.items()
            if is_blank(record.get(field))
        ]
        if missing:
            validation_error(f"Required household fields missing: {', '.join(missing)}")
        if as_bool(record.get("other_land_owner")) is None:
            validation_error("other_land_owner must be Yes or No")

    def _validate_household_size(self, record: dict) -> None:
        size_of_group = as_int(record.get("size_of_group"))
        male = as_int(record.get("number_of_male_members"))
        female = as_int(record.get("number_of_female_members"))
        for label, value in (
            ("size_of_group", size_of_group),
            ("number_of_male_members", male),
            ("number_of_female_members", female),
        ):
            if value is None:
                validation_error(f"{label} must be a whole number")
            if value < 0:
                validation_error(f"{label} must not be negative")
        if size_of_group < 1:
            validation_error("size_of_group must be at least 1")
        # Same rule as utils/household_roster: members whose gender is OTHERS or
        # UNKNOWN count toward the size but toward neither tally.
        if male + female > size_of_group:
            validation_error(
                "number_of_male_members + number_of_female_members must not exceed size_of_group"
            )

        children = as_int(record.get("number_of_children"))
        if children is not None and (children < 0 or children > size_of_group):
            validation_error("number_of_children must be between 0 and size_of_group")

        elderly = as_int(record.get("number_of_elderly_members"))
        if elderly is not None and (elderly < 0 or elderly > size_of_group):
            validation_error("number_of_elderly_members must be between 0 and size_of_group")

    async def _validate_members_against_size(self, record: dict) -> None:
        """Re-saving the household section after members were entered must not
        leave size_of_group out of step with the members table. A brand-new
        household has no internal_record_id and no members yet, so this only
        bites on edits; the members section enforces the same rule from its side
        (see G2PRegisterDomainServiceHouseholdMember)."""
        household_id = record.get("internal_record_id")
        if is_blank(household_id):
            return
        size_of_group = as_int(record.get("size_of_group"))
        if size_of_group is None:
            return

        from ..models.household_member import G2PIntakeFormHouseholdMember

        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            member_count = await session.scalar(
                select(func.count()).select_from(G2PIntakeFormHouseholdMember).where(
                    G2PIntakeFormHouseholdMember.link_internal_record_id == str(household_id)
                )
            )
        if member_count and member_count != size_of_group:
            validation_error(
                f"size_of_group is {size_of_group} but {member_count} household member(s) "
                "are recorded; update the members or the size so they match"
            )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for household")

        keys = [
            "functional_record_id",
            "record_name",
            "household_head",
            "latitude",
            "longitude",
            "altitude",
            "plus_code",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "country_code",
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
        _logger.info("Constructing record name for household")

        keys = ["household_head", "functional_record_id"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Household")

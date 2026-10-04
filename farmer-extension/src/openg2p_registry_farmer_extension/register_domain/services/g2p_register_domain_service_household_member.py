import logging
from contextvars import ContextVar
from datetime import date

from openg2p_registry_core.models import G2PRegisterChangeRequest
from openg2p_registry_core.services import G2PRegisterDomainService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .domain_validation_utils import as_bool, as_int, fallback_record_name, is_blank, parse_date, validation_error
from .utils.household_roster import (
    CHANGED_PERSON_KIND_MEMBER,
    recompute_household_for_ingested_row,
    recompute_households_for_change_request,
)

_logger = logging.getLogger("g2p-register-domain-service")

_HEAD_RELATIONSHIP = "SELF"


def _allowed_relationships() -> set[str]:
    # Lazy: ..models imports this module at load time (see models/household_member.py).
    from ..models.enums import RelationshipToTheHeadEnum

    return {item.value for item in RelationshipToTheHeadEnum}

# The members table of one intake save, handed from validate_domain_attributes
# (no DB session) to validate_intake_parent_link (has the session and the
# household link) within the same request. Task-local, so concurrent saves
# cannot see each other's rows.
_pending_member_batch: ContextVar[list[dict] | None] = ContextVar(
    "farmer_pending_household_member_batch", default=None
)


class G2PRegisterDomainServiceHouseholdMember(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_birth_date(record)
            self._validate_head_and_relationship(record)
        self._validate_single_head(records)
        # Set-level checks against the household (size / gender tallies) need
        # the household row; they run in validate_intake_parent_link, which the
        # intake save calls right after this with the resolved household link.
        _pending_member_batch.set(list(records))

    async def validate_intake_parent_link(
        self,
        record: dict,
        link_internal_record_id: str | None,
        session: AsyncSession,
    ) -> None:
        batch = _pending_member_batch.get()
        if batch is None:
            return
        # One pass per save: the batch is the whole members table.
        _pending_member_batch.set(None)

        if batch and not any(self._is_head(member) for member in batch):
            validation_error("One household member must be marked as the head (is_head)")

        if is_blank(link_internal_record_id):
            return

        from ..models.household import G2PIntakeFormHousehold

        household = await session.scalar(
            select(G2PIntakeFormHousehold).where(
                G2PIntakeFormHousehold.internal_record_id == str(link_internal_record_id)
            )
        )
        if household is None:
            return
        self._validate_members_against_household(batch, household)

    # ── per-record rules ─────────────────────────────────────────────────────

    def _validate_birth_date(self, record: dict) -> None:
        birth_date = parse_date(record.get("birth_date"))
        if birth_date is not None and birth_date > date.today():
            validation_error("birth_date must not be in the future")

    def _validate_head_and_relationship(self, record: dict) -> None:
        if "is_head" not in record and "relationship_to_the_head" not in record:
            # Partial payload that does not touch headship (e.g. an API change
            # request editing another field) — nothing to check here.
            return
        relationship = record.get("relationship_to_the_head")
        if not is_blank(relationship) and str(relationship) not in _allowed_relationships():
            validation_error(
                "relationship_to_the_head must be one of "
                + ", ".join(sorted(_allowed_relationships()))
            )
        if self._is_head(record):
            if not is_blank(relationship) and str(relationship) != _HEAD_RELATIONSHIP:
                validation_error(
                    "The household head cannot have a relationship_to_the_head other than SELF"
                )
            # Keep the stored row self-describing: the head is SELF.
            record["relationship_to_the_head"] = _HEAD_RELATIONSHIP
        else:
            if is_blank(relationship):
                validation_error(
                    "relationship_to_the_head is required for every member who is not the head"
                )
            if str(relationship) == _HEAD_RELATIONSHIP:
                validation_error(
                    "relationship_to_the_head SELF is reserved for the head; tick is_head instead"
                )

    # ── set-level rules ──────────────────────────────────────────────────────

    def _validate_single_head(self, records: list[dict]) -> None:
        heads = [record for record in records if self._is_head(record)]
        if len(heads) > 1:
            validation_error("Only one household member can be marked as the head (is_head)")

    def _validate_members_against_household(self, members: list[dict], household) -> None:
        size_of_group = as_int(getattr(household, "size_of_group", None))
        if size_of_group is not None and len(members) != size_of_group:
            validation_error(
                f"Household size_of_group is {size_of_group} but {len(members)} member(s) "
                "were entered; the members must match the size of the group"
            )

        expected_male = as_int(getattr(household, "number_of_male_members", None))
        expected_female = as_int(getattr(household, "number_of_female_members", None))
        if expected_male is None or expected_female is None:
            return
        male = sum(1 for member in members if str(member.get("gender") or "").upper() == "MALE")
        female = sum(1 for member in members if str(member.get("gender") or "").upper() == "FEMALE")
        if male != expected_male or female != expected_female:
            validation_error(
                f"Members entered: {male} male / {female} female, but the household says "
                f"{expected_male} male / {expected_female} female"
            )

    @staticmethod
    def _is_head(record: dict) -> bool:
        return bool(as_bool(record.get("is_head")))

    # ── naming ───────────────────────────────────────────────────────────────

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for household member")

        keys = [
            "first_name",
            "last_name",
            "foundational_id",
            "middle_name",
            "given_name",
            "gender",
            "birth_date",
            "marital_status",
            "occupation",
            "education_level",
            "latitude",
            "longitude",
            "altitude",
            "plus_code",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "country_code",
            "is_disabled",
            "is_head",
            "relationship_to_the_head",
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
        _logger.info("Constructing record name for household member")

        keys = ["first_name", "last_name"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Household member")

    async def pre_approve(self, change_request: G2PRegisterChangeRequest, session: AsyncSession):
        from ..models.household_member import G2PRegisterHouseholdMember

        await recompute_households_for_change_request(
            session,
            change_request,
            model=G2PRegisterHouseholdMember,
            changed_person_kind=CHANGED_PERSON_KIND_MEMBER,
        )

    async def post_ingest(self, register_id: str, register_row, session: AsyncSession):
        await recompute_household_for_ingested_row(session, register_row)

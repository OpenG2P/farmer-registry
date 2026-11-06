import logging
from datetime import date

from openg2p_registry_core.models import G2PRegisterChangeRequest
from openg2p_registry_core.services import G2PRegisterDomainService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from .domain_validation_utils import as_bool, as_int, fallback_record_name, parse_date, validate_enum_values, validation_error
from .utils.household_roster import (
    CHANGED_PERSON_KIND_FARMER,
    calculate_age,
    recompute_household_for_ingested_row,
    recompute_households_for_change_request,
)

_logger = logging.getLogger("g2p-register-domain-service")


_AGE_FIELDS = ("birth_date", "estimated_age")

def _enum_fields() -> dict:
    # Imported lazily: ..models imports these services at module level, so a
    # top-level import here would be circular whenever services load first.
    from ..models.enums import (
        EducationalLevelEnum,
        HouseholdRegistrationStatusEnum,
        SourceOfIncomeEnum,
    )

    return {
        "source_of_income": SourceOfIncomeEnum,
        "education_level": EducationalLevelEnum,
        "household_registration_status": HouseholdRegistrationStatusEnum,
    }


class G2PRegisterDomainServiceFarmer(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            validate_enum_values(record, _enum_fields())
            self._validate_birth_date_or_estimated_age(record)

    async def validate_intake_parent_link(self, record: dict, link_internal_record_id: str | None, session: AsyncSession) -> None:
        submission_id = await self._submission_id_for_record(record, session)
        status = await self._household_registration_status(record, submission_id, session)
        if status is None:
            return
        created_here = await self._household_created_in_submission(
            submission_id, link_internal_record_id, session
        )
        if status == "ALREADY_REGISTERED" and link_internal_record_id and created_here:
            validation_error(
                "Select a registered or in-flight household, not one entered in this form"
            )
        if status == "NOT_REGISTERED" and link_internal_record_id and not created_here:
            validation_error("Enter the household in this form instead of selecting an existing one")
        if status == "NOT_REQUIRED" and link_internal_record_id:
            validation_error("A household link is not allowed when household registration is not required")

    async def validate_intake_submission(self, submission, session: AsyncSession) -> None:
        submission_id = getattr(submission, "submission_id", None)
        if not submission_id:
            return
        from ..models.farmer import G2PIntakeFormFarmer
        from ..models.household import G2PRegisterHousehold
        from .household_submission_validation import validate_household_submission

        farmers = (
            await session.execute(
                select(G2PIntakeFormFarmer).where(
                    G2PIntakeFormFarmer.submission_id == str(submission_id)
                )
            )
        ).scalars().all()
        if not farmers:
            return

        for farmer in farmers:
            self._require_birth_date_or_estimated_age(farmer.birth_date, farmer.estimated_age)
            status = str(farmer.household_registration_status or "").strip() or None
            link_id = str(farmer.link_internal_record_id or "").strip() or None
            if status is None:
                continue

            created_here = await self._household_created_in_submission(
                submission_id, link_id, session
            )
            if status == "ALREADY_REGISTERED":
                if not link_id:
                    validation_error(
                        "A registered household must be linked when household_registration_status is ALREADY_REGISTERED"
                    )
                if created_here:
                    validation_error(
                        "Select a registered or in-flight household, not one entered in this form"
                    )
                live_household = await session.get(G2PRegisterHousehold, link_id)
                if live_household is None:
                    validation_error(
                        f"Linked household '{link_id}' is not present in the live household register"
                    )
            elif status == "NOT_REGISTERED":
                if not link_id or not created_here:
                    validation_error(
                        "Household details must be entered in this form when household_registration_status is NOT_REGISTERED"
                    )
                await validate_household_submission(str(submission_id), session)
            elif status == "NOT_REQUIRED":
                if link_id:
                    validation_error(
                        "A household link is not allowed when household registration is not required"
                    )

    async def _submission_id_for_record(self, record: dict, session: AsyncSession) -> str | None:
        if record.get("submission_id"):
            return str(record["submission_id"])
        internal_record_id = record.get("internal_record_id")
        if not internal_record_id:
            return None
        from ..models.farmer import G2PIntakeFormFarmer

        found = (
            await session.execute(
                select(G2PIntakeFormFarmer.submission_id).where(
                    G2PIntakeFormFarmer.internal_record_id == str(internal_record_id)
                ).limit(1)
            )
        ).scalar_one_or_none()
        return str(found) if found else None

    async def _household_registration_status(self, record: dict, submission_id: str | None, session: AsyncSession) -> str | None:
        raw = record.get("household_registration_status")
        if raw not in (None, ""):
            return str(raw)
        if not submission_id:
            return None
        from ..models.farmer import G2PIntakeFormFarmer

        rows = (
            await session.execute(
                select(G2PIntakeFormFarmer.household_registration_status).where(
                    G2PIntakeFormFarmer.submission_id == submission_id,
                    G2PIntakeFormFarmer.household_registration_status.is_not(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        return str(rows) if rows else None

    async def _household_created_in_submission(self, submission_id, link_internal_record_id, session: AsyncSession) -> bool:
        if not submission_id or not link_internal_record_id:
            return False
        from ..models.household import G2PIntakeFormHousehold

        found = (
            await session.execute(
                select(G2PIntakeFormHousehold.internal_record_id).where(
                    G2PIntakeFormHousehold.submission_id == str(submission_id),
                    G2PIntakeFormHousehold.internal_record_id == str(link_internal_record_id),
                ).limit(1)
            )
        ).scalar_one_or_none()
        return found is not None


    def _validate_birth_date_or_estimated_age(self, record: dict) -> None:
        # Farmer sections that do not collect DOB/age send neither key, and an
        # UPDATE change request only carries the keys it changes.
        present = [field for field in _AGE_FIELDS if field in record]
        if not present:
            return
        if record.get("edit_action") == "UPDATE" and len(present) < len(_AGE_FIELDS):
            return
        self._require_birth_date_or_estimated_age(record.get("birth_date"), record.get("estimated_age"))

    @staticmethod
    def _require_birth_date_or_estimated_age(birth_date, estimated_age) -> None:
        if parse_date(birth_date) is None and as_int(estimated_age) is None:
            validation_error("Either birth_date or estimated_age must be entered")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for farmer")

        keys = [
            "functional_record_id",
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
            "language_spoken",
            "source_of_income",
            "national_id_masked",
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
        _logger.info("Constructing record name for farmer")

        keys = ["first_name", "last_name"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Farmer")

    async def pre_approve(self, change_request: G2PRegisterChangeRequest, session: AsyncSession):
        from ..models.farmer import G2PRegisterFarmer

        await recompute_households_for_change_request(
            session,
            change_request,
            model=G2PRegisterFarmer,
            changed_person_kind=CHANGED_PERSON_KIND_FARMER,
        )

    async def post_approve(self, change_request: G2PRegisterChangeRequest, session: AsyncSession):
        await self._remove_disabilities_when_not_disabled(change_request, session)

    async def _remove_disabilities_when_not_disabled(
        self, change_request: G2PRegisterChangeRequest, session: AsyncSession
    ) -> None:
        from openg2p_registry_core.models import G2PRegisterChangeRequestPayload

        from ..models.farmer_disability import G2PRegisterFarmerDisability

        payload = await session.get(G2PRegisterChangeRequestPayload, change_request.change_request_id)
        farmer_ids: set[str] = set()
        for record in (payload.change_payload if payload else None) or []:
            if record.get("edit_action") in {"DELETE", "NO_CHANGE"}:
                continue
            # A payload without the key comes from a section that does not
            # collect it, so the stored answer is unknown here.
            if "disabled" not in record or as_bool(record.get("disabled")) is True:
                continue
            # A farmer-register section targets the subject itself; a
            # household-register section carries the farmer's id on the row.
            if change_request.section_register_id == change_request.register_id:
                farmer_id = change_request.internal_record_id
            else:
                farmer_id = record.get("internal_record_id")
            if farmer_id:
                farmer_ids.add(str(farmer_id))
        if not farmer_ids:
            return

        rows = (
            await session.execute(
                select(G2PRegisterFarmerDisability).where(
                    G2PRegisterFarmerDisability.link_internal_record_id.in_(farmer_ids)
                )
            )
        ).scalars().all()
        for row in rows:
            await session.delete(row)
        await session.flush()

    async def post_ingest(self, register_id: str, register_row, session: AsyncSession):
        await recompute_household_for_ingested_row(session, register_row)

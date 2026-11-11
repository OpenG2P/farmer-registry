"""Farmer-registry override of the platform intake data service.

Registered by the extension Initializer BEFORE the core initializer so that
G2PIntakeFormDataService.get_component() (an isinstance lookup over the component
registry, first match wins) resolves to this subclass.

A Not registered farmer has no household section on the form. Saving that
status creates the household intake row the member section links to. Finalize
fills the household totals from the farmer and the non-farming members.
"""
import logging
from datetime import datetime

from openg2p_registry_core.models.enum import RecordStatusEnum
from openg2p_registry_core.services.g2p_intake_form_link_service import (
    G2PIntakeFormLinkService,
)
from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
from sqlalchemy import select

from .household_submission_validation import (
    HOUSEHOLD_REGISTER_MNEMONIC,
    validate_household_submission,
)

from .utils.household_roster import recompute_intake_household_roster

_logger = logging.getLogger("g2p-register-domain-service")

FARMER_REGISTER_MNEMONIC = "Farmer"
STATUS_NOT_REGISTERED = "NOT_REGISTERED"
STATUS_ALREADY_REGISTERED = "ALREADY_REGISTERED"
STATUS_NOT_REQUIRED = "NOT_REQUIRED"


class G2PFarmerIntakeFormDataService(G2PIntakeFormDataService):
    async def save_intake_form_submission_with_session(self, *args, **kwargs):
        session = kwargs.get("session") or (args[7] if len(args) > 7 else None)
        await self._clear_auto_household_link(session, args, kwargs)
        submission = await super().save_intake_form_submission_with_session(*args, **kwargs)
        await self._sync_auto_household(submission, session)
        await self._clear_disabilities_when_not_disabled(submission, session)
        return submission

    async def _clear_auto_household_link(self, session, args, kwargs) -> None:
        """Drop a same-submission household link before a status that forbids it is saved.

        The platform keeps an omitted link. A farmer who was Not registered is
        already linked to the household this extension created, so changing to
        Already registered or Not required would be rejected before the new
        status is stored.
        """
        if session is None:
            return
        submission_id = kwargs.get("submission_id", args[0] if args else None)
        register_id = kwargs.get("register_id", args[5] if len(args) > 5 else None)
        section_payload = kwargs.get("section_payload", args[2] if len(args) > 2 else None)
        if not submission_id or not register_id:
            return

        register_definition = await self._get_register_definition(register_id, session)
        if getattr(register_definition, "register_mnemonic", None) != FARMER_REGISTER_MNEMONIC:
            return

        statuses = []
        specifies_link = False
        target_ids: set[str] = set()
        for record in section_payload or []:
            if not isinstance(record, dict) or record.get("edit_action") == "DELETE":
                continue
            status = str(record.get("household_registration_status") or "").strip()
            if status:
                statuses.append(status)
            if str(record.get("link_internal_record_id") or "").strip():
                specifies_link = True
            if record.get("internal_record_id"):
                target_ids.add(str(record["internal_record_id"]))
        if not statuses or STATUS_NOT_REGISTERED in statuses or specifies_link:
            return
        if not any(status in {STATUS_ALREADY_REGISTERED, STATUS_NOT_REQUIRED} for status in statuses):
            return

        from ..models.farmer import G2PIntakeFormFarmer
        from ..models.household import G2PIntakeFormHousehold

        household_ids = set(
            (
                await session.execute(
                    select(G2PIntakeFormHousehold.internal_record_id).where(
                        G2PIntakeFormHousehold.submission_id == str(submission_id)
                    )
                )
            ).scalars().all()
        )
        if not household_ids:
            return

        farmers = (
            await session.execute(
                select(G2PIntakeFormFarmer).where(
                    G2PIntakeFormFarmer.submission_id == str(submission_id)
                )
            )
        ).scalars().all()
        for farmer in farmers:
            if target_ids and str(farmer.internal_record_id) not in target_ids:
                continue
            if farmer.link_internal_record_id in household_ids:
                farmer.link_internal_record_id = None
        await session.flush()

    async def _sync_auto_household(self, submission, session) -> None:
        """Create the household intake row a Not registered farmer has no section for.

        Household members on the farmer form are children of Household. The
        platform will not store them until a household row exists on this
        submission. Already registered and Not required do not collect that
        row, and a Household-register submission already has its own.
        """
        if submission is None or session is None:
            return
        register_definition = await self._get_register_definition(submission.register_id, session)
        if getattr(register_definition, "register_mnemonic", None) != FARMER_REGISTER_MNEMONIC:
            return

        from ..models.farmer import G2PIntakeFormFarmer
        from ..models.household import G2PIntakeFormHousehold

        submission_id = str(submission.submission_id)
        farmers = (
            await session.execute(
                select(G2PIntakeFormFarmer).where(
                    G2PIntakeFormFarmer.submission_id == submission_id
                )
            )
        ).scalars().all()
        households = (
            await session.execute(
                select(G2PIntakeFormHousehold).where(
                    G2PIntakeFormHousehold.submission_id == submission_id
                )
            )
        ).scalars().all()

        needs_household = any(
            str(farmer.household_registration_status or "") == STATUS_NOT_REGISTERED
            for farmer in farmers
        )
        if not needs_household:
            if households:
                deleted_ids = {row.internal_record_id for row in households if row.internal_record_id}
                for row in households:
                    await session.delete(row)
                await session.flush()
                if deleted_ids:
                    await G2PIntakeFormLinkService.get_component().null_child_links_for_deleted_parents(
                        submission_id, deleted_ids, session
                    )
            return

        household = households[0] if households else None
        if household is None:
            record_data = self._build_intake_row_data(
                {},
                G2PIntakeFormHousehold,
                submission,
                submission.created_by,
            )
            if record_data.get("last_approved_at") is None:
                record_data["last_approved_at"] = record_data.get("created_at") or datetime.now()
            record_data["record_status"] = RecordStatusEnum.ACTIVE.value
            household = G2PIntakeFormHousehold(**record_data)
            session.add(household)
            await session.flush()
            _logger.info(
                "Created intake household %s for not-registered farmer submission %s",
                household.internal_record_id,
                submission_id,
            )

        for farmer in farmers:
            if str(farmer.household_registration_status or "") != STATUS_NOT_REGISTERED:
                continue
            farmer.link_internal_record_id = household.internal_record_id
        await session.flush()

    async def _clear_disabilities_when_not_disabled(self, submission, session) -> None:
        """Drop the disability rows of a farmer whose disabled answer is not YES."""
        if submission is None or session is None:
            return
        from ..models.farmer import G2PIntakeFormFarmer
        from ..models.farmer_disability import G2PIntakeFormFarmerDisability

        submission_id = str(submission.submission_id)
        farmer_ids = (
            await session.execute(
                select(G2PIntakeFormFarmer.internal_record_id).where(
                    G2PIntakeFormFarmer.submission_id == submission_id,
                    G2PIntakeFormFarmer.disabled.is_not(True),
                )
            )
        ).scalars().all()
        if not farmer_ids:
            return

        rows = (
            await session.execute(
                select(G2PIntakeFormFarmerDisability).where(
                    G2PIntakeFormFarmerDisability.submission_id == submission_id,
                    G2PIntakeFormFarmerDisability.link_internal_record_id.in_(farmer_ids),
                )
            )
        ).scalars().all()
        for row in rows:
            await session.delete(row)
        await session.flush()

    
    async def finalize_submission_with_session(self, submission_id: str, session, *args, **kwargs):
        submission = await self._get_submission_or_error(submission_id, session)
        register_definition = await self._get_register_definition(submission.register_id, session)
        if getattr(register_definition, "register_mnemonic", None) == HOUSEHOLD_REGISTER_MNEMONIC:
            await validate_household_submission(submission.submission_id, session)
        await self._assign_household_head_for_new_household(submission_id, session)
        await recompute_intake_household_roster(session, submission_id)
        return await super().finalize_submission_with_session(submission_id, session, *args, **kwargs)

    async def _assign_household_head_for_new_household(self, submission_id: str, session) -> None:
        from sqlalchemy import select

        from ..models.farmer import G2PIntakeFormFarmer
        from ..models.household import G2PIntakeFormHousehold

        farmers = (
            await session.execute(
                select(G2PIntakeFormFarmer).where(
                    G2PIntakeFormFarmer.submission_id == str(submission_id)
                )
            )
        ).scalars().all()

        for farmer in farmers:
            if str(farmer.household_registration_status or "") != "NOT_REGISTERED":
                continue
            household = (
                await session.execute(
                    select(G2PIntakeFormHousehold).where(
                        G2PIntakeFormHousehold.submission_id == str(submission_id)
                    )
                )
            ).scalars().first()
            if household is None:
                continue

            farmer.is_head = True
            farmer.relationship_to_the_head = None
            farmer.link_internal_record_id = household.internal_record_id
            household.household_head = " ".join(
                part for part in (farmer.first_name, farmer.last_name) if part
            ).strip() or None
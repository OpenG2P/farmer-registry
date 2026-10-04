"""Farmer-registry override of the platform intake data service.

Registered by the extension Initializer BEFORE the core initializer so that
G2PIntakeFormDataService.get_component() (an isinstance lookup over the component
registry, first match wins) resolves to this subclass. Only finalize is changed:
Household submissions get the cross-section roster check the per-section hooks
cannot provide.
"""
import logging

from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService

from .household_submission_validation import (
    HOUSEHOLD_REGISTER_MNEMONIC,
    validate_household_submission,
)

_logger = logging.getLogger("g2p-register-domain-service")


class G2PFarmerIntakeFormDataService(G2PIntakeFormDataService):
    async def finalize_submission_with_session(self, submission_id: str, session, *args, **kwargs):
        submission = await self._get_submission_or_error(submission_id, session)
        register_definition = await self._get_register_definition(submission.register_id, session)
        if getattr(register_definition, "register_mnemonic", None) == HOUSEHOLD_REGISTER_MNEMONIC:
            await validate_household_submission(submission.submission_id, session)
        return await super().finalize_submission_with_session(submission_id, session, *args, **kwargs)

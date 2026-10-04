"""Cross-section checks for a Household intake submission, run when it is finalized.

The per-section hooks (validate_domain_attributes / validate_intake_parent_link)
only see the section being saved, so a household whose members section was never
filled in, or was cleared afterwards, still finalizes cleanly. The platform's
finalize path has no domain hook, so G2PFarmerIntakeFormDataService calls
validate_household_submission() before handing the submission to the workflow.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .domain_validation_utils import as_bool, as_int, is_blank, validation_error

HOUSEHOLD_REGISTER_MNEMONIC = "Household"
_HEAD_RELATIONSHIP = "SELF"


def _get(obj, key: str):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _gender(member) -> str:
    return str(_get(member, "gender") or "").upper()


def validate_household_roster(household, members: list) -> None:
    """Pure rule set shared by the unit tests and the finalize hook.

    `household` / `members` may be ORM rows or plain dicts. Raises the platform
    REQ-VAL-001 validation error with a user-facing message on the first breach.
    """
    if household is None:
        validation_error("Household information must be entered before the submission can be finalized")

    size_of_group = as_int(_get(household, "size_of_group"))
    members = list(members or [])

    if not members:
        expected = f" ({size_of_group} expected)" if size_of_group else ""
        validation_error(
            "Household members must be entered before the submission can be finalized"
            f"{expected}; add every member of the household, including the head"
        )

    if size_of_group is not None and len(members) != size_of_group:
        validation_error(
            f"Household size_of_group is {size_of_group} but {len(members)} member(s) "
            "were entered; the members must match the size of the group"
        )

    heads = [member for member in members if as_bool(_get(member, "is_head"))]
    if not heads:
        validation_error("One household member must be marked as the head (is_head)")
    if len(heads) > 1:
        validation_error("Only one household member can be marked as the head (is_head)")

    for member in members:
        relationship = _get(member, "relationship_to_the_head")
        if as_bool(_get(member, "is_head")):
            if not is_blank(relationship) and str(relationship).upper() != _HEAD_RELATIONSHIP:
                validation_error(
                    f"The household head cannot have a relationship_to_the_head other than {_HEAD_RELATIONSHIP}"
                )
        elif is_blank(relationship):
            validation_error("relationship_to_the_head is required for every member who is not the head")

    expected_male = as_int(_get(household, "number_of_male_members"))
    expected_female = as_int(_get(household, "number_of_female_members"))
    if expected_male is None or expected_female is None:
        return
    male = sum(1 for member in members if _gender(member) == "MALE")
    female = sum(1 for member in members if _gender(member) == "FEMALE")
    if male != expected_male or female != expected_female:
        validation_error(
            f"Members entered: {male} male / {female} female, but the household says "
            f"{expected_male} male / {expected_female} female"
        )


async def validate_household_submission(submission_id: str, session: AsyncSession) -> None:
    """Load the submission's intake household + member rows and apply the roster rules."""
    # Lazy: ..models imports the services package at load time.
    from ..models.household import G2PIntakeFormHousehold
    from ..models.household_member import G2PIntakeFormHouseholdMember

    household = (
        await session.execute(
            select(G2PIntakeFormHousehold).where(G2PIntakeFormHousehold.submission_id == str(submission_id))
        )
    ).scalars().first()
    members = (
        await session.execute(
            select(G2PIntakeFormHouseholdMember).where(
                G2PIntakeFormHouseholdMember.submission_id == str(submission_id)
            )
        )
    ).scalars().all()
    validate_household_roster(household, members)

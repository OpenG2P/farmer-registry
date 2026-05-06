from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, select
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import (
    G2PRegister, G2PRegisterHistory, G2PPerson, G2PGeo,
    G2PPersonHistory, G2PGeoHistory
)
from ..services import G2PRegisterDomainServiceHouseholdMember


class G2PHouseholdMember:

    is_disabled: Mapped[bool] = mapped_column(Boolean, nullable=True)


# All Register classes should have the prefix G2PRegister
class G2PRegisterHouseholdMember(G2PRegister, G2PPerson, G2PGeo, G2PHouseholdMember):
    __tablename__ = "g2p_register_household_members"

    def get_search_text_fields(self) -> str:
        """Return household member fields used to build search_text."""
        return G2PRegisterDomainServiceHouseholdMember().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return household member record_name from domain service implementation."""
        return G2PRegisterDomainServiceHouseholdMember().construct_record_name(self.to_dict())


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryHouseholdMember(G2PRegisterHistory, G2PPersonHistory, G2PGeoHistory, G2PHouseholdMember):
    __tablename__ = "g2p_register_history_household_members"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormHouseholdMember(G2PIntakeForm, G2PRegister, G2PPerson, G2PGeo, G2PHouseholdMember):
    __tablename__ = "g2p_intake_form_household_members"

    async def get_link_internal_record_id(self, session):
        from .household import G2PIntakeFormHousehold
        result = await session.execute(
            select(G2PIntakeFormHousehold).where(G2PIntakeFormHousehold.submission_id == self.submission_id)
        )
        household = result.scalars().first()
        if household:
            self.link_internal_record_id = household.internal_record_id

    def get_search_text_fields(self) -> str:
        """Return household member fields used to build search_text."""
        return G2PRegisterDomainServiceHouseholdMember().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return household member record_name from domain service implementation."""
        return G2PRegisterDomainServiceHouseholdMember().construct_record_name(self.to_dict())

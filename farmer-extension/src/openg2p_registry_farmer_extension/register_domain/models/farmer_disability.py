from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from ..services import G2PRegisterDomainServiceFarmerDisability
from .enums import DisabilitySeverityEnum, DisabilityTypeEnum


class G2PFarmerDisability:

    disability_domains: Mapped[DisabilityTypeEnum] = mapped_column(String, nullable=True)
    disability_severity: Mapped[DisabilitySeverityEnum] = mapped_column(String, nullable=True)


class G2PRegisterFarmerDisability(G2PRegister, G2PFarmerDisability):
    __tablename__ = "g2p_register_farmer_disability"

    def get_search_text_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerDisability().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerDisability().construct_record_name(self.to_dict())


class G2PRegisterHistoryFarmerDisability(G2PRegisterHistory, G2PFarmerDisability):
    __tablename__ = "g2p_register_history_farmer_disability"


class G2PIntakeFormFarmerDisability(G2PIntakeForm, G2PRegister, G2PFarmerDisability):
    __tablename__ = "g2p_intake_form_farmer_disability"

    async def get_link_internal_record_id(self, session):
        from .farmer import G2PIntakeFormFarmer

        result = await session.execute(
            select(G2PIntakeFormFarmer).where(
                G2PIntakeFormFarmer.submission_id == self.submission_id
            )
        )
        farmer = result.scalars().first()
        if farmer:
            self.link_internal_record_id = farmer.internal_record_id

    def get_search_text_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerDisability().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerDisability().construct_record_name(self.to_dict())

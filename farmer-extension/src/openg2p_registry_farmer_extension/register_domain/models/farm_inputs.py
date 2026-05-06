from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, String, select
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from ..services import G2PRegisterDomainServiceFarmInputs


class G2PFarmInputs:

    fertilizer_use: Mapped[bool] = mapped_column(Boolean, nullable=True)
    pesticide_use: Mapped[bool] = mapped_column(Boolean, nullable=True)
    insecticide_use: Mapped[bool] = mapped_column(Boolean, nullable=True)
    improved_seed_use: Mapped[bool] = mapped_column(Boolean, nullable=True)
    water_source: Mapped[str] = mapped_column(String, nullable=True)          # Attribute lookup (Excel: Rainfed; Irrigation GW/Surface; Well; Water Harvesting; Surface Water)
    access_to_machinery: Mapped[bool] = mapped_column(Boolean, nullable=True)
    access_to_finance: Mapped[bool] = mapped_column(Boolean, nullable=True)


# All Register classes should have the prefix G2PRegister
class G2PRegisterFarmInputs(G2PRegister, G2PFarmInputs):
    __tablename__ = "g2p_register_farm_inputs"

    def get_search_text_fields(self) -> str:
        """Return farm inputs fields used to build search_text."""
        return G2PRegisterDomainServiceFarmInputs().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return farm inputs record_name from domain service implementation."""
        return G2PRegisterDomainServiceFarmInputs().construct_record_name(self.to_dict())


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryFarmInputs(G2PRegisterHistory, G2PFarmInputs):
    __tablename__ = "g2p_register_history_farm_inputs"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormFarmInputs(G2PIntakeForm, G2PRegister, G2PFarmInputs):
    __tablename__ = "g2p_intake_form_farm_inputs"

    async def get_link_internal_record_id(self, session):
        from .land import G2PIntakeFormLand
        result = await session.execute(
            select(G2PIntakeFormLand).where(G2PIntakeFormLand.submission_id == self.submission_id)
        )
        land = result.scalars().first()
        if land:
            self.link_internal_record_id = land.internal_record_id

    def get_search_text_fields(self) -> str:
        """Return farm inputs fields used to build search_text."""
        return G2PRegisterDomainServiceFarmInputs().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return farm inputs record_name from domain service implementation."""
        return G2PRegisterDomainServiceFarmInputs().construct_record_name(self.to_dict())

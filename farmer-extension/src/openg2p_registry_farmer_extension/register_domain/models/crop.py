from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Date, String, select
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from ..services import G2PRegisterDomainServiceCrop
from .enums import CropEndUseEnum

class G2PCrop:

    commodity: Mapped[str] = mapped_column(String, nullable=True)      # Attribute lookup
    planted_date: Mapped[str] = mapped_column(Date, nullable=True)
    season: Mapped[str] = mapped_column(String, nullable=True)
    end_use: Mapped[CropEndUseEnum] = mapped_column(String, nullable=True)        # CropEndUseEnum

# All Register classes should have the prefix G2PRegister
class G2PRegisterCrop(G2PRegister, G2PCrop):
    __tablename__ = "g2p_register_crops"

    def get_search_text_fields(self) -> str:
        """Return crop fields used to build search_text."""
        return G2PRegisterDomainServiceCrop().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return crop record_name from domain service implementation."""
        return G2PRegisterDomainServiceCrop().construct_record_name(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryCrop(G2PRegisterHistory, G2PCrop):
    __tablename__ = "g2p_register_history_crops"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormCrop(G2PIntakeForm, G2PRegister, G2PCrop):
    __tablename__ = "g2p_intake_form_crops"

    def get_search_text_fields(self) -> str:
        """Return crop fields used to build search_text."""
        return G2PRegisterDomainServiceCrop().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return crop record_name from domain service implementation."""
        return G2PRegisterDomainServiceCrop().construct_record_name(self.to_dict())

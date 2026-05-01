from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from ..services import G2PRegisterDomainServiceLivestock
from .enums import LivestockSystemEnum


class G2PLivestock:

    livestock_type: Mapped[str] = mapped_column(String, nullable=True)    # Attribute lookup
    breed: Mapped[str] = mapped_column(String, nullable=True)             # Attribute lookup
    head_count: Mapped[int] = mapped_column(Integer, nullable=True)
    livestock_system: Mapped[LivestockSystemEnum] = mapped_column(String, nullable=True)  # LivestockSystemEnum


# All Register classes should have the prefix G2PRegister
class G2PRegisterLivestock(G2PRegister, G2PLivestock):
    __tablename__ = "g2p_register_livestocks"

    def get_search_text_fields(self) -> str:
        """Return livestock fields used to build search_text."""
        return G2PRegisterDomainServiceLivestock().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return livestock record_name from domain service implementation."""
        return G2PRegisterDomainServiceLivestock().construct_record_name(self.to_dict())


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryLivestock(G2PRegisterHistory, G2PLivestock):
    __tablename__ = "g2p_register_history_livestocks"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormLivestock(G2PIntakeForm, G2PRegister, G2PLivestock):
    __tablename__ = "g2p_intake_form_livestocks"

    def get_search_text_fields(self) -> str:
        """Return livestock fields used to build search_text."""
        return G2PRegisterDomainServiceLivestock().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return livestock record_name from domain service implementation."""
        return G2PRegisterDomainServiceLivestock().construct_record_name(self.to_dict())

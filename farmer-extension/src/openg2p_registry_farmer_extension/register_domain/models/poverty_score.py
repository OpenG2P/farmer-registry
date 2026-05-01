from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from ..services import G2PRegisterDomainServicePovertyScore


class G2PPovertyScore:

    poverty_score: Mapped[str] = mapped_column(String, nullable=True)
    poverty_score_type: Mapped[str] = mapped_column(String, nullable=True)


# All Register classes should have the prefix G2PRegister
class G2PRegisterPovertyScore(G2PRegister, G2PPovertyScore):
    __tablename__ = "g2p_register_poverty_scores"

    def get_search_text_fields(self) -> str:
        """Return poverty score fields used to build search_text."""
        return G2PRegisterDomainServicePovertyScore().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return poverty score record_name from domain service implementation."""
        return G2PRegisterDomainServicePovertyScore().construct_record_name(self.to_dict())


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryPovertyScore(G2PRegisterHistory, G2PPovertyScore):
    __tablename__ = "g2p_register_history_poverty_scores"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormPovertyScore(G2PIntakeForm, G2PRegister, G2PPovertyScore):
    __tablename__ = "g2p_intake_form_poverty_scores"

    def get_search_text_fields(self) -> str:
        """Return poverty score fields used to build search_text."""
        return G2PRegisterDomainServicePovertyScore().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return poverty score record_name from domain service implementation."""
        return G2PRegisterDomainServicePovertyScore().construct_record_name(self.to_dict())

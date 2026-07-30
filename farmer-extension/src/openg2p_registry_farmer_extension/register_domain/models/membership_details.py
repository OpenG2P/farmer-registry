from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, String, select
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from ..services import G2PRegisterDomainServiceMembershipDetails
from .enums import FarmerClusterRoleEnum

class G2PMembershipDetails:

    is_primary_cooperative_member: Mapped[bool] = mapped_column(Boolean, nullable=True)
    primary_cooperative_name: Mapped[str] = mapped_column(String, nullable=True)
    is_cooperative_union_member: Mapped[bool] = mapped_column(Boolean, nullable=True)
    cooperative_union_name: Mapped[str] = mapped_column(String, nullable=True)
    is_farmer_cluster_member: Mapped[bool] = mapped_column(Boolean, nullable=True)
    farmer_cluster_role: Mapped[FarmerClusterRoleEnum] = mapped_column(String, nullable=True)   # FarmerClusterRoleEnum

# All Register classes should have the prefix G2PRegister
class G2PRegisterMembershipDetails(G2PRegister, G2PMembershipDetails):
    __tablename__ = "g2p_register_membership_details"

    def get_search_text_fields(self) -> str:
        """Return membership details fields used to build search_text."""
        return G2PRegisterDomainServiceMembershipDetails().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return membership details record_name from domain service implementation."""
        return G2PRegisterDomainServiceMembershipDetails().construct_record_name(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryMembershipDetails(G2PRegisterHistory, G2PMembershipDetails):
    __tablename__ = "g2p_register_history_membership_details"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormMembershipDetails(G2PIntakeForm, G2PRegister, G2PMembershipDetails):
    __tablename__ = "g2p_intake_form_membership_details"

    def get_search_text_fields(self) -> str:
        """Return membership details fields used to build search_text."""
        return G2PRegisterDomainServiceMembershipDetails().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return membership details record_name from domain service implementation."""
        return G2PRegisterDomainServiceMembershipDetails().construct_record_name(self.to_dict())
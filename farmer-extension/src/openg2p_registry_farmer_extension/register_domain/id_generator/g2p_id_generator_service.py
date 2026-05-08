from openg2p_fastapi_common.service import BaseService
from openg2p_registry_core.interfaces import G2PIdGeneratorInterface, IdAffix
from openg2p_registry_core.models.g2p_register import G2PRegister


class G2PIdGeneratorService(BaseService, G2PIdGeneratorInterface):

    def generate_prefix_suffix(
        self, g2p_register: G2PRegister, register_mnemonic: str
    ) -> IdAffix:
        mnemonic = (register_mnemonic or "").lower()

        if mnemonic == "household":
            return IdAffix(prefix="HH-", suffix="")
        if mnemonic == "farmer":
            return IdAffix(prefix="FR-", suffix="")

        return IdAffix(prefix="DEFAULT-", suffix="")

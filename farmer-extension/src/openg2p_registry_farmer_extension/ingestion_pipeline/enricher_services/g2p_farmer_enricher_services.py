import logging
from typing import Dict

from openg2p_registry_core.interfaces import G2PPayloadEnricherInterface
from sqlalchemy.orm import Session

_logger = logging.getLogger('g2p-payload-enricher-service')

# DCI Payload Enrichers
class G2PDciFarmerCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciFarmerCreateEnricherService")
        return data

class G2PDciFarmerUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciFarmerUpdateEnricherService")
        return data

class G2PDciFarmerDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciFarmerDeleteEnricherService")
        return data

# SPDCI Payload Enrichers
class G2PSpdciFarmerCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciFarmerCreateEnricherService")
        return data

class G2PSpdciFarmerUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciFarmerUpdateEnricherService")
        return data

class G2PSpdciFarmerDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciFarmerDeleteEnricherService")
        return data

# UNDP Payload Enrichers
class G2PUndpFarmerCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpFarmerCreateEnricherService")
        return data

class G2PUndpFarmerUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpFarmerUpdateEnricherService")
        return data

class G2PUndpFarmerDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpFarmerDeleteEnricherService")
        return data

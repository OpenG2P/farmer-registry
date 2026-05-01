import logging
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy import select
from openg2p_registry_core.interfaces import G2PPayloadEnricherInterface
from openg2p_registry_extensions.register_domain.models import G2PRegisterHouseholdMember


_logger = logging.getLogger('g2p-payload-enricher-service')

# DCI Payload Enrichers
class G2PDciHouseholdMemberCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciHouseholdMemberCreateEnricherService")

        parent_link_internal_record_id = None

        # Try to find a parent Household member using parent1_identifier
        parent1_identifier_data = data.get('parent1_identifier')
        if isinstance(parent1_identifier_data, dict):
            identifier_value = parent1_identifier_data.get('identifier_value')
            if identifier_value:
                _logger.debug(f"Checking for parent Household member with parent1_identifier: {identifier_value}")
                parent_Household_member = session.execute(
                    select(G2PRegisterHouseholdMember).filter_by(identifier_value=identifier_value)
                ).scalar_one_or_none()

                if parent_Household_member:
                    parent_link_internal_record_id = parent_Household_member.link_internal_record_id
                    _logger.info(f"Found parent Household member via parent1_identifier. Link record ID: {parent_link_internal_record_id}")

        # If parent1_identifier didn't yield a result, try parent2_identifier
        if parent_link_internal_record_id is None:
            parent2_identifier_data = data.get('parent2_identifier')
            if isinstance(parent2_identifier_data, dict):
                identifier_value = parent2_identifier_data.get('identifier_value')
                if identifier_value:
                    _logger.debug(f"Checking for parent Household member with parent2_identifier: {identifier_value}")
                    parent_Household_member = session.execute(
                        select(G2PRegisterHouseholdMember).filter_by(identifier_value=identifier_value)
                    ).scalar_one_or_none()

                    if parent_Household_member:
                        parent_link_internal_record_id = parent_Household_member.link_internal_record_id
                        _logger.info(f"Found parent Household member via parent2_identifier. Link record ID: {parent_link_internal_record_id}")

        if parent_link_internal_record_id:
            data['link_internal_record_id'] = parent_link_internal_record_id
        else:
            _logger.warning("Could not find a parent Household member using either parent1_identifier or parent2_identifier.")
            data["link_internal_record_id"] = None
        
        return data

class G2PDciHouseholdMemberUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciHouseholdMemberUpdateEnricherService")
        return data

class G2PDciHouseholdMemberDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciHouseholdMemberDeleteEnricherService")
        return data

# SPDCI Payload Enrichers
class G2PSpdciHouseholdMemberCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciHouseholdMemberCreateEnricherService")
        return data

class G2PSpdciHouseholdMemberUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciHouseholdMemberUpdateEnricherService")
        return data

class G2PSpdciHouseholdMemberDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciHouseholdMemberDeleteEnricherService")
        return data

# UNDP Payload Enrichers
class G2PUndpHouseholdMemberCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpHouseholdMemberCreateEnricherService")
        return data

class G2PUndpHouseholdMemberUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpHouseholdMemberUpdateEnricherService")
        return data

class G2PUndpHouseholdMemberDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpHouseholdMemberDeleteEnricherService")
        return data

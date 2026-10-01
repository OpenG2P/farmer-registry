# ruff: noqa: E402
import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_common.context import dbengine
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from openg2p_registry_core.app import Initializer as CoreInitializer

from .register_domain.models import (
    G2PRegisterFarmer, G2PRegisterHistoryFarmer,
    G2PRegisterHousehold, G2PRegisterHistoryHousehold,
    G2PRegisterHouseholdMember, G2PRegisterHistoryHouseholdMember,
    G2PRegisterLand, G2PRegisterHistoryLand,
    G2PRegisterFarmInputs, G2PRegisterHistoryFarmInputs,
    G2PRegisterLivestock, G2PRegisterHistoryLivestock,
    G2PRegisterMembershipDetails, G2PRegisterHistoryMembershipDetails,
    G2PIntakeFormHousehold, G2PIntakeFormFarmer, G2PIntakeFormHouseholdMember,
    G2PIntakeFormLand, G2PIntakeFormFarmInputs,
    G2PIntakeFormLivestock, G2PIntakeFormMembershipDetails,
)
from .register_domain.factory import G2PRegisterDomainFactory
from .register_domain.services import G2PRegisterDomainServiceFarmer, G2PRegisterDomainServiceHousehold

_logger = logging.getLogger(_config.logging_default_logger_name)


async def add_missing_columns(model) -> list[str]:
    """Add the model's columns that its existing table lacks; return their names.

    create_migrate() only creates a table that is not there yet, so a column
    added to a model later (Farmer's main_crops) never reaches an install whose
    table already exists. This brings such a table up to the model -- the same
    approach RP takes for its activity tables (add_missing_columns in
    G2PActivityPartitionService), kept here so it does not depend on the RP
    version this extension is deployed on.

    Columns are added nullable unless they carry a server default, so existing
    rows stay valid. Nothing is ever dropped: a column or table the model no
    longer declares (the retired g2p_register_crops*) keeps its data.
    """
    table = model.__table__
    dialect = postgresql.dialect()
    async with dbengine.get().begin() as conn:
        existing = set(
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = current_schema() AND table_name = :name"
                    ),
                    {"name": table.name},
                )
            ).scalars()
        )
        if not existing:
            return []  # no table yet: create_migrate creates it whole
        added = []
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = (
                f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS "{column.name}" '
                + column.type.compile(dialect=dialect)
            )
            default = column.server_default
            if default is not None:
                value = getattr(default.arg, "text", default.arg)
                ddl += f" DEFAULT {value}"
                if not column.nullable:
                    ddl += " NOT NULL"
            await conn.execute(text(ddl))
            added.append(column.name)
    if added:
        _logger.info("Added columns to %s: %s", table.name, added)
    return added


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize()
        CoreInitializer().initialize()

        G2PRegisterDomainFactory()
        G2PRegisterDomainServiceFarmer()
        G2PRegisterDomainServiceHousehold()

    def migrate_database(self, args):

        async def migrate():
            _logger.info("Migrating extensions database")

            await G2PRegisterHousehold.create_migrate()
            await G2PRegisterHistoryHousehold.create_migrate()
            await G2PIntakeFormHousehold.create_migrate()

            await G2PRegisterHouseholdMember.create_migrate()
            await G2PRegisterHistoryHouseholdMember.create_migrate()
            await G2PIntakeFormHouseholdMember.create_migrate()

            await G2PRegisterFarmer.create_migrate()
            await G2PRegisterHistoryFarmer.create_migrate()
            await G2PIntakeFormFarmer.create_migrate()
            # Existing installs: the farmer tables predate main_crops.
            for model in (G2PRegisterFarmer, G2PRegisterHistoryFarmer, G2PIntakeFormFarmer):
                await add_missing_columns(model)

            await G2PRegisterMembershipDetails.create_migrate()
            await G2PRegisterHistoryMembershipDetails.create_migrate()
            await G2PIntakeFormMembershipDetails.create_migrate()

            await G2PRegisterLand.create_migrate()
            await G2PRegisterHistoryLand.create_migrate()
            await G2PIntakeFormLand.create_migrate()

            await G2PRegisterFarmInputs.create_migrate()
            await G2PRegisterHistoryFarmInputs.create_migrate()
            await G2PIntakeFormFarmInputs.create_migrate()

            await G2PRegisterLivestock.create_migrate()
            await G2PRegisterHistoryLivestock.create_migrate()
            await G2PIntakeFormLivestock.create_migrate()

        asyncio.run(migrate())

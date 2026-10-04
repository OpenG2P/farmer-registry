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
from openg2p_fastapi_common.context import component_registry
from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService

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
from .register_domain.services import (
    G2PFarmerIntakeFormDataService,
    G2PRegisterDomainServiceFarmer,
    G2PRegisterDomainServiceHousehold,
    G2PRegisterDomainServiceHouseholdMember,
)

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


async def convert_land_size_to_numeric(model) -> None:
    """Convert a land table's land_size from text to numeric, if it is still text.

    land_size became Numeric in the model (1.2, G2P-5480); create_migrate()
    never alters an existing column, so an install whose land tables were made
    while it was a string keeps varchar and the API then binds a number to a
    text column. Idempotent: only a character/text column is touched. Blank or
    non-numeric values become NULL (counted in the log) instead of failing the
    start-up.

    Postgres cannot change the type of a column a view reads. The only readers
    are this registry's reporting views (fr_rpt_land and the views built on
    it), which the reporting-views Job drops and recreates on every
    install/upgrade, so they are dropped here (CASCADE) and come back with that
    Job.
    """
    table = model.__table__.name
    numeric = r"^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$"
    async with dbengine.get().begin() as conn:
        data_type = (
            await conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = :name "
                    "AND column_name = 'land_size'"
                ),
                {"name": table},
            )
        ).scalar()
        if data_type not in ("character varying", "text", "character"):
            return
        dependents = (
            await conn.execute(
                text(
                    "SELECT DISTINCT quote_ident(n.nspname) || '.' || quote_ident(c.relname), c.relkind::text "
                    "FROM pg_depend d "
                    "JOIN pg_rewrite r ON r.oid = d.objid "
                    "JOIN pg_class c ON c.oid = r.ev_class "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid "
                    "WHERE d.classid = 'pg_rewrite'::regclass "
                    "AND d.refobjid = CAST(:name AS regclass) AND a.attname = 'land_size' "
                    "AND c.oid <> d.refobjid AND c.relkind IN ('v', 'm')"
                ),
                {"name": table},
            )
        ).all()
        for name, relkind in dependents:
            kind = "MATERIALIZED VIEW" if relkind == "m" else "VIEW"
            await conn.execute(text(f"DROP {kind} IF EXISTS {name} CASCADE"))
        dropped = (
            await conn.execute(
                text(
                    f'SELECT count(*) FROM "{table}" WHERE land_size IS NOT NULL '
                    f"AND btrim(land_size) <> '' AND btrim(land_size) !~ :pattern"
                ),
                {"pattern": numeric},
            )
        ).scalar()
        await conn.execute(
            text(
                f'ALTER TABLE "{table}" ALTER COLUMN land_size TYPE NUMERIC USING '
                f"CASE WHEN btrim(land_size) ~ '{numeric}' THEN btrim(land_size)::numeric END"
            )
        )
    _logger.info(
        "Converted %s.land_size to numeric (%s non-numeric value(s) set to NULL; dropped views: %s)",
        table, dropped, [d[0] for d in dependents],
    )


def _install_component_override(instance, base_cls) -> None:
    """Place `instance` before every other registered `base_cls` component."""
    registry = component_registry
    if instance in registry:
        registry.remove(instance)
    first = next((i for i, c in enumerate(registry) if isinstance(c, base_cls)), len(registry))
    registry.insert(first, instance)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize()
        CoreInitializer().initialize()

        # Override the platform intake data service (adds the Household finalize
        # roster check). get_component() returns the FIRST registered instance of
        # the class, and the API main constructs the core initializer before this
        # one, so the subclass has to be moved ahead of the core instance.
        _install_component_override(G2PFarmerIntakeFormDataService(), G2PIntakeFormDataService)

        G2PRegisterDomainServiceFarmer()
        G2PRegisterDomainServiceHousehold()
        G2PRegisterDomainServiceHouseholdMember()

    def migrate_database(self, args):

        async def migrate():
            _logger.info("Migrating extensions database")

            await G2PRegisterHousehold.create_migrate()
            await G2PRegisterHistoryHousehold.create_migrate()
            await G2PIntakeFormHousehold.create_migrate()
            # Existing installs: the household tables predate number_of_elderly_members.
            for model in (G2PRegisterHousehold, G2PRegisterHistoryHousehold, G2PIntakeFormHousehold):
                await add_missing_columns(model)

            await G2PRegisterHouseholdMember.create_migrate()
            await G2PRegisterHistoryHouseholdMember.create_migrate()
            await G2PIntakeFormHouseholdMember.create_migrate()
            # Existing installs: the member tables predate is_head / relationship_to_the_head.
            for model in (G2PRegisterHouseholdMember, G2PRegisterHistoryHouseholdMember, G2PIntakeFormHouseholdMember):
                await add_missing_columns(model)

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
            # Existing installs: land_size predates its change from text to numeric.
            for model in (G2PRegisterLand, G2PRegisterHistoryLand, G2PIntakeFormLand):
                await convert_land_size_to_numeric(model)

            await G2PRegisterFarmInputs.create_migrate()
            await G2PRegisterHistoryFarmInputs.create_migrate()
            await G2PIntakeFormFarmInputs.create_migrate()

            await G2PRegisterLivestock.create_migrate()
            await G2PRegisterHistoryLivestock.create_migrate()
            await G2PIntakeFormLivestock.create_migrate()

        asyncio.run(migrate())

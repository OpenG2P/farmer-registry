import httpx
import pytest

from sanity import awe_seed, cm_seed, data_seed, keycloak_seed, pm_seed
from sanity.config import Config
from sanity.signing import load_private_key_pem
from sanity.staff import StaffClient


@pytest.fixture(scope="session")
def cfg() -> Config:
    return Config.from_env()


@pytest.fixture(scope="session")
def partner_client(cfg):
    # The Farmer Registry PARTNER api (DCI search) — the PEP under test.
    with httpx.Client(base_url=cfg.partner_base_url, verify=cfg.verify_tls, timeout=30) as c:
        yield c


@pytest.fixture(scope="session")
def priv(cfg):
    return load_private_key_pem(cfg.pm_private_key_pem)


@pytest.fixture(scope="session")
def seeded(cfg):
    """Ensure the shared sanity partner exists in BOTH Partner Management (key)
    and the Consent Manager (binding + policy).

    Skips the e2e (rather than failing) when e2e is off or PM/CM aren't
    reachable/seedable, so smoke coverage stays green everywhere. The seeded
    partner + binding are intentionally left in place after the run.
    """
    if not cfg.run_e2e:
        pytest.skip("SANITY_RUN_E2E not enabled")
    if not cfg.can_reach_pm:
        pytest.skip("SANITY_PM_PARTNER_API_URL not set — cannot seed Partner Management")
    if not cfg.can_reach_cm:
        pytest.skip("SANITY_CM_STAFF_URL not set — cannot seed the Consent Manager binding")
    try:
        pm_status = pm_seed.ensure_seeded(cfg)
        cm_status = cm_seed.ensure_binding(cfg)
    except Exception as exc:  # noqa: BLE001 — surface as a skip with the reason
        pytest.skip(f"could not seed the sanity partner: {exc}")
    return {"pm": pm_status, "cm": cm_status}


@pytest.fixture(scope="session")
def farmer_seeded(cfg):
    """Ensure the sanity test farmer exists in the registry.

    Injected by SQL rather than an API: every staff-portal-api register write is
    a change request, and the DCI tests need a record that already exists in an
    approved, ACTIVE state. Injected rather than reusing seeded sample data so
    the e2e also works on installs with `dbSeed.loadSampleData=false`.

    Normally the data-seed Job has already done this at install; doing it again
    here is idempotent and keeps the suite runnable on demand.
    """
    if not cfg.run_e2e:
        pytest.skip("SANITY_RUN_E2E not enabled")
    if not cfg.registry_dsn:
        pytest.skip("registry DB not configured — cannot inject the sanity farmer")
    try:
        return data_seed.ensure_seeded(cfg)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"could not inject the sanity farmer: {exc}")


@pytest.fixture(scope="session")
def staff_user(cfg):
    """Provision the suite's own Keycloak identity (non-temporary password).

    The shipped demo users cannot be used — keycloak-init gives them a temporary
    password, so Keycloak forces UPDATE_PASSWORD and the password grant fails.
    """
    if not cfg.run_e2e:
        pytest.skip("SANITY_RUN_E2E not enabled")
    if not (cfg.keycloak_base_url and cfg.keycloak_admin_password):
        pytest.skip("Keycloak admin not configured — cannot provision the sanity user")
    try:
        return keycloak_seed.ensure_user(cfg)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"could not provision the sanity Keycloak user: {exc}")


@pytest.fixture(scope="session")
def awe_approver(cfg, staff_user):
    """Name the sanity user as an approver on the register's shipped CR policy."""
    if not (cfg.registry_dsn and cfg.awe_dsn):
        pytest.skip("registry or AWE DB not configured — cannot register the approver")
    try:
        return awe_seed.ensure_approver(cfg)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"could not register the sanity approver: {exc}")


@pytest.fixture(scope="session")
def staff_client(cfg, staff_user):
    """staff-portal-api logged in as the seeded sanity user."""
    if not cfg.can_reach_staff:
        pytest.skip("staff-portal-api not configured (SANITY_STAFF_BASE_URL / token / client / password)")
    try:
        client = StaffClient.login(cfg, cfg.staff_username, cfg.staff_password)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"could not log in to staff-portal-api as '{cfg.staff_username}': {exc}")
    try:
        yield client
    finally:
        client.close()

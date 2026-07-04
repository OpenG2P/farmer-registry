import httpx
import pytest

from sanity import cm_seed, pm_seed
from sanity.config import Config
from sanity.signing import load_private_key_pem


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

import os
from dataclasses import dataclass, field
from typing import List

from .testkey import DEFAULT_KID, DEFAULT_PARTNER_ID, TEST_PRIVATE_KEY_PEM


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "yes", "on")


def _list(value, default):
    if not value:
        return list(default)
    return [s.strip() for s in value.split(",") if s.strip()]


@dataclass
class Config:
    # ── Farmer Registry partner-api (the PEP under test) ────────────────────
    partner_base_url: str  # e.g. http://<release>-partner-api  (no ingress path prefix)
    verify_tls: bool
    run_e2e: bool
    readiness_timeout: int

    # ── Shared sanity partner identity (same partner as CM) ─────────────────
    pm_partner_id: str       # PM reference, e.g. PARTNER_CM_SANITY
    pm_kid: str              # kid registered in PM
    pm_private_key_pem: str  # PEM private key the e2e signs both JWSs with

    # ── DCI request shaping ─────────────────────────────────────────────────
    dci_sender_id: str       # envelope sender; PARTNER_<upper> must equal pm_partner_id
    dci_receiver_id: str     # envelope receiver (the registry)
    reg_type: str            # register mnemonic, e.g. Farmer
    reg_record_type: str     # DCI record type for the payload shape
    search_text: str         # a value to search for (0 hits is still a valid request)

    # ── Consent Manager binding + consent object ────────────────────────────
    cm_staff_url: str        # CM staff-portal-api base (to seed the binding + policy)
    cm_audience: str         # the consent object's `aud` == the CM binding audience
    controller_id: str       # data_controller (must match the binding's controller)
    data_scopes: List[str] = field(default_factory=list)  # policy + consent scopes

    # ── Partner Management seeding (key) ────────────────────────────────────
    pm_partner_api_url: str = ""   # PM key-fetch base (servability check)
    pm_admin_url: str = ""         # PM staff-portal-api base (to onboard/approve)
    pm_admin_token_url: str = ""
    pm_admin_client_id: str = "partner-management"
    pm_admin_client_secret: str = ""

    # ── Consent Manager admin auth (to create the binding via staff API) ────
    cm_auth_enabled: bool = True
    cm_token_url: str = ""
    cm_client_id: str = "consent-manager"
    cm_client_secret: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            partner_base_url=(os.environ.get("SANITY_PARTNER_BASE_URL") or "http://localhost:8000").rstrip("/"),
            verify_tls=_bool(os.environ.get("SANITY_VERIFY_TLS"), True),
            run_e2e=_bool(os.environ.get("SANITY_RUN_E2E"), False),
            readiness_timeout=int(os.environ.get("SANITY_READINESS_TIMEOUT", "180")),
            pm_partner_id=os.environ.get("SANITY_PM_PARTNER_ID") or DEFAULT_PARTNER_ID,
            pm_kid=os.environ.get("SANITY_PM_KID") or DEFAULT_KID,
            pm_private_key_pem=os.environ.get("SANITY_PM_PRIVATE_KEY_PEM") or TEST_PRIVATE_KEY_PEM,
            dci_sender_id=os.environ.get("SANITY_DCI_SENDER_ID") or "cm_sanity",
            dci_receiver_id=os.environ.get("SANITY_DCI_RECEIVER_ID") or "farmer-registry",
            reg_type=os.environ.get("SANITY_DCI_REG_TYPE") or "Farmer",
            reg_record_type=os.environ.get("SANITY_DCI_REG_RECORD_TYPE") or "spdci-extensions-dci:Farmer",
            search_text=os.environ.get("SANITY_DCI_SEARCH_TEXT") or "sanity",
            cm_staff_url=(os.environ.get("SANITY_CM_STAFF_URL") or "").rstrip("/"),
            cm_audience=os.environ.get("SANITY_CM_AUDIENCE") or "FR_SANITY_PARTNER",
            controller_id=os.environ.get("SANITY_CONTROLLER_ID") or "fr-sanity-controller",
            data_scopes=_list(
                os.environ.get("SANITY_DATA_SCOPES"),
                ["first_name", "last_name", "birth_date", "gender"],
            ),
            pm_partner_api_url=(os.environ.get("SANITY_PM_PARTNER_API_URL") or "").rstrip("/"),
            pm_admin_url=(os.environ.get("SANITY_PM_ADMIN_URL") or "").rstrip("/"),
            pm_admin_token_url=os.environ.get("SANITY_PM_ADMIN_TOKEN_URL", ""),
            pm_admin_client_id=os.environ.get("SANITY_PM_ADMIN_CLIENT_ID", "partner-management"),
            pm_admin_client_secret=os.environ.get("SANITY_PM_ADMIN_CLIENT_SECRET", ""),
            cm_auth_enabled=_bool(os.environ.get("SANITY_CM_AUTH_ENABLED"), True),
            cm_token_url=os.environ.get("SANITY_CM_TOKEN_URL", ""),
            cm_client_id=os.environ.get("SANITY_CM_CLIENT_ID", "consent-manager"),
            cm_client_secret=os.environ.get("SANITY_CM_CLIENT_SECRET", ""),
        )

    # Aliases so the reused CM pm_seed module (which reads cfg.token_url /
    # cfg.client_* as a fallback) works unchanged against this config.
    @property
    def token_url(self) -> str:
        return self.cm_token_url

    @property
    def client_id(self) -> str:
        return self.cm_client_id

    @property
    def client_secret(self) -> str:
        return self.cm_client_secret

    @property
    def can_reach_pm(self) -> bool:
        return bool(self.pm_partner_api_url)

    @property
    def can_reach_cm(self) -> bool:
        return bool(self.cm_staff_url)

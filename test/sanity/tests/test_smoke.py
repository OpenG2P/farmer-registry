import pytest

# Liveness + wiring for the Farmer Registry partner-api (the PEP). No auth, no
# data created — runs on every install/upgrade.


@pytest.mark.smoke
def test_partner_ping(partner_client):
    r = partner_client.get("/ping")
    assert r.status_code == 200, r.text


@pytest.mark.smoke
def test_openapi_has_dci_search(partner_client):
    r = partner_client.get("/openapi.json")
    assert r.status_code == 200, r.text
    paths = r.json().get("paths", {})
    assert any("/dci/registry" in p and p.endswith("/search") for p in paths), (
        f"DCI search route not found in openapi paths: {sorted(paths)[:20]}"
    )

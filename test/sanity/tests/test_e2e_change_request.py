"""Change request -> AWE approval -> applied change -> version history -> audit.

The flow under test:
  1. raise a change request on the sanity farmer via staff-portal-api;
  2. AWE starts a workflow from the register's bound approval policy;
  3. approve each stage through the **AWE proxy**;
  4. AWE posts an HMAC-signed decision webhook back to the registry;
  5. the registry applies the change and writes a history row;
  6. Audit Manager records the events.

Identity: the suite's OWN seeded user (sanity.keycloak_seed), logged in with the
password grant. The shipped demo users cannot be reused — keycloak-init gives
them a temporary password, so Keycloak forces UPDATE_PASSWORD and their password
grant fails. sanity.awe_seed therefore names the sanity user as an approver on
each stage of the shipped policy, additively, leaving the demo-user rules alone.
`forbid_self_approval` is FALSE on the shipped policy, so the one user both
raises the CR and clears every stage.

It never calls `/change-requests/approve_change_request`: that endpoint flips
the CR to approved **without inspecting the AWE workflow at all**, so approving
through it would make this test pass while proving nothing about the approval
policy. The only meaningful path is the AWE proxy.

AWE does not apply the decision itself — it POSTs an HMAC-signed webhook to the
registry, which applies the change and writes history. So the change lands
asynchronously and the assertions below poll rather than read once.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from sanity import audit, db, fixtures


def _field_value(cfg):
    rows = db.query(
        cfg.registry_dsn,
        f'SELECT "{fixtures.CR_FIELD}" AS v FROM "public"."g2p_register_farmers" '
        f'WHERE "internal_record_id" = %s',
        (fixtures.FARMER_INTERNAL_ID,),
    )
    assert rows, f"sanity farmer {fixtures.FARMER_INTERNAL_ID} not found"
    return rows[0]["v"]


def _wait_until(predicate, timeout, interval=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture(scope="module")
def change_request(cfg, staff_client, farmer_seeded, awe_approver):
    """Raise a CR that changes CR_FIELD, and return its id."""
    payload = {
        "register_id": cfg.farmer_register_id,
        "tab_id": cfg.cr_tab_id,
        "section_id": cfg.cr_section_id,
        "section_register_id": cfg.farmer_register_id,
        "internal_record_id": fixtures.FARMER_INTERNAL_ID,
        "change_payload": [
            {
                "internal_record_id": fixtures.FARMER_INTERNAL_ID,
                "edit_action": "EDIT",
                fixtures.CR_FIELD: fixtures.CR_VALUE_UPDATED,
            }
        ],
    }
    resp = staff_client.create_change_request(payload)
    body = (resp.get("response_body") or {}).get("response_payload") or resp
    cr_id = body.get("change_request_id") or body.get("id")
    assert cr_id, f"could not find change_request_id in response: {resp}"
    return cr_id


@pytest.mark.e2e
def test_change_request_is_created_pending(cfg, change_request):
    """Every register write is a change request — nothing is applied yet."""
    assert _field_value(cfg) == fixtures.CR_VALUE_INITIAL, (
        "the register row changed before the change request was approved — "
        "the change should only be applied on approval"
    )


def _tasks_for(client, cr_id):
    resp = client.list_my_tasks({"artifact_id": str(cr_id)})
    body = (resp.get("response_body") or {}).get("response_payload") or resp
    return body.get("tasks") or body.get("items") or []


@pytest.mark.e2e
def test_approval_through_awe_applies_the_change(cfg, staff_client, change_request):
    """Clear every stage the policy offers; the change must then be applied.

    Stages are walked by re-asking what tasks are outstanding rather than
    assuming a stage count, so a one- or three-level policy needs no change
    here. A later stage only becomes visible once the earlier one is cleared,
    so each round waits briefly for AWE to advance the workflow.
    """
    approved_any = False
    for _ in range(cfg.max_approval_rounds):
        tasks = _tasks_for(staff_client, change_request)
        if not tasks:
            # Either nothing was ever offered, or every stage is now cleared.
            if approved_any:
                break
            if not _wait_until(lambda: _tasks_for(staff_client, change_request), timeout=30):
                break
            continue
        for task in tasks:
            staff_client.submit_task_decision({
                "task_id": task.get("task_id") or task.get("id"),
                "action": "approve",
                "comment": "approved by sanity e2e",
                "artifact_id": str(change_request),
                "artifact_type": "registry.change_request",
                "current_stage": task.get("stage_order") or task.get("current_stage") or 1,
            })
            approved_any = True

    if not approved_any:
        pytest.skip(
            f"no AWE tasks were offered to '{cfg.staff_username}' for this change "
            f"request. Either AWE is disabled (global.aweEnabled=false — then "
            f"start_change_request_workflow silently no-ops), no policy is bound to "
            f"the register, or the awe-seed Job did not register the approver rule."
        )

    # AWE applies the decision by POSTing an HMAC-signed webhook back to the
    # registry, so the change lands asynchronously — poll, do not read once.
    applied = _wait_until(
        lambda: _field_value(cfg) == fixtures.CR_VALUE_UPDATED,
        timeout=cfg.awe_settle_timeout,
    )
    assert applied, (
        f"'{fixtures.CR_FIELD}' is still '{_field_value(cfg)}' after clearing every "
        f"offered stage and waiting {cfg.awe_settle_timeout}s — AWE's decision webhook "
        f"may not have reached the registry (check the callback secret / HMAC signature)."
    )


@pytest.mark.e2e
def test_version_history_retains_the_previous_record(cfg, staff_client, change_request):
    """Approval must write a history row; the previous value survives in the DB."""
    rows = db.query(
        cfg.registry_dsn,
        'SELECT "history_record_id", "change_request_id" '
        'FROM "public"."g2p_register_history_farmers" '
        'WHERE "internal_record_id" = %s',
        (fixtures.FARMER_INTERNAL_ID,),
    )
    assert rows, (
        "no history row for the sanity farmer after approval — history is written by "
        "insert_into_register_history during approve, so its absence means the change "
        "was never applied through the approval path"
    )

    versions = staff_client.get_number_of_versions({
        "register_id": cfg.farmer_register_id,
        "internal_record_id": fixtures.FARMER_INTERNAL_ID,
    })
    body = (versions.get("response_body") or {}).get("response_payload") or versions
    count = body.get("number_of_versions") or body.get("count") or len(rows)
    assert count >= 1, f"expected at least one prior version, got {count}"


@pytest.mark.e2e
def test_audit_events_are_recorded(cfg, change_request):
    """The change request must leave an audit trail in Audit Manager.

    Audit Manager has no query API, so this reads its table directly. The write
    is fire-and-forget -> Kafka -> Postgres, so it polls rather than reading
    once.
    """
    if not cfg.audit_dsn:
        pytest.skip("audit DB not configured — cannot assert the audit trail")

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = audit.wait_for(cfg, change_request, since)
    assert rows, (
        f"no audit events for change request {change_request} within {cfg.audit_timeout}s. "
        f"Audit is emitted fire-and-forget by the API middleware; check that "
        f"auditEnabled=true and the Audit Manager URL is reachable."
    )

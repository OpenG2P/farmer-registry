"""Make the sanity user an approver on the register's change-request policy.

Needed because the suite logs in as its **own** test user (see keycloak_seed.py
for why the shipped demo users cannot be used), and the shipped policy names
only those demo users — so without this the sanity user would never be offered a
task.

Approach — **additive, not an override.** The chart ships an active Farmer
change-request policy (`registry.change_request.farmer`, bound at REGISTER
scope, currently two stages owned by alex.carter / nina.patel). Rather than seed
a competing policy and rebind the register to it — which would silently change
behaviour for real change requests — this adds one extra `approver_rule` per
stage naming the sanity user. The shipped rules stay untouched, so:

  * the e2e exercises the **real** shipped policy, not a test-only stand-in;
  * it adapts to however many stages the policy has — the test walks whatever
    tasks it is offered, so 1 or 3 stages need no change here;
  * `forbid_self_approval` is already FALSE on the shipped policy, so the one
    sanity user can both raise the CR and clear every stage. If that is ever
    tightened, this suite needs a second seeded user.

Every rule carries the sanity marker in its `rule_value`, so the whole set is
removable with one predicate (see fixtures.TEARDOWN_SQL).
"""

import json
import uuid

from . import db, fixtures

# Deterministic namespace so re-running produces the same rule ids (idempotent).
_RULE_NS = uuid.UUID("5a117e2e-0000-4000-8000-000000000001")

_POLICY_FOR_REGISTER = """
SELECT policy_key
  FROM "public"."g2p_registry_awe_policy_configurations"
 WHERE policy_type = 'registry.change_request'
   AND policy_scope = 'REGISTER'
   AND register_id = %s
 LIMIT 1;
"""

_STAGES_FOR_POLICY = """
SELECT s.id, s.stage_order
  FROM "public"."approval_stage" s
  JOIN "public"."approval_policy" p ON p.id = s.policy_id
 WHERE p.policy_key = %s
   AND p.status = 'active'
 ORDER BY s.stage_order;
"""

_UPSERT_RULE = """
INSERT INTO "public"."approver_rule"
    ("id", "stage_id", "rule_type", "rule_value", "kind", "required", "created_at", "updated_at")
VALUES (%s, %s, 'user', %s, 'approver', FALSE, NOW(), NOW())
ON CONFLICT ("id") DO UPDATE SET "rule_value" = EXCLUDED."rule_value", "updated_at" = NOW();
"""


def policy_key_for_register(cfg) -> str:
    rows = db.query(cfg.registry_dsn, _POLICY_FOR_REGISTER, (cfg.farmer_register_id,))
    if not rows:
        raise RuntimeError(
            f"no REGISTER-scoped registry.change_request policy bound to register "
            f"{cfg.farmer_register_id} — AWE would no-op and the CR would never "
            f"reach a workflow"
        )
    return rows[0]["policy_key"]


def stages(cfg, policy_key):
    rows = db.query(cfg.awe_dsn, _STAGES_FOR_POLICY, (policy_key,))
    if not rows:
        raise RuntimeError(f"policy '{policy_key}' has no active stages")
    return rows


def ensure_approver(cfg) -> str:
    """Add the sanity user as an approver on every stage of the Farmer CR policy."""
    policy_key = policy_key_for_register(cfg)
    stage_rows = stages(cfg, policy_key)
    rule_value = json.dumps({"user_id": cfg.staff_username, "tag": fixtures.AWE_RULE_MARKER})
    for stage in stage_rows:
        rule_id = str(uuid.uuid5(_RULE_NS, f"{stage['id']}:{cfg.staff_username}"))
        db.execute(cfg.awe_dsn, _UPSERT_RULE, (rule_id, stage["id"], rule_value))
    return f"policy={policy_key} stages={len(stage_rows)}"


def main() -> int:
    """CLI entrypoint (`python -m sanity.awe_seed`) for the deploy-time Job."""
    from .config import Config

    cfg = Config.from_env()
    if not (cfg.registry_dsn and cfg.awe_dsn):
        print("[awe-seed] registry or AWE DB not configured — nothing to seed; skipping")
        return 0
    try:
        status = ensure_approver(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[awe-seed] FAILED to register approver '{cfg.staff_username}': {exc}")
        return 1
    print(f"[awe-seed] approver '{cfg.staff_username}' registered: {status}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

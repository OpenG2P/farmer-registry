-- dedup_register: clone a real change request whose farmer record exists.
-- deduplication_register_status = PENDING
-- deduplication_change_request_status = FAILED so the other dedup producer stays idle.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT cr.*
FROM g2p_register_change_requests cr
JOIN g2p_register_change_request_payloads p
  ON p.change_request_id = cr.change_request_id
JOIN g2p_register_farmers f
  ON f.internal_record_id = cr.internal_record_id
JOIN g2p_register_definitions d
  ON d.register_id = cr.register_id
WHERE cr.created_by IS NOT NULL
  AND cr.source_partner_id IS NOT NULL
  AND cr.section_id IS NOT NULL
  AND cr.change_request_id NOT LIKE '-perf-%'
  AND d.dedup_is_enabled
ORDER BY cr.created_at DESC
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'dedup_register needs one existing change request whose internal_record_id is in g2p_register_farmers, with a payload, on a register that has dedup enabled';
  END IF;
END $$;

DELETE FROM g2p_register_change_request_payloads
WHERE change_request_id LIKE '-perf-dedup-register-%';

DELETE FROM g2p_register_change_requests
WHERE change_request_id LIKE '-perf-dedup-register-%';

INSERT INTO g2p_register_change_requests (
  change_request_id, record_name, register_id, tab_id, section_id, section_register_id,
  internal_record_id, no_of_verifications_required, no_of_verifications_done,
  deduplication_register_status, deduplication_register_failure_reason,
  deduplication_change_request_status, deduplication_change_request_failure_reason,
  remarks, approval_status, created_at, approved_at, created_by, approved_by,
  change_request_source, source_partner_id
)
SELECT
  '-perf-dedup-register-' || lpad(g::text, 8, '0'),
  t.record_name, t.register_id, t.tab_id, t.section_id, t.section_register_id,
  t.internal_record_id, t.no_of_verifications_required, t.no_of_verifications_done,
  'PENDING', NULL,
  'FAILED', NULL,
  'celery-perf:dedup_register', 'APPROVED', now(), t.approved_at, t.created_by, t.approved_by,
  t.change_request_source, t.source_partner_id
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t;

INSERT INTO g2p_register_change_request_payloads (
  change_request_id, change_payload, search_text
)
SELECT
  '-perf-dedup-register-' || lpad(g::text, 8, '0'),
  p.change_payload,
  p.search_text
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
JOIN g2p_register_change_request_payloads p
  ON p.change_request_id = t.change_request_id;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM g2p_register_change_requests
  WHERE change_request_id LIKE '-perf-dedup-register-%'
    AND deduplication_register_status = 'PENDING'
    AND deduplication_change_request_status = 'FAILED';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'dedup_register inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'dedup_register pending rows: %', got;
END $$;

COMMIT;

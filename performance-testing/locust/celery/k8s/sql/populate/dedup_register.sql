-- dedup_register: new farmer rows, plus a change request for each one.
-- People are inserted only into g2p_register_farmers. Child tables are left alone.
-- Existing farmer rows are not updated. A rerun deletes only perf-farmer-* rows.
-- Every new farmer has first_name, last_name, and birth_date.
-- The first 1000 change requests match exactly two farmer rows: the row itself
-- and one copy with the same name and birth date. Each of those 1000 has its
-- own birth date and a name that is not a near-copy of the others.
-- Every later change request uses a name and birth date that no farmer has.
-- The change request sits on farmer personal identification.
-- deduplication_register_status = PENDING
-- deduplication_change_request_status = FAILED so the other dedup producer stays idle.
-- approval_status = APPROVED so change-request dedup does not treat these as candidates.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT cr.*
FROM g2p_register_change_requests cr
JOIN g2p_register_change_request_payloads p
  ON p.change_request_id = cr.change_request_id
JOIN g2p_register_definitions d
  ON d.register_id = cr.register_id
WHERE cr.created_by IS NOT NULL
  AND cr.source_partner_id IS NOT NULL
  AND cr.section_id IS NOT NULL
  AND cr.change_request_id NOT LIKE '-perf-%'
  AND d.dedup_is_enabled
ORDER BY cr.created_at DESC
LIMIT 1;

CREATE TEMP TABLE perf_actor ON COMMIT DROP AS
SELECT created_by, last_approved_by, record_status
FROM g2p_register_farmers
WHERE internal_record_id = (SELECT internal_record_id FROM perf_template);

CREATE TEMP TABLE perf_section ON COMMIT DROP AS
SELECT s.section_id, s.section_register_id, min(t.tab_id) AS tab_id
FROM g2p_register_sections s
JOIN g2p_register_ui_tab_sections t
  ON t.section_id = s.section_id
 AND t.register_id = s.register_id
WHERE s.section_id = 'farmer_farmer_personal_identification_section_01'
  AND s.register_id = (SELECT register_id FROM perf_template)
GROUP BY s.section_id, s.section_register_id;

CREATE TEMP TABLE perf_farmers ON COMMIT DROP AS
SELECT
  g,
  'perf-farmer-' || lpad(g::text, 8, '0') AS internal_record_id,
  CASE WHEN g <= 1000
    THEN substr(md5('fn-' || g::text), 1, 20)
    ELSE 'perfzxqfn' || lpad(g::text, 8, '0')
  END AS first_name,
  CASE WHEN g <= 1000
    THEN substr(md5('ln-' || g::text), 1, 20)
    ELSE 'perfzxqln' || lpad(g::text, 8, '0')
  END AS last_name,
  CASE WHEN g <= 1000
    THEN DATE '1217-03-01' + g
    ELSE DATE '1800-01-01'
  END AS birth_date,
  (g <= 1000) AS is_match
FROM generate_series(1, :count) AS g;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'dedup_register needs one existing change request with a payload on a register that has dedup enabled';
  END IF;
  IF (SELECT count(*) FROM perf_actor) <> 1 THEN
    RAISE EXCEPTION 'dedup_register needs the template farmer row for created_by and record_status';
  END IF;
  IF (SELECT count(*) FROM perf_section) <> 1 THEN
    RAISE EXCEPTION
      'dedup_register needs section farmer_farmer_personal_identification_section_01 on the register';
  END IF;
END $$;

DELETE FROM g2p_register_farmers
WHERE internal_record_id >= 'perf-farmer-'
  AND internal_record_id < 'perf-farmer.';

DELETE FROM deduplication_register_results
WHERE change_request_id LIKE '-perf-dedup-register-%';

DELETE FROM g2p_register_change_request_payloads
WHERE change_request_id LIKE '-perf-dedup-register-%';

DELETE FROM g2p_register_change_requests
WHERE change_request_id LIKE '-perf-dedup-register-%';

INSERT INTO g2p_register_farmers (
  internal_record_id, first_name, last_name, birth_date,
  record_name, search_text,
  created_by, created_at, last_approved_at, last_approved_by, record_status
)
SELECT
  f.internal_record_id, f.first_name, f.last_name, f.birth_date,
  f.first_name || ' ' || f.last_name,
  f.first_name || ' ' || f.last_name,
  a.created_by, now(), now(), a.last_approved_by, a.record_status
FROM perf_farmers f
CROSS JOIN perf_actor a;

INSERT INTO g2p_register_farmers (
  internal_record_id, first_name, last_name, birth_date,
  record_name, search_text,
  created_by, created_at, last_approved_at, last_approved_by, record_status
)
SELECT
  'perf-farmer-b' || lpad(f.g::text, 8, '0'),
  f.first_name, f.last_name, f.birth_date,
  f.first_name || ' ' || f.last_name,
  f.first_name || ' ' || f.last_name,
  a.created_by, now(), now(), a.last_approved_by, a.record_status
FROM perf_farmers f
CROSS JOIN perf_actor a
WHERE f.is_match;

INSERT INTO g2p_register_change_requests (
  change_request_id, record_name, register_id, tab_id, section_id, section_register_id,
  internal_record_id, no_of_verifications_required, no_of_verifications_done,
  deduplication_register_status, deduplication_register_failure_reason,
  deduplication_change_request_status, deduplication_change_request_failure_reason,
  remarks, approval_status, created_at, approved_at, created_by, approved_by,
  change_request_source, source_partner_id
)
SELECT
  '-perf-dedup-register-' || lpad(f.g::text, 8, '0'),
  t.record_name, t.register_id, s.tab_id, s.section_id, s.section_register_id,
  f.internal_record_id,
  t.no_of_verifications_required, t.no_of_verifications_done,
  'PENDING', NULL,
  'FAILED', NULL,
  'celery-perf:dedup_register', 'APPROVED', now(), t.approved_at, t.created_by, t.approved_by,
  t.change_request_source, t.source_partner_id
FROM perf_farmers f
CROSS JOIN perf_template t
CROSS JOIN perf_section s;

INSERT INTO g2p_register_change_request_payloads (
  change_request_id, change_payload, search_text
)
SELECT
  '-perf-dedup-register-' || lpad(f.g::text, 8, '0'),
  jsonb_build_array(jsonb_build_object(
    'edit_action', 'UPDATE',
    'internal_record_id', f.internal_record_id,
    'first_name', CASE WHEN f.is_match THEN f.first_name ELSE 'perfzxqnomatch' || lpad(f.g::text, 8, '0') END,
    'last_name', CASE WHEN f.is_match THEN f.last_name ELSE 'perfzxqnomatchln' || lpad(f.g::text, 8, '0') END,
    'birth_date', CASE WHEN f.is_match THEN to_char(f.birth_date, 'YYYY-MM-DD') ELSE '1801-01-01' END
  )),
  CASE WHEN f.is_match
    THEN f.first_name || ' ' || f.last_name
    ELSE 'perfzxqnomatch' || lpad(f.g::text, 8, '0')
  END
FROM perf_farmers f;

DO $$
DECLARE
  got int;
  farmers int;
  dupes int;
BEGIN
  SELECT count(*) INTO farmers
  FROM g2p_register_farmers
  WHERE internal_record_id >= 'perf-farmer-'
    AND internal_record_id < 'perf-farmer.';
  IF farmers <> (SELECT n + least(n, 1000) FROM perf_n) THEN
    RAISE EXCEPTION 'dedup_register inserted % farmers, wanted %',
      farmers, (SELECT n + least(n, 1000) FROM perf_n);
  END IF;
  SELECT count(*) INTO got
  FROM g2p_register_change_requests
  WHERE change_request_id LIKE '-perf-dedup-register-%'
    AND deduplication_register_status = 'PENDING'
    AND deduplication_change_request_status = 'FAILED'
    AND approval_status = 'APPROVED'
    AND section_id = 'farmer_farmer_personal_identification_section_01';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'dedup_register inserted % change requests, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  SELECT count(*) INTO dupes
  FROM g2p_register_change_request_payloads p
  JOIN g2p_register_farmers f
    ON f.internal_record_id = p.change_payload::jsonb -> 0 ->> 'internal_record_id'
   AND f.first_name = p.change_payload::jsonb -> 0 ->> 'first_name'
   AND f.last_name = p.change_payload::jsonb -> 0 ->> 'last_name'
   AND f.birth_date::text = p.change_payload::jsonb -> 0 ->> 'birth_date'
  WHERE p.change_request_id LIKE '-perf-dedup-register-%'
    AND f.internal_record_id >= 'perf-farmer-'
    AND f.internal_record_id < 'perf-farmer.';
  IF dupes <> (SELECT least(n, 1000) FROM perf_n) THEN
    RAISE EXCEPTION 'dedup_register seeded % matching payloads, wanted %',
      dupes, (SELECT least(n, 1000) FROM perf_n);
  END IF;
  IF (
    SELECT count(*)
    FROM (
      SELECT p.change_request_id
      FROM g2p_register_change_request_payloads p
      JOIN g2p_register_farmers f
        ON f.first_name = p.change_payload::jsonb -> 0 ->> 'first_name'
       AND f.last_name = p.change_payload::jsonb -> 0 ->> 'last_name'
       AND f.birth_date::text = p.change_payload::jsonb -> 0 ->> 'birth_date'
       AND f.internal_record_id >= 'perf-farmer-'
       AND f.internal_record_id < 'perf-farmer.'
      WHERE p.change_request_id LIKE '-perf-dedup-register-%'
        AND right(p.change_request_id, 8)::int <= 1000
      GROUP BY p.change_request_id
      HAVING count(*) = 2
    ) ok
  ) <> (SELECT least(n, 1000) FROM perf_n) THEN
    RAISE EXCEPTION 'a matching change request does not have exactly 2 farmer rows';
  END IF;
  RAISE NOTICE 'dedup_register farmers: %, pending change requests: %, matching payloads: %',
    farmers, got, dupes;
END $$;

COMMIT;

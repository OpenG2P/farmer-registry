-- dedup_change_request: same real farmer and register as an existing change request.
-- approval_status stays PENDING so the worker can see the cohort.
-- 5000 of the cohort share one real section_id from g2p_register_sections.
-- 20000 rows use 4 genuine sections. One of them is personal identification,
-- the section whose schema has first_name, last_name, and birth_date.
-- Inside every section, every 10th row copies one real payload so those rows
-- match each other. The other rows keep that section's keys with a unique value.
-- Every other change request is set to APPROVED so it is not in that list.
-- deduplication_register_status = FAILED so register dedup does not claim these rows.

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

CREATE TEMP TABLE perf_sections ON COMMIT DROP AS
SELECT section_id, section_register_id, tab_id, bucket
FROM (
  SELECT s.section_id,
         s.section_register_id,
         min(t.tab_id) AS tab_id,
         row_number() OVER (
           ORDER BY (s.section_id = 'farmer_farmer_personal_identification_section_01') DESC,
                    s.section_id
         ) - 1 AS bucket
  FROM g2p_register_sections s
  JOIN g2p_register_ui_tab_sections t
    ON t.section_id = s.section_id
   AND t.register_id = s.register_id
  WHERE s.register_id = (SELECT register_id FROM perf_template)
  GROUP BY s.section_id, s.section_register_id
) q
WHERE bucket < 4;

CREATE TEMP TABLE perf_section_payload ON COMMIT DROP AS
SELECT DISTINCT ON (s.section_id)
  s.section_id,
  s.bucket,
  CASE
    WHEN jsonb_typeof(p.change_payload::jsonb) = 'array' THEN p.change_payload::jsonb -> 0
    ELSE p.change_payload::jsonb
  END AS payload_object,
  p.search_text
FROM perf_sections s
JOIN g2p_register_change_requests cr
  ON cr.section_id = s.section_id
 AND cr.change_request_id NOT LIKE '-perf-%'
JOIN g2p_register_change_request_payloads p
  ON p.change_request_id = cr.change_request_id
WHERE s.section_id <> 'farmer_farmer_personal_identification_section_01'
ORDER BY s.section_id, cr.created_at DESC;

CREATE TEMP TABLE perf_match_farmer ON COMMIT DROP AS
SELECT btrim(first_name) AS first_name,
       btrim(last_name) AS last_name,
       birth_date::text AS birth_date,
       internal_record_id
FROM g2p_register_farmers
WHERE first_name IS NOT NULL AND btrim(first_name) <> ''
  AND last_name IS NOT NULL AND btrim(last_name) <> ''
  AND birth_date IS NOT NULL
  AND char_length(btrim(first_name)) >= 4
  AND char_length(btrim(last_name)) >= 4
ORDER BY internal_record_id
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'dedup_change_request needs one existing change request whose internal_record_id is in g2p_register_farmers, with a payload, on a register that has dedup enabled';
  END IF;
  IF (SELECT count(*) FROM perf_sections) <> 4 THEN
    RAISE EXCEPTION 'dedup_change_request needs 4 genuine sections on the register, found %',
      (SELECT count(*) FROM perf_sections);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM perf_sections
    WHERE section_id = 'farmer_farmer_personal_identification_section_01'
  ) THEN
    RAISE EXCEPTION
      'dedup_change_request needs section farmer_farmer_personal_identification_section_01';
  END IF;
  IF (SELECT count(*) FROM perf_section_payload) <> 3 THEN
    RAISE EXCEPTION 'each non-personal section needs one real change-request payload, found %',
      (SELECT count(*) FROM perf_section_payload);
  END IF;
  IF (SELECT count(*) FROM perf_match_farmer) <> 1 THEN
    RAISE EXCEPTION 'dedup_change_request needs one farmer with first_name, last_name, and birth_date';
  END IF;
END $$;

DELETE FROM deduplication_change_request_results
WHERE change_request_id LIKE '-perf-dedup-cr-%'
   OR candidate_change_request_id LIKE '-perf-dedup-cr-%';

DELETE FROM g2p_register_change_request_payloads
WHERE change_request_id LIKE '-perf-dedup-cr-%';

DELETE FROM g2p_register_change_requests
WHERE change_request_id LIKE '-perf-dedup-cr-%';

UPDATE g2p_register_change_requests
SET approval_status = 'APPROVED'
WHERE approval_status = 'PENDING'
  AND change_request_id NOT LIKE '-perf-dedup-cr-%';

INSERT INTO g2p_register_change_requests (
  change_request_id, record_name, register_id, tab_id, section_id, section_register_id,
  internal_record_id, no_of_verifications_required, no_of_verifications_done,
  deduplication_register_status, deduplication_register_failure_reason,
  deduplication_change_request_status, deduplication_change_request_failure_reason,
  remarks, approval_status, created_at, approved_at, created_by, approved_by,
  change_request_source, source_partner_id
)
SELECT
  '-perf-dedup-cr-' || lpad(g::text, 8, '0'),
  t.record_name, t.register_id, s.tab_id, s.section_id, s.section_register_id,
  CASE
    WHEN s.section_id = 'farmer_farmer_personal_identification_section_01' AND g % 10 = 0
      THEN f.internal_record_id
    ELSE t.internal_record_id
  END,
  t.no_of_verifications_required, t.no_of_verifications_done,
  'FAILED', NULL,
  'PENDING', NULL,
  'celery-perf:dedup_change_request', 'PENDING', now(), NULL, t.created_by, NULL,
  t.change_request_source, t.source_partner_id
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
CROSS JOIN perf_match_farmer f
JOIN perf_sections s ON s.bucket = (g - 1) / 5000;

INSERT INTO g2p_register_change_request_payloads (
  change_request_id, change_payload, search_text
)
SELECT
  '-perf-dedup-cr-' || lpad(g::text, 8, '0'),
  CASE
    WHEN s.section_id = 'farmer_farmer_personal_identification_section_01' THEN
      jsonb_build_array(jsonb_build_object(
        'edit_action', 'UPDATE',
        'internal_record_id', CASE WHEN g % 10 = 0 THEN f.internal_record_id ELSE t.internal_record_id END,
        'first_name', CASE WHEN g % 10 = 0 THEN f.first_name ELSE 'perfzxqfn' || lpad(g::text, 8, '0') END,
        'last_name', CASE WHEN g % 10 = 0 THEN f.last_name ELSE 'perfzxqln' || lpad(g::text, 8, '0') END,
        'birth_date', CASE WHEN g % 10 = 0 THEN f.birth_date ELSE '1800-01-01' END
      ))
    WHEN g % 10 = 0 THEN jsonb_build_array(sp.payload_object)
    ELSE jsonb_build_array((
      SELECT jsonb_object_agg(
        e.key,
        CASE
          WHEN e.key = 'edit_action' THEN e.value
          WHEN jsonb_typeof(e.value) = 'string'
            THEN to_jsonb('perfzxq' || lpad(g::text, 8, '0'))
          ELSE e.value
        END
      )
      FROM jsonb_each(sp.payload_object) e
    ))
  END,
  CASE
    WHEN s.section_id = 'farmer_farmer_personal_identification_section_01' AND g % 10 = 0
      THEN f.first_name || ' ' || f.last_name
    WHEN s.section_id = 'farmer_farmer_personal_identification_section_01'
      THEN 'perfzxqfn' || lpad(g::text, 8, '0')
    WHEN g % 10 = 0 THEN sp.search_text
    ELSE 'perfzxq' || lpad(g::text, 8, '0')
  END
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
CROSS JOIN perf_match_farmer f
JOIN perf_sections s ON s.bucket = (g - 1) / 5000
LEFT JOIN perf_section_payload sp ON sp.section_id = s.section_id;

DO $$
DECLARE
  got int;
  personal_matches int;
BEGIN
  SELECT count(*) INTO got
  FROM g2p_register_change_requests
  WHERE change_request_id LIKE '-perf-dedup-cr-%'
    AND deduplication_change_request_status = 'PENDING'
    AND deduplication_register_status = 'FAILED'
    AND approval_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'dedup_change_request inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  IF EXISTS (
    SELECT 1
    FROM g2p_register_change_requests
    WHERE approval_status = 'PENDING'
    GROUP BY section_id
    HAVING count(*) > 5000
  ) THEN
    RAISE EXCEPTION 'a section has more than 5000 approval-PENDING change requests';
  END IF;
  IF (SELECT n FROM perf_n) % 5000 = 0 AND EXISTS (
    SELECT 1
    FROM g2p_register_change_requests
    WHERE change_request_id LIKE '-perf-dedup-cr-%'
    GROUP BY section_id
    HAVING count(*) <> 5000
  ) THEN
    RAISE EXCEPTION 'a dedup_change_request section does not have 5000 rows';
  END IF;
  SELECT count(*) INTO personal_matches
  FROM g2p_register_change_requests cr
  JOIN g2p_register_change_request_payloads p
    ON p.change_request_id = cr.change_request_id
  WHERE cr.change_request_id LIKE '-perf-dedup-cr-%'
    AND cr.section_id = 'farmer_farmer_personal_identification_section_01'
    AND (p.change_payload::jsonb -> 0 ->> 'first_name') = (SELECT first_name FROM perf_match_farmer)
    AND (p.change_payload::jsonb -> 0 ->> 'last_name') = (SELECT last_name FROM perf_match_farmer)
    AND (p.change_payload::jsonb -> 0 ->> 'birth_date') = (SELECT birth_date FROM perf_match_farmer);
  IF personal_matches <> (
    SELECT count(*)
    FROM g2p_register_change_requests
    WHERE change_request_id LIKE '-perf-dedup-cr-%'
      AND section_id = 'farmer_farmer_personal_identification_section_01'
      AND right(change_request_id, 8)::int % 10 = 0
  ) THEN
    RAISE EXCEPTION 'personal section matched % rows, wanted the 10%% slice', personal_matches;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM g2p_register_change_requests cr
    JOIN g2p_register_change_request_payloads p
      ON p.change_request_id = cr.change_request_id
    WHERE cr.change_request_id LIKE '-perf-dedup-cr-%'
      AND cr.section_id <> 'farmer_farmer_personal_identification_section_01'
      AND right(cr.change_request_id, 8)::int % 10 <> 0
      AND p.change_payload::jsonb -> 0 = (
        SELECT payload_object FROM perf_section_payload sp WHERE sp.section_id = cr.section_id
      )
  ) THEN
    RAISE EXCEPTION 'a non-matching change request kept the shared section payload';
  END IF;
  RAISE NOTICE 'dedup_change_request pending rows: %, personal-section matches: %', got, personal_matches;
END $$;

COMMIT;

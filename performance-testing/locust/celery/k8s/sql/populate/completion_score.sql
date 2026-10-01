-- One queue row per farmer, on the farmer socio-economic section.
-- The section register is Farmer, so the worker reads g2p_register_farmers.
-- Household, crop, land, and membership sections are not used.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;

CREATE TEMP TABLE perf_section ON COMMIT DROP AS
SELECT s.section_id, parent.register_id
FROM g2p_register_sections s
JOIN g2p_register_definitions section_reg
  ON section_reg.register_id = s.section_register_id
JOIN g2p_register_definitions parent
  ON parent.register_mnemonic = 'Farmer'
WHERE s.section_id = 'farmer_farmer_socio_economic_and_health_section_04'
  AND section_reg.register_mnemonic = 'Farmer'
  AND s.is_list = false;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_section) <> 1 THEN
    RAISE EXCEPTION
      'completion_score needs the Farmer socio-economic section farmer_farmer_socio_economic_and_health_section_04';
  END IF;
END $$;

DELETE FROM g2p_completion_score_computation_queue
WHERE queue_id LIKE '-perf-completion-%';

INSERT INTO g2p_completion_score_computation_queue (
  queue_id, register_id, internal_record_id, section_id,
  change_request_id, submission_id,
  compute_status, compute_number_of_attempts
)
SELECT
  '-perf-completion-' || lpad(g::text, 8, '0'),
  sec.register_id,
  farmers.internal_record_id,
  sec.section_id,
  NULL,
  NULL,
  'PENDING',
  0
FROM (
  SELECT internal_record_id, row_number() OVER (ORDER BY internal_record_id) AS g
  FROM (
    SELECT internal_record_id
    FROM g2p_register_farmers
    ORDER BY internal_record_id
    LIMIT :count
  ) picked
) farmers
CROSS JOIN perf_section sec;

DO $$
DECLARE
  got int;
  farmer_sections int;
BEGIN
  SELECT count(*) INTO got
  FROM g2p_completion_score_computation_queue
  WHERE queue_id LIKE '-perf-completion-%' AND compute_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'completion_score inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;

  SELECT count(*) INTO farmer_sections
  FROM g2p_completion_score_computation_queue q
  JOIN g2p_register_sections s ON s.section_id = q.section_id
  JOIN g2p_register_definitions d ON d.register_id = s.section_register_id
  WHERE q.queue_id LIKE '-perf-completion-%'
    AND d.register_mnemonic = 'Farmer'
    AND q.register_id = (SELECT register_id FROM perf_section);
  IF farmer_sections <> got THEN
    RAISE EXCEPTION 'completion_score farmer section rows %, wanted %', farmer_sections, got;
  END IF;

  RAISE NOTICE 'completion_score pending farmer rows: %', got;
END $$;

COMMIT;

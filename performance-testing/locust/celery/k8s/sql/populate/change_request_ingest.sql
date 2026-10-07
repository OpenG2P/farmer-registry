-- UPDATE ingest. There is no classified UPDATE row to copy.
-- One existing farmer is the subject. The payload is the personal-identification
-- section, and that section must already have a tab on the farmer register.
-- transformation_status is PROCESSED, so the ingest producer routes these
-- rows to the change-request worker.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;

CREATE TEMP TABLE perf_subject ON COMMIT DROP AS
SELECT
  f.internal_record_id,
  d.register_id,
  s.section_id,
  s.section_mnemonic,
  p.data_model_id,
  p.semantic_pattern_id
FROM g2p_register_farmers f
JOIN g2p_register_definitions d
  ON lower(d.register_mnemonic) = 'farmer'
JOIN g2p_register_sections s
  ON s.section_id = 'farmer_farmer_personal_identification_section_01'
 AND s.section_register_id = d.register_id
 AND s.is_list = false
JOIN g2p_register_ui_tab_sections ts
  ON ts.section_id = s.section_id
 AND ts.register_id = d.register_id
JOIN g2p_register_ui_tabs t
  ON t.tab_id = ts.tab_id
 AND t.register_id = d.register_id
JOIN incoming_model_semantic_patterns p
  ON p.register_id = d.register_id
JOIN g2p_intake_form_definitions form
  ON form.form_id = p.intake_form_id
 AND form.form_mnemonic = 'farmer_ingestion_intake'
WHERE f.created_by IS NOT NULL
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_subject) <> 1 THEN
    RAISE EXCEPTION
      'change_request_ingest needs one farmer, the personal-identification section on a register tab, and the farmer ingestion semantic pattern';
  END IF;
END $$;

DELETE FROM incoming_enriched_transformed_data
WHERE ingest_id LIKE '-perf-ingest-upd-%';

DELETE FROM incoming_classified_data
WHERE ingest_id LIKE '-perf-ingest-upd-%';

INSERT INTO incoming_classified_data (
  ingest_id, data_model_id, partner_id, register_id, pipeline_action,
  section_id, internal_record_id, semantic_pattern_id,
  classified_date_time,
  transformation_status, transformation_number_of_attempts,
  ingestion_status, ingestion_number_of_attempts
)
SELECT
  '-perf-ingest-upd-' || lpad(g::text, 8, '0'),
  s.data_model_id, 'perf-ingest-partner', s.register_id, 'UPDATE',
  s.section_id, s.internal_record_id, s.semantic_pattern_id,
  now(),
  'PROCESSED', 1,
  'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_subject s;

INSERT INTO incoming_enriched_transformed_data (
  ingest_id, transformed_data_json
)
SELECT
  '-perf-ingest-upd-' || lpad(g::text, 8, '0'),
  jsonb_build_object(
    s.section_mnemonic,
    jsonb_build_array(
      jsonb_build_object(
        'first_name', 'Perf',
        'last_name', 'Ingest'
      )
    )
  )::json
FROM generate_series(1, :count) AS g
CROSS JOIN perf_subject s;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM incoming_classified_data
  WHERE ingest_id LIKE '-perf-ingest-upd-%'
    AND ingestion_status = 'PENDING'
    AND pipeline_action = 'UPDATE'
    AND transformation_status = 'PROCESSED';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'change_request_ingest inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'change_request_ingest pending rows: %', got;
END $$;

COMMIT;

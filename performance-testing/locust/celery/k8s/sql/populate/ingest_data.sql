-- ADD ingest. Uses one real classified row when the database has one.
-- This database has none, so the fallback builds the row from the farmer
-- ingestion form and its semantic pattern. The payload is one personal-info
-- record. The worker assigns a new internal_record_id for each task.
-- transformation_status is PROCESSED so the transformation producer does not claim it.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;

CREATE TEMP TABLE perf_source (
  data_model_id text,
  partner_id text,
  register_id text,
  pipeline_action text,
  section_id text,
  internal_record_id text,
  intake_form_id text,
  semantic_pattern_id text,
  transformed_data_json json
) ON COMMIT DROP;

INSERT INTO perf_source
SELECT
  c.data_model_id, c.partner_id, c.register_id, c.pipeline_action,
  c.section_id, c.internal_record_id, c.intake_form_id, c.semantic_pattern_id,
  e.transformed_data_json
FROM incoming_classified_data c
JOIN incoming_enriched_transformed_data e ON e.ingest_id = c.ingest_id
WHERE c.ingest_id NOT LIKE '-perf-%'
  AND c.partner_id IS NOT NULL
  AND c.pipeline_action IS DISTINCT FROM 'UPDATE'
  AND c.intake_form_id IS NOT NULL
  AND e.transformed_data_json IS NOT NULL
ORDER BY c.classified_date_time DESC
LIMIT 1;

INSERT INTO perf_source
SELECT
  p.data_model_id,
  'perf-ingest-partner',
  p.register_id,
  'ADD',
  NULL,
  NULL,
  p.intake_form_id,
  p.semantic_pattern_id,
  jsonb_build_object(
    s.section_mnemonic,
    jsonb_build_array(jsonb_build_object('first_name', 'Perf', 'last_name', 'Ingest'))
  )::json
FROM incoming_model_semantic_patterns p
JOIN g2p_intake_form_definitions f
  ON f.form_id = p.intake_form_id
 AND f.register_id = p.register_id
JOIN g2p_register_definitions d
  ON d.register_id = p.register_id
 AND d.register_mnemonic = 'Farmer'
JOIN g2p_register_sections s
  ON s.section_id = 'farmer_farmer_personal_identification_section_01'
 AND s.section_register_id = p.register_id
 AND s.is_list = false
WHERE f.form_mnemonic = 'farmer_ingestion_intake'
  AND NOT EXISTS (SELECT 1 FROM perf_source)
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_source) <> 1 THEN
    RAISE EXCEPTION
      'ingest_data needs either one existing non-UPDATE classified row, or the farmer_ingestion_intake form with a semantic pattern and the personal-identification section';
  END IF;
END $$;

DELETE FROM incoming_enriched_transformed_data
WHERE ingest_id LIKE '-perf-ingest-add-%';

DELETE FROM incoming_classified_data
WHERE ingest_id LIKE '-perf-ingest-add-%';

INSERT INTO incoming_classified_data (
  ingest_id, data_model_id, partner_id, register_id, pipeline_action,
  section_id, internal_record_id, intake_form_id, semantic_pattern_id,
  classified_date_time,
  transformation_status, transformation_number_of_attempts,
  ingestion_status, ingestion_number_of_attempts
)
SELECT
  '-perf-ingest-add-' || lpad(g::text, 8, '0'),
  t.data_model_id, t.partner_id, t.register_id, t.pipeline_action,
  t.section_id, t.internal_record_id, t.intake_form_id, t.semantic_pattern_id,
  now(),
  'PROCESSED', 1,
  'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_source t;

INSERT INTO incoming_enriched_transformed_data (
  ingest_id, transformed_data_json
)
SELECT
  '-perf-ingest-add-' || lpad(g::text, 8, '0'),
  t.transformed_data_json
FROM generate_series(1, :count) AS g
CROSS JOIN perf_source t;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM incoming_classified_data
  WHERE ingest_id LIKE '-perf-ingest-add-%'
    AND ingestion_status = 'PENDING'
    AND pipeline_action IS DISTINCT FROM 'UPDATE'
    AND transformation_status = 'PROCESSED';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'ingest_data inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'ingest_data pending rows: %', got;
END $$;

COMMIT;

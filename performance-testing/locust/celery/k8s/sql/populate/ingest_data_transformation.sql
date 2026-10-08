-- Classified ADD row plus the raw payload the transformer reads.
-- Uses the farmer DCI semantic pattern and requires the incoming template
-- for that data model and register. ingestion_status stays NOT_APPLICABLE
-- until the worker finishes and sets it to PENDING.
-- The business payload sits at
--   $.body.message.search_response[0].data.reg_records[0]
-- which is key_path_for_business_payload on that pattern.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;

CREATE TEMP TABLE perf_pattern ON COMMIT DROP AS
SELECT
  p.semantic_pattern_id,
  p.data_model_id,
  p.register_id,
  p.intake_form_id
FROM incoming_model_semantic_patterns p
JOIN g2p_intake_form_definitions f
  ON f.form_id = p.intake_form_id
 AND f.register_id = p.register_id
JOIN g2p_register_definitions d
  ON d.register_id = p.register_id
 AND d.register_mnemonic = 'Farmer'
JOIN incoming_templates t
  ON t.data_model_id = p.data_model_id
 AND t.register_id = p.register_id
WHERE f.form_mnemonic = 'farmer_ingestion_intake'
  AND p.key_path_for_business_payload = '$.body.message.search_response[0].data.reg_records[0]'
  AND p.raw_payload_enricher_class IS NOT NULL
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_pattern) <> 1 THEN
    RAISE EXCEPTION
      'ingest_data_transformation needs the farmer_ingestion_intake semantic pattern and an incoming template for that data model and register';
  END IF;
END $$;

DELETE FROM incoming_enriched_transformed_data
WHERE ingest_id LIKE '-perf-ingest-xform-%';

DELETE FROM incoming_classified_data
WHERE ingest_id LIKE '-perf-ingest-xform-%';

DELETE FROM incoming_raw_data_payloads
WHERE ingest_id LIKE '-perf-ingest-xform-%';

INSERT INTO incoming_raw_data_payloads (ingest_id, raw_data_json)
SELECT
  '-perf-ingest-xform-' || lpad(g::text, 8, '0'),
  jsonb_build_object(
    'body', jsonb_build_object(
      'header', jsonb_build_object(
        'message_id', '-perf-ingest-xform-' || lpad(g::text, 8, '0'),
        'sender_id', 'perf-ingest-partner'
      ),
      'message', jsonb_build_object(
        'search_response', jsonb_build_array(
          jsonb_build_object(
            'data', jsonb_build_object(
              'reg_type', 'Farmer',
              'reg_record_type', 'Farmer',
              'reg_records', jsonb_build_array(
                jsonb_build_object('first_name', 'Perf', 'last_name', 'Ingest')
              )
            )
          )
        )
      )
    )
  )::json
FROM generate_series(1, :count) AS g;

INSERT INTO incoming_classified_data (
  ingest_id, data_model_id, partner_id, register_id, pipeline_action,
  intake_form_id, semantic_pattern_id, classified_date_time,
  transformation_status, transformation_number_of_attempts,
  ingestion_status, ingestion_number_of_attempts
)
SELECT
  '-perf-ingest-xform-' || lpad(g::text, 8, '0'),
  p.data_model_id, 'perf-ingest-partner', p.register_id, 'ADD',
  p.intake_form_id, p.semantic_pattern_id, now(),
  'PENDING', 0,
  'NOT_APPLICABLE', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_pattern p;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM incoming_classified_data
  WHERE ingest_id LIKE '-perf-ingest-xform-%'
    AND transformation_status = 'PENDING'
    AND ingestion_status = 'NOT_APPLICABLE';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'ingest_data_transformation inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'ingest_data_transformation pending rows: %', got;
END $$;

COMMIT;

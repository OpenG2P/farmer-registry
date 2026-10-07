-- Raw ADD ingest for the farmer DCI semantic pattern.
-- There is no existing raw row to copy. The payload matches
-- incoming_model_semantic_patterns for farmer_ingestion_intake:
--   $.body.message.search_response[0].data.reg_type => ^Farmer$
--   $.body.message.search_response[0].data.reg_record_type => ^Farmer$
-- This data model has no register-semantic rows, so the worker uses that
-- legacy match and writes the classified row itself.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;

CREATE TEMP TABLE perf_pattern ON COMMIT DROP AS
SELECT
  p.semantic_pattern_id,
  p.data_model_id,
  p.register_id,
  p.intake_form_id,
  p.pattern_for_register,
  p.pattern_for_intake_form
FROM incoming_model_semantic_patterns p
JOIN g2p_intake_form_definitions f
  ON f.form_id = p.intake_form_id
 AND f.register_id = p.register_id
JOIN g2p_register_definitions d
  ON d.register_id = p.register_id
 AND d.register_mnemonic = 'Farmer'
WHERE f.form_mnemonic = 'farmer_ingestion_intake'
  AND p.pattern_for_register IS NOT NULL
  AND p.pattern_for_intake_form IS NOT NULL
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_pattern) <> 1 THEN
    RAISE EXCEPTION
      'ingest_data_classification needs the farmer_ingestion_intake semantic pattern';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM incoming_model_register_semantic_patterns r
    JOIN perf_pattern p ON p.data_model_id = r.data_model_id
  ) THEN
    RAISE EXCEPTION
      'ingest_data_classification builds a legacy ADD payload, and this data model has register semantic patterns';
  END IF;
END $$;

DELETE FROM incoming_enriched_transformed_data
WHERE ingest_id LIKE '-perf-ingest-class-%';

DELETE FROM incoming_classified_data
WHERE ingest_id LIKE '-perf-ingest-class-%';

DELETE FROM incoming_raw_data_payloads
WHERE ingest_id LIKE '-perf-ingest-class-%';

DELETE FROM incoming_raw_data
WHERE ingest_id LIKE '-perf-ingest-class-%';

INSERT INTO incoming_raw_data (
  ingest_id, partner_id, data_model_id, ingest_message_id, ingest_correlation_id,
  receipt_date_time, classification_status, classification_number_of_attempts
)
SELECT
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  'perf-ingest-partner',
  p.data_model_id,
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  now(), 'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_pattern p;

INSERT INTO incoming_raw_data_payloads (ingest_id, raw_data_json)
SELECT
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  jsonb_build_object(
    'body', jsonb_build_object(
      'header', jsonb_build_object(
        'message_id', '-perf-ingest-class-' || lpad(g::text, 8, '0'),
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

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM incoming_raw_data
  WHERE ingest_id LIKE '-perf-ingest-class-%'
    AND classification_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'ingest_data_classification inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'ingest_data_classification pending rows: %', got;
END $$;

COMMIT;

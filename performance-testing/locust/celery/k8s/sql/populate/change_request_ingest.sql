-- UPDATE ingest. The farmer record and the section must already exist.
-- transformation_status is PROCESSED, so only the ingest producer claims it,
-- and that producer routes UPDATE rows to the change-request worker.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT c.*
FROM incoming_classified_data c
JOIN incoming_enriched_transformed_data e ON e.ingest_id = c.ingest_id
JOIN g2p_register_farmers f ON f.internal_record_id = c.internal_record_id
JOIN g2p_register_sections s ON s.section_id = c.section_id
JOIN g2p_partners partner ON partner.partner_id = c.partner_id
WHERE c.ingest_id NOT LIKE '-perf-%'
  AND c.pipeline_action = 'UPDATE'
  AND e.transformed_data_json IS NOT NULL
ORDER BY c.classified_date_time DESC
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'change_request_ingest needs one UPDATE classified row whose internal_record_id is in g2p_register_farmers, with a section and transformed JSON';
  END IF;
END $$;

DELETE FROM incoming_enriched_transformed_data
WHERE ingest_id LIKE '-perf-ingest-upd-%';

DELETE FROM incoming_classified_data
WHERE ingest_id LIKE '-perf-ingest-upd-%';

INSERT INTO incoming_classified_data (
  ingest_id, data_model_id, partner_id, register_id, pipeline_action,
  section_id, internal_record_id, intake_form_id, semantic_pattern_id,
  classified_date_time,
  transformation_status, transformation_number_of_attempts,
  ingestion_status, ingestion_number_of_attempts
)
SELECT
  '-perf-ingest-upd-' || lpad(g::text, 8, '0'),
  t.data_model_id, t.partner_id, t.register_id, 'UPDATE',
  t.section_id, t.internal_record_id, t.intake_form_id, t.semantic_pattern_id,
  now(),
  'PROCESSED', 1,
  'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t;

INSERT INTO incoming_enriched_transformed_data (
  ingest_id, enriched_data_json, enriched_data_xml,
  transformed_data_json, transformed_data_xml
)
SELECT
  '-perf-ingest-upd-' || lpad(g::text, 8, '0'),
  e.enriched_data_json, e.enriched_data_xml,
  e.transformed_data_json, e.transformed_data_xml
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
JOIN incoming_enriched_transformed_data e ON e.ingest_id = t.ingest_id;

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

-- Copies a classified ingest and the raw payload the transformer reads.
-- ingestion_status is NOT_APPLICABLE, so the ingest producer does not claim
-- these rows until transformation itself sets ingestion to PENDING.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT c.*
FROM incoming_classified_data c
JOIN incoming_raw_data_payloads p ON p.ingest_id = c.ingest_id
JOIN g2p_partners partner ON partner.partner_id = c.partner_id
WHERE c.ingest_id NOT LIKE '-perf-%'
  AND c.semantic_pattern_id IS NOT NULL
  AND c.register_id IS NOT NULL
ORDER BY c.classified_date_time DESC
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'ingest_data_transformation needs one classified row with a raw payload and a real partner_id';
  END IF;
END $$;

DELETE FROM incoming_enriched_transformed_data
WHERE ingest_id LIKE '-perf-ingest-xform-%';

DELETE FROM incoming_classified_data
WHERE ingest_id LIKE '-perf-ingest-xform-%';

DELETE FROM incoming_raw_data_payloads
WHERE ingest_id LIKE '-perf-ingest-xform-%';

INSERT INTO incoming_raw_data_payloads (
  ingest_id, raw_data_json, raw_data_xml, raw_data_text
)
SELECT
  '-perf-ingest-xform-' || lpad(g::text, 8, '0'),
  p.raw_data_json, p.raw_data_xml, p.raw_data_text
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
JOIN incoming_raw_data_payloads p ON p.ingest_id = t.ingest_id;

INSERT INTO incoming_classified_data (
  ingest_id, data_model_id, partner_id, register_id, pipeline_action,
  section_id, internal_record_id, change_request_id, intake_form_id,
  semantic_pattern_id, classified_date_time,
  transformation_status, transformation_number_of_attempts,
  ingestion_status, ingestion_number_of_attempts
)
SELECT
  '-perf-ingest-xform-' || lpad(g::text, 8, '0'),
  t.data_model_id, t.partner_id, t.register_id, t.pipeline_action,
  t.section_id, t.internal_record_id, NULL, t.intake_form_id,
  t.semantic_pattern_id, now(),
  'PENDING', 0,
  'NOT_APPLICABLE', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t;

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

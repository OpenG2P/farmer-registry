-- ADD ingest. Copies a classified row that is not UPDATE, plus the transformed payload.
-- transformation_status is PROCESSED so the transformation producer does not claim it.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT c.*
FROM incoming_classified_data c
JOIN incoming_enriched_transformed_data e ON e.ingest_id = c.ingest_id
JOIN g2p_partners partner ON partner.partner_id = c.partner_id
WHERE c.ingest_id NOT LIKE '-perf-%'
  AND c.pipeline_action IS DISTINCT FROM 'UPDATE'
  AND c.intake_form_id IS NOT NULL
  AND e.transformed_data_json IS NOT NULL
ORDER BY c.classified_date_time DESC
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'ingest_data needs one non-UPDATE classified row with transformed JSON, an intake form, and a real partner_id';
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
CROSS JOIN perf_template t;

INSERT INTO incoming_enriched_transformed_data (
  ingest_id, enriched_data_json, enriched_data_xml,
  transformed_data_json, transformed_data_xml
)
SELECT
  '-perf-ingest-add-' || lpad(g::text, 8, '0'),
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

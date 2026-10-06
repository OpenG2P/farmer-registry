-- One queue row per CSV, matching play's farmer_sample_data.csv columns.
-- import_csv.sh uploads perf-import-00000001.csv and so on before this runs.
-- :count is the number of records in each file, up to 50000.
-- :files is the number of CSVs. One CSV is one Celery task.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n, :files::int AS files;

DO $$
BEGIN
  IF (SELECT n FROM perf_n) > 50000 THEN
    RAISE EXCEPTION 'import_file_process supports at most 50000 records in the CSV';
  END IF;
  IF (SELECT files FROM perf_n) > 20 THEN
    RAISE EXCEPTION 'import_file_process supports at most 20 CSV files';
  END IF;
END $$;

INSERT INTO data_models (
  data_model_id, data_model_mnemonic, pattern_for_data_model,
  response_template_document_id, is_active
)
VALUES (
  '088211ee-577c-4623-9cc8-ffb674f4ab4a',
  'IMPORT_FARMER_CSV',
  '*',
  NULL,
  true
)
ON CONFLICT (data_model_id) DO NOTHING;

INSERT INTO incoming_model_key_paths (
  key_path_id, data_model_id,
  key_path_for_message_id, key_path_for_sender, key_path_for_signature,
  key_path_for_signature_payload, is_list, key_path_for_list_elements
)
VALUES (
  '805860f3-06a2-43a3-9318-7f7b263d7ed3',
  '088211ee-577c-4623-9cc8-ffb674f4ab4a',
  '$.headers.message_id',
  '$.headers.sender_id',
  '$.headers.signature',
  '$.body',
  false,
  '*'
)
ON CONFLICT (data_model_id) DO NOTHING;

INSERT INTO incoming_model_semantic_patterns (
  semantic_pattern_id, data_model_id, register_id, intake_form_id,
  section_id, pattern_for_register, pattern_for_intake_form, pattern_for_section,
  key_path_for_business_payload, raw_payload_enricher_class
)
VALUES (
  '79ed478e-2f54-457b-a60b-c09f779ff331',
  '088211ee-577c-4623-9cc8-ffb674f4ab4a',
  'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
  'a1a4d25a-1cd4-4356-abac-8782382649',
  NULL,
  '*',
  '*',
  NULL,
  '$.body',
  'G2PDciFarmerCreateEnricherService'
)
ON CONFLICT (semantic_pattern_id) DO NOTHING;

DELETE FROM import_file_process_log
WHERE import_file_id LIKE '-perf-import-%';

DELETE FROM import_file_process_queue
WHERE import_file_id LIKE '-perf-import-%';

DELETE FROM g2p_registry_documents
WHERE document_id LIKE '-perf-import-doc-%';

INSERT INTO g2p_registry_documents (
  document_id, document_store_id, bucket, source_filename, created_by, created_at
)
SELECT
  '-perf-import-doc-' || lpad(g::text, 8, '0'),
  'perf-import-' || lpad(g::text, 8, '0') || '.csv',
  'documents',
  'farmer_sample_data.csv',
  'seeder',
  now()
FROM generate_series(1, :files) AS g;

INSERT INTO import_file_process_queue (
  import_file_id, document_id, data_model_id, register_id, intake_form_id,
  queued_at, queued_by,
  intake_form_ingestion_status, intake_form_ingestion_attempts,
  number_of_records_present
)
SELECT
  '-perf-import-' || lpad(g::text, 8, '0'),
  '-perf-import-doc-' || lpad(g::text, 8, '0'),
  '088211ee-577c-4623-9cc8-ffb674f4ab4a',
  'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
  'a1a4d25a-1cd4-4356-abac-8782382649',
  now(),
  'perf',
  'PENDING',
  0,
  :count
FROM generate_series(1, :files) AS g;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM import_file_process_queue q
  JOIN g2p_registry_documents d ON d.document_id = q.document_id
  JOIN data_models m ON m.data_model_id = q.data_model_id
  JOIN g2p_register_definitions r ON r.register_id = q.register_id
  JOIN g2p_intake_form_definitions f ON f.form_id = q.intake_form_id
  WHERE q.import_file_id LIKE '-perf-import-%'
    AND q.intake_form_ingestion_status = 'PENDING'
    AND q.number_of_records_present = (SELECT n FROM perf_n);
  IF got <> (SELECT files FROM perf_n) THEN
    RAISE EXCEPTION 'import_file_process queued % CSVs, wanted %', got, (SELECT files FROM perf_n);
  END IF;
  RAISE NOTICE 'import_file_process pending files: %, records each: %', got, (SELECT n FROM perf_n);
END $$;

COMMIT;

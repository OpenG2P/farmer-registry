-- document_id is unique and the file has to exist in storage.
-- This marks that many existing import rows PENDING. It does not invent files.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_imports ON COMMIT DROP AS
SELECT q.import_file_id
FROM import_file_process_queue q
JOIN g2p_registry_documents d ON d.document_id = q.document_id
JOIN data_models m ON m.data_model_id = q.data_model_id
JOIN g2p_register_definitions r ON r.register_id = q.register_id
JOIN g2p_intake_form_definitions f ON f.form_id = q.intake_form_id
ORDER BY q.queued_at
LIMIT :count;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got FROM perf_imports;
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION
      'import_file_process needs % existing import files whose document, data model, register, and intake form exist. Found %.',
      (SELECT n FROM perf_n), got;
  END IF;
END $$;

UPDATE import_file_process_queue q
SET intake_form_ingestion_status = 'PENDING',
    intake_form_ingestion_attempts = 0,
    intake_form_ingestion_error = NULL
FROM perf_imports p
WHERE q.import_file_id = p.import_file_id;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM import_file_process_queue q
  JOIN perf_imports p ON p.import_file_id = q.import_file_id
  WHERE q.intake_form_ingestion_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'import_file_process updated % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'import_file_process pending rows: %', got;
END $$;

COMMIT;

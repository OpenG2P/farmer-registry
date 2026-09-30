-- Beat selects each of these independently. Pending means the producer will enqueue it.
CREATE TEMP TABLE celery_case_def (
  name text PRIMARY KEY,
  table_name text NOT NULL,
  pk text NOT NULL,
  col text NOT NULL,
  extra text NOT NULL,
  park text NOT NULL
);

INSERT INTO celery_case_def (name, table_name, pk, col, extra, park) VALUES
  ('ingest_data_classification', 'incoming_raw_data', 'ingest_id', 'classification_status', 'TRUE', 'NOT_APPLICABLE'),
  ('ingest_data_transformation', 'incoming_classified_data', 'ingest_id', 'transformation_status', 'TRUE', 'NOT_APPLICABLE'),
  ('ingest_data', 'incoming_classified_data', 'ingest_id', 'ingestion_status', 'pipeline_action IS DISTINCT FROM ''UPDATE''', 'NOT_APPLICABLE'),
  ('change_request_ingest', 'incoming_classified_data', 'ingest_id', 'ingestion_status', 'pipeline_action = ''UPDATE''', 'NOT_APPLICABLE'),
  ('outgest_data_transformation', 'outgoing_raw_data', 'outgest_id', 'transformation_status', 'TRUE', 'NOT_APPLICABLE'),
  ('outgest_data_publish', 'outgoing_raw_data', 'outgest_id', 'publish_status', 'TRUE', 'NOT_APPLICABLE'),
  ('outgest_topic_register', 'outgoing_topics', 'topic_id', 'websub_register_status', 'TRUE', 'NOT_APPLICABLE'),
  ('dedup_register', 'g2p_register_change_requests', 'change_request_id', 'deduplication_register_status', 'TRUE', 'FAILED'),
  ('dedup_change_request', 'g2p_register_change_requests', 'change_request_id', 'deduplication_change_request_status', 'TRUE', 'FAILED'),
  ('dedup_intake_vs_register', 'g2p_intake_form_submissions', 'submission_id', 'deduplication_status_vs_register', 'draft_status = ''FINAL''', 'FAILED'),
  ('dedup_intake_vs_intake', 'g2p_intake_form_submissions', 'submission_id', 'deduplication_status_vs_intake_forms', 'draft_status = ''FINAL''', 'FAILED'),
  ('intake_register_ingest', 'g2p_intake_form_submissions', 'submission_id', 'register_ingest_process_status', 'approval_status = ''APPROVED''', 'NOT_APPLICABLE'),
  ('functional_id_allocation', 'g2p_functional_id_generation_queue', 'queue_id', 'id_allocation_status', 'TRUE', 'NOT_APPLICABLE'),
  ('functional_id_updation', 'g2p_functional_id_generation_queue', 'queue_id', 'id_updation_status', 'TRUE', 'NOT_APPLICABLE'),
  ('score_compute', 'g2p_score_compute_queue', 'queue_id', 'compute_status', 'TRUE', 'NOT_APPLICABLE'),
  ('completion_score', 'g2p_completion_score_computation_queue', 'queue_id', 'compute_status', 'TRUE', 'NOT_APPLICABLE'),
  ('import_file_process', 'import_file_process_queue', 'import_file_id', 'intake_form_ingestion_status', 'TRUE', 'NOT_APPLICABLE');

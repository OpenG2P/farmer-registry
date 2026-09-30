-- Copies a real completion-score queue row whose section and farmer record exist.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT q.*
FROM g2p_completion_score_computation_queue q
JOIN g2p_register_sections s ON s.section_id = q.section_id
JOIN g2p_register_farmers f ON f.internal_record_id = q.internal_record_id
WHERE q.queue_id NOT LIKE '-perf-%'
ORDER BY q.queue_id
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'completion_score needs one existing queue row whose section_id exists and whose internal_record_id is in g2p_register_farmers';
  END IF;
END $$;

DELETE FROM g2p_completion_score_computation_queue
WHERE queue_id LIKE '-perf-completion-%';

INSERT INTO g2p_completion_score_computation_queue (
  queue_id, register_id, internal_record_id, section_id,
  change_request_id, submission_id,
  compute_status, compute_number_of_attempts
)
SELECT
  '-perf-completion-' || lpad(g::text, 8, '0'),
  t.register_id, t.internal_record_id, t.section_id,
  t.change_request_id, t.submission_id,
  'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM g2p_completion_score_computation_queue
  WHERE queue_id LIKE '-perf-completion-%' AND compute_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'completion_score inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'completion_score pending rows: %', got;
END $$;

COMMIT;

-- One queue row per farmer that already has a functional_record_id.
-- Allocation status is COMPLETED, so the allocation producer does not claim these rows.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_farmers ON COMMIT DROP AS
SELECT f.internal_record_id, f.functional_record_id, d.register_id
FROM g2p_register_farmers f
CROSS JOIN (
  SELECT register_id
  FROM g2p_register_definitions
  WHERE lower(register_mnemonic) = 'farmer'
  LIMIT 1
) d
WHERE f.functional_record_id IS NOT NULL
  AND f.created_by IS NOT NULL
ORDER BY f.internal_record_id
LIMIT :count;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got FROM perf_farmers;
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION
      'functional_id_updation needs % farmers that already have functional_record_id, found %',
      (SELECT n FROM perf_n), got;
  END IF;
END $$;

DELETE FROM g2p_functional_id_generation_queue
WHERE queue_id LIKE '-perf-func-upd-%';

INSERT INTO g2p_functional_id_generation_queue (
  queue_id, register_id, internal_record_id,
  resolved_id, resolved_prefix, resolved_suffix,
  id_allocation_status, id_allocation_no_of_attempts,
  id_updation_status, id_updation_no_of_attempts
)
SELECT
  '-perf-func-upd-' || lpad(row_number() OVER (ORDER BY internal_record_id)::text, 8, '0'),
  register_id,
  internal_record_id,
  functional_record_id, NULL, NULL,
  'COMPLETED', 1,
  'PENDING', 0
FROM perf_farmers;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM g2p_functional_id_generation_queue
  WHERE queue_id LIKE '-perf-func-upd-%'
    AND id_updation_status = 'PENDING'
    AND id_allocation_status = 'COMPLETED';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'functional_id_updation inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'functional_id_updation pending rows: %', got;
END $$;

COMMIT;

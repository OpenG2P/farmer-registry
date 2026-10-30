DO $$
DECLARE
  r record;
  restored bigint;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'celery_perf_hold'
  ) THEN
    RAISE NOTICE 'celery_perf_hold does not exist. Nothing to restore.';
    RETURN;
  END IF;

  FOR r IN
    SELECT DISTINCT table_name, pk_column, column_name
    FROM celery_perf_hold
  LOOP
    EXECUTE format(
      'UPDATE %I AS t
       SET %I = h.previous_status
       FROM celery_perf_hold h
       WHERE h.table_name = %L
         AND h.pk_column = %L
         AND h.column_name = %L
         AND h.row_id = t.%I::text',
      r.table_name, r.column_name, r.table_name, r.pk_column, r.column_name, r.pk_column
    );
    GET DIAGNOSTICS restored = ROW_COUNT;
    RAISE NOTICE 'restored % rows for %.%', restored, r.table_name, r.column_name;
  END LOOP;

  DELETE FROM celery_perf_hold;
END $$;

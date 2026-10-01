CREATE TABLE IF NOT EXISTS celery_perf_cohort (
  row_id text PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS celery_perf_hold (
  held_at timestamptz DEFAULT now(),
  table_name text NOT NULL,
  pk_column text NOT NULL,
  row_id text NOT NULL,
  column_name text NOT NULL,
  previous_status text NOT NULL
);

DO $$
DECLARE
  keep_case text := '__KEEP_CASE__';
  keep_size int := __KEEP_SIZE__;
  r record;
  parked bigint;
BEGIN
  IF keep_size < 0 THEN
    RAISE EXCEPTION 'SIZE must be >= 0';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM celery_case_def WHERE name = keep_case) THEN
    RAISE EXCEPTION 'Unknown case %', keep_case;
  END IF;
  IF EXISTS (SELECT 1 FROM celery_perf_hold LIMIT 1) THEN
    RAISE EXCEPTION 'celery_perf_hold is not empty. Run restore-hold.sh before pinning another case.';
  END IF;

  TRUNCATE celery_perf_cohort;

  FOR r IN SELECT * FROM celery_case_def ORDER BY name LOOP
    -- A stopped run leaves rows INPROGRESS with no Redis message. Beat will not
    -- pick them up. Put them back to PENDING, then park with the rest.
    EXECUTE format(
      'UPDATE %I SET %I = ''PENDING''
       WHERE %I::text IN (''INPROGRESS'', ''PROCESSING'') AND (%s)',
      r.table_name, r.col, r.col, r.extra
    );

    IF r.name = keep_case THEN
      EXECUTE format(
        'INSERT INTO celery_perf_hold (table_name, pk_column, row_id, column_name, previous_status)
         SELECT %L, %L, %I::text, %L, %I
         FROM %I
         WHERE %I = ''PENDING'' AND (%s)
         ORDER BY %I
         OFFSET %s',
        r.table_name, r.pk, r.pk, r.col, r.col, r.table_name, r.col, r.extra, r.pk, keep_size
      );
      EXECUTE format(
        'UPDATE %I SET %I = %L
         WHERE %I IN (
           SELECT %I FROM %I
           WHERE %I = ''PENDING'' AND (%s)
           ORDER BY %I
           OFFSET %s
         )',
        r.table_name, r.col, r.park, r.pk, r.pk, r.table_name, r.col, r.extra, r.pk, keep_size
      );
      GET DIAGNOSTICS parked = ROW_COUNT;
      EXECUTE format(
        'INSERT INTO celery_perf_cohort (row_id)
         SELECT %I::text FROM %I
         WHERE %I = ''PENDING'' AND (%s)',
        r.pk, r.table_name, r.col, r.extra
      );
    ELSE
      EXECUTE format(
        'INSERT INTO celery_perf_hold (table_name, pk_column, row_id, column_name, previous_status)
         SELECT %L, %L, %I::text, %L, %I
         FROM %I
         WHERE %I = ''PENDING'' AND (%s)',
        r.table_name, r.pk, r.pk, r.col, r.col, r.table_name, r.col, r.extra
      );
      EXECUTE format(
        'UPDATE %I SET %I = %L
         WHERE %I = ''PENDING'' AND (%s)',
        r.table_name, r.col, r.park, r.col, r.extra
      );
      GET DIAGNOSTICS parked = ROW_COUNT;
    END IF;
    RAISE NOTICE 'parked % rows for %', parked, r.name;
  END LOOP;
END $$;

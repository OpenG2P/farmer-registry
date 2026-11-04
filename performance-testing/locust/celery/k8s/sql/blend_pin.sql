-- Keep one isolated backlog per blend case. Park the overflow of that case only.
-- A case with no row in celery_blend_size is parked entirely.
-- celery_perf_blend remembers the rows this run counts.

CREATE TABLE IF NOT EXISTS celery_perf_hold (
  held_at timestamptz DEFAULT now(),
  table_name text NOT NULL,
  pk_column text NOT NULL,
  row_id text NOT NULL,
  column_name text NOT NULL,
  previous_status text NOT NULL
);

CREATE TABLE IF NOT EXISTS celery_perf_blend (
  case_name text NOT NULL,
  row_id text NOT NULL,
  PRIMARY KEY (case_name, row_id)
);

DO $$
DECLARE
  r record;
  parked bigint;
  kept bigint;
BEGIN
  IF to_regclass('public.celery_perf_hold') IS NOT NULL
     AND EXISTS (SELECT 1 FROM celery_perf_hold LIMIT 1) THEN
    RAISE EXCEPTION 'celery_perf_hold is not empty. Restore before a blend pin.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM celery_blend_size) THEN
    RAISE EXCEPTION 'blend pin has no sizes';
  END IF;

  TRUNCATE celery_perf_blend;

  FOR r IN
    SELECT d.name, d.table_name, d.pk, d.col, d.extra, d.park, d.prefer, s.keep_size
    FROM celery_case_def d
    LEFT JOIN celery_blend_size s ON s.name = d.name
    ORDER BY d.name
  LOOP
    EXECUTE format(
      'UPDATE %I SET %I = ''PENDING''
       WHERE %I::text IN (''INPROGRESS'', ''PROCESSING'') AND (%s)',
      r.table_name, r.col, r.col, r.extra
    );

    IF r.keep_size IS NULL THEN
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
      RAISE NOTICE 'parked % rows for % (left out of this blend)', parked, r.name;
    ELSE
      EXECUTE format(
        'INSERT INTO celery_perf_hold (table_name, pk_column, row_id, column_name, previous_status)
         SELECT %L, %L, %I::text, %L, %I
         FROM %I
         WHERE %I = ''PENDING'' AND (%s)
         ORDER BY (CASE WHEN %I::text LIKE %L THEN 0 ELSE 1 END), %I
         OFFSET %s',
        r.table_name, r.pk, r.pk, r.col, r.col, r.table_name, r.col, r.extra, r.pk, r.prefer, r.pk, r.keep_size
      );
      EXECUTE format(
        'UPDATE %I SET %I = %L
         WHERE %I IN (
           SELECT %I FROM %I
           WHERE %I = ''PENDING'' AND (%s)
           ORDER BY (CASE WHEN %I::text LIKE %L THEN 0 ELSE 1 END), %I
           OFFSET %s
         )',
        r.table_name, r.col, r.park, r.pk, r.pk, r.table_name, r.col, r.extra, r.pk, r.prefer, r.pk, r.keep_size
      );
      GET DIAGNOSTICS parked = ROW_COUNT;
      EXECUTE format(
        'INSERT INTO celery_perf_blend (case_name, row_id)
         SELECT %L, %I::text FROM %I
         WHERE %I = ''PENDING'' AND (%s)',
        r.name, r.pk, r.table_name, r.col, r.extra
      );
      GET DIAGNOSTICS kept = ROW_COUNT;
      RAISE NOTICE 'blend % kept % parked %', r.name, kept, parked;
    END IF;
  END LOOP;
END $$;

SELECT case_name, count(*) AS kept
FROM celery_perf_blend
GROUP BY case_name
ORDER BY case_name;

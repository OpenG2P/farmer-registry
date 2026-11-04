"""Runs inside the partner-api pod. Prints functional ids, one per line.

No names, birth dates, or other columns.
"""
import os
import sys

import psycopg2

LIMIT = int(os.environ.get("FID_POOL_SIZE", "100000"))

conn = psycopg2.connect(
    host=os.environ["REGISTRY_PARTNER_API_DB_HOSTNAME"],
    port=os.environ["REGISTRY_PARTNER_API_DB_PORT"],
    dbname=os.environ["REGISTRY_PARTNER_API_DB_DBNAME"],
    user=os.environ["REGISTRY_PARTNER_API_DB_USERNAME"],
    password=os.environ["REGISTRY_PARTNER_API_DB_PASSWORD"],
)
cur = conn.cursor()
cur.execute(
    """
    SELECT functional_record_id
    FROM g2p_register_farmers
    WHERE functional_record_id >= 'FR-'
      AND functional_record_id < 'FS-'
    ORDER BY functional_record_id
    LIMIT %s
    """,
    (LIMIT,),
)
count = 0
seen = set()
for (fid,) in cur:
    value = fid.strip()
    if not value or value in seen:
        continue
    seen.add(value)
    sys.stdout.write(value + "\n")
    count += 1
print("fid_rows", count, file=sys.stderr)
if count < LIMIT:
    sys.exit(f"only {count} functional ids; need {LIMIT}")

"""Runs inside the partner-api pod. Prints hub/topic status, then a CSV pool."""
import csv
import os
import sys
import uuid
from datetime import datetime

import httpx
import psycopg2

topic = os.environ.get("TOPIC_URL", "http://websub/topics/PARTNER_STAFF_PORTAL")
hub = os.environ["REGISTRY_PARTNER_API_WEBSUB_BASE_URL"].rstrip("/") + "/hub/"

response = httpx.post(hub, data={"hub.mode": "register", "hub.topic": topic}, timeout=10.0)
body = response.text[:300].replace("\n", " ")
print("hub_register", response.status_code, body, file=sys.stderr)
already = "already registered" in body.lower()
denied = "denied" in body.lower() and "hub.mode" in body.lower() and not already
if response.status_code >= 400 or denied:
    sys.exit("websub hub rejected topic register")

conn = psycopg2.connect(
    host=os.environ["REGISTRY_PARTNER_API_DB_HOSTNAME"],
    port=os.environ["REGISTRY_PARTNER_API_DB_PORT"],
    dbname=os.environ["REGISTRY_PARTNER_API_DB_DBNAME"],
    user=os.environ["REGISTRY_PARTNER_API_DB_USERNAME"],
    password=os.environ["REGISTRY_PARTNER_API_DB_PASSWORD"],
)
conn.autocommit = True
cur = conn.cursor()
# Live perftest schema predates PARTNER topics. Add the columns the running
# partner-api model selects, then mark existing rows as REGISTER.
cur.execute("ALTER TABLE outgoing_topics ADD COLUMN IF NOT EXISTS topic_type varchar NOT NULL DEFAULT 'REGISTER'")
cur.execute("ALTER TABLE outgoing_topics ADD COLUMN IF NOT EXISTS partner_id varchar")
cur.execute("ALTER TABLE outgoing_topics ALTER COLUMN register_id DROP NOT NULL")
cur.execute("ALTER TABLE outgoing_topics ALTER COLUMN data_model_id DROP NOT NULL")
cur.execute("CREATE INDEX IF NOT EXISTS ix_outgoing_topics_partner_id ON outgoing_topics (partner_id)")
cur.execute("ALTER TABLE outgoing_topics DROP CONSTRAINT IF EXISTS ck_outgoing_topics_type_ids")
cur.execute(
    """
    ALTER TABLE outgoing_topics ADD CONSTRAINT ck_outgoing_topics_type_ids CHECK (
        (topic_type = 'REGISTER' AND register_id IS NOT NULL AND data_model_id IS NOT NULL AND partner_id IS NULL)
        OR (topic_type = 'PARTNER' AND partner_id IS NOT NULL AND partner_id <> '' AND register_id IS NULL AND data_model_id IS NULL)
    )
    """
)
cur.execute(
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uix_outgoing_topics_partner
    ON outgoing_topics (partner_id) WHERE topic_type = 'PARTNER'
    """
)
now = datetime.now()
cur.execute(
    """
    INSERT INTO outgoing_topics (
        topic_id, topic_type, partner_id, websub_topic, description, is_active,
        created_at, websub_register_status, websub_register_datetime,
        websub_register_number_of_attempts
    ) VALUES (%s, 'PARTNER', 'PARTNER_STAFF_PORTAL', %s, %s, true, %s, 'PROCESSED', %s, 1)
    ON CONFLICT (partner_id) WHERE topic_type = 'PARTNER'
    DO UPDATE SET
        websub_topic = EXCLUDED.websub_topic,
        is_active = true,
        websub_register_status = 'PROCESSED',
        websub_register_datetime = EXCLUDED.websub_register_datetime,
        updated_at = EXCLUDED.websub_register_datetime
    """,
    (str(uuid.uuid4()), topic, "perftest Staff Portal async search", now, now),
)
cur.execute(
    """
    SELECT websub_topic, is_active, websub_register_status
    FROM outgoing_topics
    WHERE topic_type = 'PARTNER' AND partner_id = 'PARTNER_STAFF_PORTAL'
    """
)
print("topic_row", cur.fetchone(), file=sys.stderr)

cur.execute(
    """
    SELECT functional_record_id, foundational_id, first_name, last_name, birth_date::text
    FROM g2p_register_farmers
    WHERE functional_record_id >= 'FR-'
    ORDER BY functional_record_id
    LIMIT 20000
    """
)
kept = []
for fid, found, first, last, birth in cur.fetchall():
    if not (fid and found and first and last and birth):
        continue
    if len(first) < 3 or len(last) < 4:
        continue
    kept.append((fid, found, first, last, birth[:10]))
    if len(kept) >= 10000:
        break
print("pool_rows", len(kept), file=sys.stderr)
writer = csv.writer(sys.stdout)
writer.writerow(["functional_record_id", "foundational_id", "first_name", "last_name", "birth_date"])
writer.writerows(kept)

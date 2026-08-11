#!/usr/bin/env python3
"""Prints a row count per register/history table and writes the same as CSV
to locust/api/results/{VOLUME_TIER}_records.csv.

VOLUME_TIER comes from the environment -- source locust/api/env.sh first.
The DB connection comes from SEED_DB_DSN -- source seeding/dsn.sh first.

Usage:
    source ../locust/api/env.sh
    source ../seeding/dsn.sh
    python capture_volume.py
"""
import csv
import os
from pathlib import Path

import psycopg2
from psycopg2 import sql

TABLES = [
    "g2p_register_farmers",
    "g2p_register_crops",
    "g2p_register_farm_inputs",
    "g2p_register_households",
    "g2p_register_household_members",
    "g2p_register_lands",
    "g2p_register_livestocks",
    "g2p_register_history_farmers",
    "g2p_register_history_crops",
    "g2p_register_history_farm_inputs",
    "g2p_register_history_households",
    "g2p_register_history_household_members",
    "g2p_register_history_lands",
    "g2p_register_history_livestocks",
]

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR.parent / "locust" / "api" / "results"


def main():
    volume_tier = os.environ.get("VOLUME_TIER")
    if not volume_tier:
        raise SystemExit("VOLUME_TIER is not set -- source locust/api/env.sh first")

    dsn = os.environ.get("SEED_DB_DSN")
    if not dsn:
        raise SystemExit("SEED_DB_DSN is not set -- source seeding/dsn.sh first")

    conn = psycopg2.connect(dsn)
    try:
        counts = []
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(sql.SQL("SELECT COUNT(1) FROM {}").format(sql.Identifier(table)))
                counts.append((table, cur.fetchone()[0]))
    finally:
        conn.close()

    out_path = RESULTS_DIR / f"{volume_tier}_records.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Table_Name", "Number_of_Records"])
        writer.writerows(counts)
        for table, count in counts:
            print(f"{table},{count}")

    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()

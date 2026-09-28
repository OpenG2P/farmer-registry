#!/usr/bin/env python3
"""CLI entrypoint for the bulk seed generator. See README.md for the full
flow and design rationale. Usage:

    cd performance-testing/seeding
    python run.py --tier smoke
    python run.py --tier primary --dsn postgresql://...
    python run.py --tier primary --pod-index 0 --total-pods 2 --workers 4
"""

import argparse
import multiprocessing as mp
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import db
from db import log
from common import RANDOM_SEED
from generators import (
    crop, farm_inputs, farmer, history, household, household_member,
    land, livestock, membership_details,
)
from id_scheme import init_pod_id_scheme
from search_anchors import load_or_generate_anchors
from seed_manifest import ManifestBuilder

CHILD_GENERATORS = {
    "land": land.generate,
    "livestock": livestock.generate,
    "farm_inputs": farm_inputs.generate,
    "membership_details": membership_details.generate,
}


def per_parent_count(table_key: str) -> int:
    _, _, span = config.RATIOS[table_key]
    return random.randint(*span)


class TableSink:
    """One BatchWriter for the live table, one for its history twin, plus
    the tab/section lookup history rows need."""

    def __init__(self, conn, table_key: str, cursor_for_metadata):
        live_table, history_table, mnemonic = config.TABLE_NAMES[table_key]
        self.table_key = table_key
        self.mnemonic = mnemonic
        self.conn = conn
        self.live_table = live_table
        self.history_table = history_table
        self.live_writer = None
        self.history_writer = None
        self.tab_sections = history.load_tab_sections(cursor_for_metadata, mnemonic)
        self.live_count = 0
        self.history_count = 0

    def write_live(self, row: dict):
        if self.live_writer is None:
            self.live_writer = db.BatchWriter(self.conn, self.live_table, list(row.keys()))
        self.live_writer.add(row)
        self.live_count += 1

        # Every live insert gets a corresponding history insert (1:1, not a
        # sample) -- tab_id/section_id come from load_tab_sections(), i.e.
        # real g2p_register_sections/g2p_register_ui_tab_sections metadata,
        # not invented values.
        history_row = history.generate(row, self.tab_sections)
        if self.history_writer is None:
            self.history_writer = db.BatchWriter(self.conn, self.history_table, list(history_row.keys()))
        self.history_writer.add(history_row)
        self.history_count += 1

    def flush(self):
        if self.live_writer:
            self.live_writer.flush()
        if self.history_writer:
            self.history_writer.flush()


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _progress_line(shard_index: int, farmers_written: int, target_farmers: int, elapsed: float, sinks: dict) -> str:
    rate = farmers_written / elapsed if elapsed else 0
    remaining = max(0, target_farmers - farmers_written)
    eta = remaining / rate if rate else 0
    live = sum(s.live_count for s in sinks.values())
    hist = sum(s.history_count for s in sinks.values())
    pct = (100.0 * farmers_written / target_farmers) if target_farmers else 100
    return (
        f"[seed] shard={shard_index} farmers={farmers_written}/{target_farmers} "
        f"({pct:.1f}%) {rate:.0f} farmers/s eta={_fmt_duration(eta)} "
        f"elapsed={_fmt_duration(elapsed)} live_rows={live} history_rows={hist}"
    )


def _shard_farmer_target(total_target_farmers: int, shard_index: int, total_shards: int) -> int:
    farmers_per_shard = total_target_farmers // total_shards
    if shard_index == total_shards - 1:
        return total_target_farmers - (shard_index * farmers_per_shard)
    return farmers_per_shard


def generate_shard(
    tier: str,
    dsn_override: str | None,
    shard_index: int,
    total_shards: int,
    total_target_farmers: int,
):
    if dsn_override:
        config.DB_DSN = dsn_override

    random.seed(RANDOM_SEED + shard_index)
    target_farmers = _shard_farmer_target(total_target_farmers, shard_index, total_shards)
    log(
        f"[seed] shard start tier={tier} shard={shard_index}/{total_shards} "
        f"target_farmers={target_farmers} of total={total_target_farmers}"
    )

    init_pod_id_scheme(shard_index, total_shards, total_target_farmers)
    anchors, anchor_source = load_or_generate_anchors()
    log(
        f"[seed] shard={shard_index} anchors={len(anchors)} source={anchor_source} "
        f"id_block_start={shard_index * int(os.environ.get('SEED_ID_BLOCK', '100000000'))}"
    )
    if not anchors:
        raise RuntimeError("no search anchors loaded or generated")
    expected_hits = (
        total_target_farmers // len(anchors) if anchors else 0
    )
    log(
        f"[seed] shard={shard_index} expected_hits_per_term_global≈{expected_hits} "
        f"(pod_share≈{target_farmers // len(anchors) if anchors else 0})"
    )
    manifest = ManifestBuilder(
        search_terms=anchors,
        data_volume=tier,
        pod_index=shard_index,
        total_pods=total_shards,
    )

    conn = db.connect()
    db.configure_bulk_session(conn)
    metadata_cursor = conn.cursor()
    sinks = {key: TableSink(conn, key, metadata_cursor) for key in config.TABLE_NAMES}
    metadata_cursor.close()
    conn.commit()

    start = time.time()
    farmers_written = 0
    last_reported = 0
    last_report_at = start
    report_every_farmers = max(1, config.BATCH_SIZE)
    report_every_seconds = 30

    while farmers_written < target_farmers:
        household_row = household.generate()
        sinks["household"].write_live(household_row)
        manifest.observe_household(household_row["internal_record_id"])

        for _ in range(per_parent_count("household_member")):
            member_row = household_member.generate(household_row)
            sinks["household_member"].write_live(member_row)

        for _ in range(per_parent_count("farmer")):
            if farmers_written >= target_farmers:
                break
            farmer_row = farmer.generate(household_row, anchors)
            sinks["farmer"].write_live(farmer_row)
            manifest.observe_farmer(farmer_row["internal_record_id"])
            farmers_written += 1

            for _ in range(per_parent_count("land")):
                land_row = land.generate(farmer_row)
                sinks["land"].write_live(land_row)
                for _ in range(per_parent_count("crop")):
                    crop_row = crop.generate(land_row)
                    sinks["crop"].write_live(crop_row)

            for table_key in ("livestock", "farm_inputs", "membership_details"):
                for _ in range(per_parent_count(table_key)):
                    row = CHILD_GENERATORS[table_key](farmer_row)
                    sinks[table_key].write_live(row)

        now = time.time()
        if (
            farmers_written - last_reported >= report_every_farmers
            or now - last_report_at >= report_every_seconds
        ):
            last_reported = farmers_written
            last_report_at = now
            log(_progress_line(shard_index, farmers_written, target_farmers, now - start, sinks))

    log(f"[seed] shard={shard_index} flushing remaining COPY buffers")
    for sink in sinks.values():
        sink.flush()
    conn.commit()

    manifest.write(config.SEED_MANIFEST_PATH)
    for key, sink in sinks.items():
        log(f"[seed] shard={shard_index} {key}: live={sink.live_count} history={sink.history_count}")
    conn.close()
    log(
        f"[seed] shard={shard_index} COPY done in {_fmt_duration(time.time() - start)} "
        f"farmers={farmers_written}"
    )


def run(
    tier: str,
    dsn_override: str | None,
    pod_index: int = 0,
    total_pods: int = 1,
    workers: int = 1,
):
    if dsn_override:
        config.DB_DSN = dsn_override

    total_target_farmers = int(os.environ.get("SEED_TARGET_FARMERS") or 0) or config.DATA_VOLUME_TIERS[tier]
    workers = max(1, workers)
    total_shards = total_pods * workers
    writer_id = f"pod{pod_index}"

    log(
        f"[seed] pod start tier={tier} total_target={total_target_farmers} "
        f"pod={pod_index}/{total_pods} workers={workers} shards={total_shards} "
        f"defer_indexes={config.DEFER_INDEXES} batch_size={config.BATCH_SIZE}"
    )

    parent_conn = db.connect()
    db.configure_bulk_session(parent_conn)
    if config.DEFER_INDEXES:
        log("[seed] deferring non-PK indexes for live + history tables")
        db.begin_deferred_indexes(parent_conn, writer_id)

    start = time.time()
    if workers == 1:
        parent_conn.close()
        generate_shard(tier, dsn_override, pod_index, total_pods, total_target_farmers)
        parent_conn = db.connect()
        db.configure_bulk_session(parent_conn)
    else:
        parent_conn.close()
        ctx = mp.get_context("fork")
        procs = []
        for worker_id in range(workers):
            shard_index = pod_index * workers + worker_id
            log(f"[seed] starting worker={worker_id} shard={shard_index}/{total_shards}")
            proc = ctx.Process(
                target=generate_shard,
                args=(tier, dsn_override, shard_index, total_shards, total_target_farmers),
                name=f"seed-w{worker_id}",
            )
            proc.start()
            log(f"[seed] worker={worker_id} pid={proc.pid} started")
            procs.append(proc)
        failed = False
        for proc in procs:
            proc.join()
            if proc.exitcode != 0:
                failed = True
                log(f"[seed] worker {proc.name} pid={proc.pid} exited {proc.exitcode}")
            else:
                log(f"[seed] worker {proc.name} pid={proc.pid} finished ok")
        if failed:
            raise SystemExit(1)
        parent_conn = db.connect()
        db.configure_bulk_session(parent_conn)

    rebuilt = False
    if config.DEFER_INDEXES:
        rebuilt = db.end_deferred_indexes(parent_conn, writer_id)

    if rebuilt or not config.DEFER_INDEXES:
        log("[seed] ANALYZE starting")
        with parent_conn.cursor() as cur:
            for live_table, history_table, _ in config.TABLE_NAMES.values():
                db.analyze(cur, live_table)
                db.analyze(cur, history_table)
        parent_conn.commit()

    parent_conn.close()
    log(f"[seed] pod={pod_index} wall time {_fmt_duration(time.time() - start)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tier",
        choices=list(config.DATA_VOLUME_TIERS),
        default=os.environ.get("SEED_TIER") or None,
        help="volume tier (or SEED_TIER). Ignored when SEED_TARGET_FARMERS is set.",
    )
    parser.add_argument("--dsn", default=None, help="overrides SEED_DB_DSN / config.DB_DSN")
    parser.add_argument(
        "--pod-index",
        type=int,
        default=None,
        help="zero-based index (or SEED_POD_INDEX / JOB_COMPLETION_INDEX)",
    )
    parser.add_argument(
        "--total-pods",
        type=int,
        default=None,
        help="total pods (or SEED_TOTAL_PODS)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="COPY/generator processes inside this pod (SEED_WORKERS, default 1)",
    )
    args = parser.parse_args()

    pod_index = args.pod_index
    if pod_index is None:
        pod_index = int(os.environ.get("SEED_POD_INDEX") or os.environ.get("JOB_COMPLETION_INDEX") or "0")
    total_pods = args.total_pods
    if total_pods is None:
        total_pods = int(os.environ.get("SEED_TOTAL_PODS") or "5")
    workers = args.workers if args.workers is not None else config.WORKERS
    tier = args.tier or os.environ.get("SEED_TIER") or "stretch"

    if pod_index >= total_pods:
        print(f"Error: pod-index ({pod_index}) must be less than total-pods ({total_pods})", flush=True)
        sys.exit(1)
    if workers < 1:
        print("Error: --workers must be >= 1", flush=True)
        sys.exit(1)

    run(tier, args.dsn, pod_index, total_pods, workers)

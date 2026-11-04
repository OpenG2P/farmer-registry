#!/usr/bin/env python3
"""Snapshot one celery case while beat and workers keep running.

Writes a CSV row at t=0 and at each mark (minutes). Counts are table-wide for
the case status column. Deltas are against the t=0 row, so historical
COMPLETED rows are not counted as work done in this window.

Redis depth is LLEN of the Celery queue name (default registry_worker_queue).
Leave REDIS_URL unset to skip it.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cases import Case, get_case
from db import connect, fetch_one_int, fetch_status_counts


def redis_depth() -> str:
    url = os.environ.get("REDIS_URL")
    if not url:
        return ""
    try:
        import redis
    except ImportError:
        print("WARN: REDIS_URL is set but the redis package is not installed", file=sys.stderr)
        return ""
    queue = os.environ.get("CELERY_QUEUE", "registry_worker_queue")
    client = redis.Redis.from_url(url)
    try:
        return str(int(client.llen(queue)))
    except Exception as exc:  # noqa: BLE001 — observation must keep going
        print(f"WARN: redis LLEN failed: {exc}", file=sys.stderr)
        return ""
    finally:
        client.close()


def snapshot(conn, case: Case) -> dict[str, int]:
    counts = fetch_status_counts(conn, case.status_counts_sql)
    extra = fetch_one_int(conn, case.extra_sql) if case.extra_sql else 0
    known = {case.pending, case.in_progress, case.done, case.failed}
    other = sum(n for status, n in counts.items() if status not in known)
    return {
        "pending": counts.get(case.pending, 0),
        "in_progress": counts.get(case.in_progress, 0),
        "done": counts.get(case.done, 0),
        "failed": counts.get(case.failed, 0),
        "other": other,
        "extra": extra,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument(
        "--marks",
        default="5,10,15,20,25,30",
        help="Comma-separated minute marks. A t=0 row is always written.",
    )
    parser.add_argument("--out", required=True, help="CSV path")
    parser.add_argument(
        "--arm",
        action="store_true",
        help="Record the idle cohort, wait until rows start leaving PENDING, then start the clock.",
    )
    parser.add_argument("--poll-s", type=float, default=2.0)
    parser.add_argument(
        "--arm-timeout-s",
        type=int,
        default=1800,
        help="Give up if beat and workers never start draining the cohort.",
    )
    args = parser.parse_args()

    marks = [int(part) for part in args.marks.split(",") if part.strip()]
    if any(mark <= 0 for mark in marks):
        sys.exit("marks must be positive minutes")
    if marks != sorted(marks):
        sys.exit("marks must be in ascending order")

    case = get_case(args.case)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp_utc",
        "elapsed_s",
        "mark_min",
        "case",
        "workers",
        "size",
        "pending",
        "in_progress",
        "done",
        "failed",
        "other",
        "done_delta",
        "failed_delta",
        "pending_drained",
        "redis_depth",
        "extra_name",
        "extra_count",
    ]

    conn = connect()
    start = time.monotonic()
    baseline: dict[str, int] | None = None

    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        print(",".join(fieldnames), flush=True)

        def write(mark_min: int, elapsed_s: float) -> None:
            nonlocal baseline
            counts = snapshot(conn, case)
            if baseline is None:
                baseline = counts
            row = {
                "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "elapsed_s": f"{elapsed_s:.1f}",
                "mark_min": mark_min,
                "case": case.name,
                "workers": args.workers,
                "size": args.size,
                "pending": counts["pending"],
                "in_progress": counts["in_progress"],
                "done": counts["done"],
                "failed": counts["failed"],
                "other": counts["other"],
                "done_delta": counts["done"] - baseline["done"],
                "failed_delta": counts["failed"] - baseline["failed"],
                "pending_drained": baseline["pending"] - counts["pending"],
                "redis_depth": redis_depth(),
                "extra_name": case.extra_name or "",
                "extra_count": counts["extra"],
            }
            writer.writerow(row)
            handle.flush()
            print(
                f"t={mark_min:>2}m pending={row['pending']} in_progress={row['in_progress']} "
                f"done_delta={row['done_delta']} failed_delta={row['failed_delta']} "
                f"redis_depth={row['redis_depth'] or '-'} {case.extra_name or 'extra'}={row['extra_count']}",
                flush=True,
            )
            print(",".join(str(row[name]) for name in fieldnames), flush=True)

        if args.arm:
            armed = snapshot(conn, case)
            baseline = armed
            print(
                f"COLLECTOR_ARMED case={case.name} pending={armed['pending']} "
                f"in_progress={armed['in_progress']} done={armed['done']}",
                flush=True,
            )
            print(
                "Scale beat to 1 and workers to the planned replica count. "
                "The clock starts when this cohort leaves PENDING.",
                flush=True,
            )
            deadline = time.monotonic() + args.arm_timeout_s
            while True:
                time.sleep(args.poll_s)
                seen = snapshot(conn, case)
                if (
                    seen["pending"] < armed["pending"]
                    or seen["in_progress"] > armed["in_progress"]
                    or seen["done"] > armed["done"]
                    or seen["failed"] > armed["failed"]
                ):
                    break
                if time.monotonic() >= deadline:
                    sys.exit(
                        "Timed out waiting for the cohort to move. "
                        "Beat is still at 0, or this case has no eligible rows."
                    )
            start = time.monotonic()
            write(0, 0.0)
        else:
            start = time.monotonic()
            write(0, 0.0)

        for mark in marks:
            target = start + mark * 60
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            write(mark, time.monotonic() - start)

    conn.close()
    print(f"COLLECTOR_FINISHED wrote {out}", flush=True)


if __name__ == "__main__":
    main()

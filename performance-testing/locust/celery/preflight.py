#!/usr/bin/env python3
"""Check that one celery case can be observed as a closed backlog.

Exit 0 when the cohort is eligible and siblings are idle.
Exit 1 when the run would not be an isolated drain of --size rows.
Pass --allow-mixed to keep going with sibling pending rows.
Pass --allow-size-mismatch when --size is a label, not an exact cohort.
Pass --strict-beat to fail when the beat tick cap cannot drain --size
inside the observation window.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

from cases import CASES, get_case
from db import connect, fetch_one_int


def enqueue_ceiling(window_s: int, frequency_s: int, tasks_per_tick: int) -> int:
    if frequency_s <= 0 or tasks_per_tick <= 0:
        return 0
    # Beat fires once per interval. This counts ticks inside the window,
    # not an extra tick at t=0, so it is a lower bound.
    ticks = math.floor(window_s / frequency_s)
    return ticks * tasks_per_tick


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True, help="Expected PENDING cohort size")
    parser.add_argument(
        "--window-min",
        type=int,
        default=30,
        help="Observation window used for the beat-ceiling check",
    )
    parser.add_argument(
        "--frequency-s",
        type=int,
        default=None,
        help="Beat interval. Defaults to the case's Helm/code default.",
    )
    parser.add_argument(
        "--tasks-per-tick",
        type=int,
        default=int(os.environ.get("REGISTRY_CELERY_BEAT_NO_OF_TASKS_TO_PROCESS", "4")),
    )
    parser.add_argument("--allow-mixed", action="store_true")
    parser.add_argument("--allow-size-mismatch", action="store_true")
    parser.add_argument("--strict-beat", action="store_true")
    args = parser.parse_args()

    if args.size < 0:
        sys.exit("--size must be >= 0")

    case = get_case(args.case)
    frequency_s = args.frequency_s if args.frequency_s is not None else case.frequency_s
    window_s = args.window_min * 60
    ceiling = enqueue_ceiling(window_s, frequency_s, args.tasks_per_tick)

    conn = connect()
    try:
        eligible = fetch_one_int(conn, case.eligible_sql)
        extra = fetch_one_int(conn, case.extra_sql) if case.extra_sql else 0
        others = {
            name: fetch_one_int(conn, other.eligible_sql)
            for name, other in CASES.items()
            if name != case.name
        }
    finally:
        conn.close()

    print(f"case={case.name}")
    print(f"description={case.description}")
    print(f"eligible={eligible}")
    print(f"expected_size={args.size}")
    print(f"frequency_s={frequency_s}")
    print(f"tasks_per_tick={args.tasks_per_tick}")
    print(f"enqueue_ceiling_{args.window_min}m={ceiling}")
    if case.extra_name:
        print(f"{case.extra_name}={extra}")
    for name, count in others.items():
        print(f"other:{name}={count}")
    print(f"producer_claims_row={case.producer_claims_row}")
    print(f"note={case.notes}")

    failed = False

    if eligible == 0:
        print("ERROR: no eligible rows. Fill this case's PENDING cohort before starting beat.")
        failed = True
    elif eligible != args.size and not args.allow_size_mismatch:
        print(
            "ERROR: eligible row count does not match --size. "
            "Beat drains every eligible row, so the cohort has to be exactly the backlog under test. "
            "Pass --allow-size-mismatch only when --size is a label."
        )
        failed = True

    busy = {name: count for name, count in others.items() if count}
    if busy and not args.allow_mixed:
        listed = ", ".join(f"{name}={count}" for name, count in busy.items())
        print(
            "ERROR: beat starts every producer, and these other cases still have "
            f"eligible rows: {listed}. Park them before scaling beat to 1."
        )
        failed = True

    if extra and case.extra_role == "sibling":
        print(
            f"ERROR: {case.extra_name}={extra}. Another producer will enqueue onto "
            "registry_worker_queue during this run. Clear that sibling status "
            "or pass --allow-mixed."
        )
        if not args.allow_mixed:
            failed = True
    elif extra and case.extra_role == "follow_on":
        print(
            f"ERROR: {case.extra_name}={extra} before the run starts. "
            "Those rows would be processed in the same window. "
            "Pass --allow-mixed to keep them."
        )
        if not args.allow_mixed:
            failed = True
    elif extra and case.extra_role == "reject":
        print(
            f"ERROR: {case.extra_name}={extra}. The worker rejects approved "
            "submissions whose draft_status is not FINAL. Those rows are inside "
            "the eligible cohort and will count as failures."
        )
        failed = True

    if not case.producer_claims_row:
        print(
            "WARN: this producer does not claim the row before enqueue. "
            "Raising tasks-per-tick or shortening the interval duplicates tasks "
            "until the worker marks PROCESSING."
        )

    if args.size > ceiling:
        message = (
            f"WARN: beat can enqueue about {ceiling} tasks in {args.window_min}m "
            f"({args.tasks_per_tick} every {frequency_s}s). "
            f"A cohort of {args.size} will still be mostly pending, and 1 vs 2 vs 3 "
            "worker pods will look the same. Raise "
            "REGISTRY_CELERY_BEAT_NO_OF_TASKS_TO_PROCESS and this case's frequency "
            "so enqueue stays ahead of the workers, then re-check this ceiling."
        )
        print(message)
        if args.strict_beat:
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

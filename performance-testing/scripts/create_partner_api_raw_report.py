#!/usr/bin/env python3
"""First-stage output (partner-api only): walk
locust/api/results/partner-api/ and emit
../documentation/partner-api/raw-report.md -- one markdown table per
Mode > Pod-Scale > Case, straight from Locust's own *_stats.csv, plus a
one-line concurrency/RPS note from *_stats_history.csv. No filtering to a
curated endpoint set, no SLO checks, no PASS/FAIL judgement -- every case
Locust actually measured, verbatim. That interpretation step is
final-report.md's job.

Columns match locust/api/templates/staff-api/raw_report_templates/isolated.csv
(partner-api has no templates of its own yet -- the staff-api template is
reused as-is since the Locust CSV shape is identical).

Usage:
    python create_partner_api_raw_report.py
"""
from __future__ import annotations

import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PERF_TESTING_DIR = SCRIPT_DIR.parent
RESULTS_ROOT = PERF_TESTING_DIR / "locust" / "api" / "results" / "partner-api"
COLUMNS_CSV = PERF_TESTING_DIR / "locust" / "api" / "templates" / "staff-api" / "raw_report_templates" / "isolated.csv"
OUT_PATH = PERF_TESTING_DIR / "documentation" / "partner-api" / "raw-report.md"

MODE_TITLES = {"sync": "Sync", "async": "Async", "ingest": "Ingest"}

DISPLAY_TO_LOCUST = {
    "Endpoint": "Name",
    "Method": "Type",
    "Median Response Time (ms)": "Median Response Time",
    "Average Response Time (ms)": "Average Response Time",
    "Min Response Time (ms)": "Min Response Time",
    "Max Response Time (ms)": "Max Response Time",
    "p50": "50%", "p66": "66%", "p75": "75%", "p80": "80%",
    "p90": "90%", "p95": "95%", "p98": "98%", "p99": "99%",
    "p99.9": "99.9%", "p99.99": "99.99%", "p100": "100%",
}


def load_columns() -> list[str]:
    with COLUMNS_CSV.open(newline="") as f:
        return next(csv.reader(f))


def render_table(rows: list[dict], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "|" + "---|" * len(columns)
    lines = [header, sep]
    for row in rows:
        cells = [row.get(DISPLAY_TO_LOCUST.get(c, c), "") for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def concurrency_note(tag_dir: Path, tag: str) -> str | None:
    history_csv = tag_dir / f"{tag}_stats_history.csv"
    if not history_csv.exists():
        return None
    with history_csv.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("Name") == "Aggregated"]
    counts = [int(r["User Count"]) for r in rows if r.get("User Count", "").strip() != ""]
    rps_values = []
    for row in rows:
        raw = (row.get("Requests/s") or "").strip()
        if not raw:
            continue
        try:
            rps_values.append(float(raw))
        except ValueError:
            continue
    if not counts and not rps_values:
        return None
    last_active = None
    for row in reversed(rows):
        raw_users = (row.get("User Count") or "").strip()
        if not raw_users:
            continue
        try:
            users = int(raw_users)
        except ValueError:
            continue
        if users > 0:
            last_active = row
            break
    final_users = int(last_active["User Count"]) if last_active else (counts[-1] if counts else None)
    final_rps = None
    if last_active and (last_active.get("Requests/s") or "").strip():
        try:
            final_rps = float(last_active["Requests/s"])
        except ValueError:
            pass
    if final_rps is None and rps_values:
        final_rps = rps_values[-1]
    bits = []
    if counts:
        bits.append(
            f"Concurrent users (from `{history_csv.name}`): "
            f"min {min(counts)}, max {max(counts)}, final {final_users}"
        )
    if rps_values:
        bits.append(
            f"Peak RPS (Aggregated): min {min(rps_values):.2f}, "
            f"max {max(rps_values):.2f}, final {final_rps:.2f}"
        )
    return "  \n".join(f"{bit}." for bit in bits)


def count_csv_rows(p: Path) -> int:
    if not p.exists():
        return 0
    with p.open(newline="") as f:
        return sum(1 for _ in f) - 1


def render_case(tag_dir: Path, tag: str, columns: list[str]) -> str | None:
    stats_csv = tag_dir / f"{tag}_stats.csv"
    if not stats_csv.exists():
        return None
    with stats_csv.open(newline="") as f:
        rows = list(csv.DictReader(f))
    header = f"**Case: `{tag}`**"
    note = concurrency_note(tag_dir, tag)
    if note:
        header += f"  \n{note}"
    body = header + "\n\n" + render_table(rows, columns)
    fail_rows = count_csv_rows(tag_dir / f"{tag}_failures.csv")
    exc_rows = count_csv_rows(tag_dir / f"{tag}_exceptions.csv")
    rec_rows = count_csv_rows(tag_dir / f"{tag}_records.csv")
    if fail_rows or exc_rows or rec_rows:
        bits = []
        if fail_rows:
            bits.append(f"{fail_rows} distinct error(s) in `{tag}_failures.csv`")
        if exc_rows:
            bits.append(f"{exc_rows} distinct exception(s) in `{tag}_exceptions.csv`")
        if rec_rows:
            bits.append(f"{rec_rows}-row per-minute record log in `{tag}_records.csv`")
        body += "\n\n" + "; ".join(bits) + "."
    return body


def main():
    if not RESULTS_ROOT.is_dir():
        raise SystemExit(f"No results directory at {RESULTS_ROOT}")

    columns = load_columns()
    mode_sections = []
    for mode_dir in sorted(p for p in RESULTS_ROOT.iterdir() if p.is_dir()):
        pod_sections = []
        for pod_dir in sorted((p for p in mode_dir.iterdir() if p.is_dir() and p.name.startswith("pod-")),
                               key=lambda p: int(p.name.split("-")[1])):
            tags = sorted(p.name[: -len("_stats.csv")] for p in pod_dir.glob("*_stats.csv"))
            case_sections = []
            for tag in tags:
                body = render_case(pod_dir, tag, columns)
                if body:
                    case_sections.append(body)
            if case_sections:
                pod_sections.append(f"### Pod-Scale: `{pod_dir.name}`\n\n" + "\n\n".join(case_sections))
        if pod_sections:
            title = MODE_TITLES.get(mode_dir.name, mode_dir.name)
            mode_sections.append(f"## {title}\n\n" + "\n\n".join(pod_sections))

    if not mode_sections:
        raise SystemExit(f"No result files found anywhere under {RESULTS_ROOT}")

    doc = [
        "# Raw Report",
        "",
        "Every measurement Locust actually recorded, verbatim -- no curation to a "
        "headline case set, no SLO comparison, no PASS/FAIL. That interpretation "
        "lives in [`final-report.md`](final-report.md), built from this document.",
        "",
        "Auto-generated by `scripts/create_partner_api_raw_report.py` from "
        "`locust/api/results/partner-api/` -- re-run it after any new run rather than "
        "editing this file by hand; it will be overwritten.",
        "",
        *mode_sections,
    ]

    OUT_PATH.write_text("\n".join(doc) + "\n")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

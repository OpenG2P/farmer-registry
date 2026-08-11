#!/usr/bin/env python3
"""Second-stage output (staff-api only): fill
locust/api/templates/staff-api/synthesize_templates/{isolated,blended}-capacity.csv
from raw Locust *_stats.csv runs (Step 1 / Step 2 -- see
../documentation/staff-api/test-scenarios.md §3/§7), applying SLOs and
computing PASS/FAIL for the curated set of headline endpoints. For the
*full*, raw, uninterpreted measurements (every endpoint, no SLO/pass-fail
judgement), see create_raw_report.py / ../documentation/staff-api/raw-report.md
instead -- that's this script's raw-data counterpart, not something it
depends on.

Usage:

    # Step 1 (isolated): results/staff-api/<ingress>/<tier>/pod-<pod_scale>/1-isolated/<flow>/*_stats.csv
    python synthesize_report.py --step isolated --ingress end-to-end --volume-tier smoke --pod-scale 1

    # Step 2 (blended): results/staff-api/<ingress>/<tier>/pod-<pod_scale>/2-blended/*_stats.csv
    python synthesize_report.py --step blended --ingress in-cluster --volume-tier primary --pod-scale 2

Matches each Locust-reported endpoint to the corresponding row in
synthesize_templates/<step>-capacity.csv by (scenario, endpoint, volume_tier,
pod_scale) -- scenario is empty for blended rows -- fills it, and writes a
filled copy alongside the raw results:
results/staff-api/<ingress>/<tier>/pod-<pod_scale>/<ordinal>-<step>/<step>-capacity.csv.
The template itself is never modified. Columns Locust can't supply (pod_cpu,
pod_mem, workers, saturating_resource) are left as-is for manual/
observability input.
"""
import argparse
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PERF_TESTING_DIR = SCRIPT_DIR.parent
TEMPLATES_DIR = PERF_TESTING_DIR / "locust" / "api" / "templates" / "staff-api" / "synthesize_templates"
RESULTS_ROOT = PERF_TESTING_DIR / "locust" / "api" / "results" / "staff-api"

# Step folders carry a readable ordinal prefix (matches env.sh's STEP export,
# e.g. "1-isolated") -- this script's own --step choices don't.
STEP_ORDINALS = {"isolated": "1", "blended": "2"}


def find_stats_csv(run_dir: Path) -> Path | None:
    matches = list(run_dir.glob("*_stats.csv"))
    return matches[0] if matches else None


def load_stats_rows(stats_csv: Path) -> list[dict]:
    with stats_csv.open(newline="") as f:
        return list(csv.DictReader(f))


def stats_row_to_fields(row: dict) -> dict:
    request_count = int(row["Request Count"])
    failure_count = int(row["Failure Count"])
    error_pct = (failure_count / request_count * 100) if request_count else 0.0
    return {
        "max_rps": row["Requests/s"],
        "p50_ms": row["50%"],
        "p90_ms": row["90%"],
        "p95_ms": row["95%"],
        "p99_ms": row["99%"],
        "max_ms": row["100%"],
        "error_pct": f"{error_pct:.2f}",
        "_p95_num": float(row["95%"]),
        "_error_pct_num": error_pct,
    }


def pass_fail(fields: dict, slo_p95_ms: str) -> str:
    if not slo_p95_ms:
        return ""
    return "PASS" if fields["_p95_num"] <= float(slo_p95_ms) and fields["_error_pct_num"] == 0 else "FAIL"


def row_key(row: dict) -> tuple:
    return (row.get("scenario") or "", row["endpoint"], row["volume_tier"], row["pod_scale"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--step", required=True, choices=["isolated", "blended"])
    parser.add_argument("--volume-tier", required=True, help="smoke | primary | stretch | stress")
    parser.add_argument("--pod-scale", required=True)
    parser.add_argument("--ingress", required=True, choices=["in-cluster", "end-to-end"])
    parser.add_argument("--register", default="Farmer")
    parser.add_argument("--notes", default="", help="Extra free-text appended to the notes column")
    args = parser.parse_args()

    step_dir = RESULTS_ROOT / args.ingress / args.volume_tier / f"pod-{args.pod_scale}" / f"{STEP_ORDINALS[args.step]}-{args.step}"
    if not step_dir.is_dir():
        raise SystemExit(f"No results directory at {step_dir}")

    template_path = TEMPLATES_DIR / f"{args.step}-capacity.csv"
    with template_path.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        template_rows = list(reader)

    rows_by_key = {row_key(row): row for row in template_rows}

    if args.step == "isolated":
        # one subfolder per scenario, each its own Locust run
        run_dirs = sorted(p for p in step_dir.iterdir() if p.is_dir())
        if not run_dirs:
            raise SystemExit(f"No scenario folders found in {step_dir}")
        runs = [(run_dir.name, run_dir) for run_dir in run_dirs]
    else:
        # blended: one combined locustfile run, directly in step_dir
        runs = [(None, step_dir)]

    summary = []
    for scenario, run_dir in runs:
        stats_csv = find_stats_csv(run_dir)
        if stats_csv is None:
            print(f"skip {run_dir}: no *_stats.csv found")
            continue

        stats_rows = load_stats_rows(stats_csv)
        endpoint_rows = [r for r in stats_rows if r["Name"] != "Aggregated"]
        aggregated_rows = [r for r in stats_rows if r["Name"] == "Aggregated"]

        to_apply = list(endpoint_rows)
        if len(endpoint_rows) > 1 and aggregated_rows:
            to_apply.append({**aggregated_rows[0], "Name": "BLENDED"})

        for stats_row in to_apply:
            endpoint = stats_row["Name"]
            key = (scenario or "", endpoint, args.volume_tier, args.pod_scale)
            template_row = rows_by_key.get(key)
            if template_row is None:
                print(f"warn {run_dir}: no {template_path.name} row for {key}, skipping")
                continue
            if template_row["ingress"] != args.ingress or template_row["register"] != args.register:
                print(
                    f"warn {run_dir}/{endpoint}: template row is ingress={template_row['ingress']} "
                    f"register={template_row['register']}, but you passed ingress={args.ingress} "
                    f"register={args.register} — filling anyway, check this is the right row"
                )

            fields = stats_row_to_fields(stats_row)
            template_row["max_rps"] = fields["max_rps"]
            template_row["p50_ms"] = fields["p50_ms"]
            template_row["p90_ms"] = fields["p90_ms"]
            template_row["p95_ms"] = fields["p95_ms"]
            template_row["p99_ms"] = fields["p99_ms"]
            template_row["max_ms"] = fields["max_ms"]
            template_row["error_pct"] = fields["error_pct"]
            template_row["pass_fail"] = pass_fail(fields, template_row["slo_p95_ms"])
            note = f"{args.step} run"
            if args.notes:
                note += f"; {args.notes}"
            template_row["notes"] = note

            summary.append((endpoint, fields["max_rps"], fields["p95_ms"], template_row["slo_p95_ms"], template_row["pass_fail"]))

    out_path = step_dir / f"{args.step}-capacity.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(template_rows)

    print(f"\nwrote {out_path}")
    print(f"{'endpoint':<40} {'rps':>8} {'p95_ms':>8} {'slo_p95_ms':>10}  pass_fail")
    for endpoint, rps, p95, slo, verdict in summary:
        print(f"{endpoint:<40} {rps:>8} {p95:>8} {slo:>10}  {verdict}")


if __name__ == "__main__":
    main()

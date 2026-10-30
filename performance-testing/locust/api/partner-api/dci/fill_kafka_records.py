#!/usr/bin/env python3
"""Fill the async records CSV from the partner WebSub Kafka topic.

Sync range runs count farmers in the HTTP body. Async returns only an ACK.
The on-search envelope is published to Kafka topic
http___websub_topics_PARTNER_STAFF_PORTAL (hub topic
http://websub/topics/PARTNER_STAFF_PORTAL). This writes the same
minute,processed_records,records_total file.

The clock starts when Locust writes the start file (click Start, or
headless test start). After the stop file, it keeps reading until the
topic is quiet so pages still in flight are included.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import signal
import subprocess
import time
from pathlib import Path

TOPIC = os.environ.get("KAFKA_TOPIC", "http___websub_topics_PARTNER_STAFF_PORTAL")
NAMESPACE = os.environ.get("PERF_NAMESPACE", "perftest")
POD = os.environ.get("KAFKA_POD", "commons-kafka-controller-0")
QUIET_SECONDS = 15
DRAIN_SECONDS = 180


def page_record_count(payload: dict) -> int:
    message = payload.get("message") or {}
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            return 0
    if not isinstance(message, dict):
        return 0
    count = 0
    for item in message.get("search_response") or []:
        records = ((item or {}).get("data") or {}).get("reg_records") or []
        if isinstance(records, list):
            count += len(records)
    return count


def as_envelope(value):
    """Return the DCI on-search object, or None."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    message = value.get("message")
    if isinstance(message, (dict, str)):
        return value
    for key in ("hub.content", "content", "payload", "data"):
        nested = value.get(key)
        if nested is not None and nested is not value:
            found = as_envelope(nested)
            if found is not None:
                return found
    event = value.get("event")
    if isinstance(event, dict):
        return as_envelope(event.get("data"))
    return None


class MinuteLog:
    """One CSV row per 60 seconds from the Locust start instant.

    Minute 1 is [start, start+60). A publish is filed by the broker time,
    shifted onto this machine's clock so a slow read does not move it into
    a later minute. The file is rewritten when a minute closes, so a record
    that arrives late still lands in its own minute and the running total
    stays the sum of the rows.
    """

    def __init__(self, path: Path):
        self.path = path
        self.epoch = 0.0
        self.total = 0
        self.counts: dict[int, int] = {}
        self._logged = 0
        self._skew: float | None = None

    def start(self, epoch: float):
        self.epoch = epoch

    def place(self, count: int, kafka_ts: float | None, received_at: float) -> float | None:
        if self.epoch <= 0 or count < 0:
            return None
        when = self._local_time(kafka_ts, received_at)
        minute = int((when - self.epoch) // 60) + 1
        if minute < 1:
            minute = 1
        self.counts[minute] = self.counts.get(minute, 0) + count
        self.total += count
        return when

    def _local_time(self, kafka_ts: float | None, received_at: float) -> float:
        if kafka_ts is None:
            return received_at
        if self._skew is None:
            self._skew = kafka_ts - received_at
        return kafka_ts - self._skew

    def closed_minute(self, now: float) -> int:
        """Last minute whose 60 seconds have finished. 0 before the first minute ends."""
        if self.epoch <= 0:
            return 0
        return int((now - self.epoch) // 60)

    def write(self, last_minute: int, log_new: bool):
        if self.epoch <= 0 or last_minute < 1:
            return
        running = 0
        lines = ["minute,processed_records,records_total"]
        for minute in range(1, last_minute + 1):
            count = self.counts.get(minute, 0)
            running += count
            lines.append(f"{minute},{count},{running}")
            if log_new and minute > self._logged:
                print(
                    f"[served] minute {minute}: processed {count}, total {running}",
                    flush=True,
                )
        self.path.write_text("\n".join(lines) + "\n")
        self._logged = last_minute


def transaction_id(envelope: dict) -> str:
    message = envelope.get("message") or {}
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            return ""
    if not isinstance(message, dict):
        return ""
    return str(message.get("transaction_id") or "")


def take_message(buf: str):
    """Pull one consumer record from the front of buf.

    Returns (payload, rest, kafka_epoch_seconds) or None when the next
    record is still incomplete. payload is the string 'skip' for a
    non-JSON line.
    """
    buf = buf.lstrip("\r\n")
    if not buf:
        return ("", "", None)
    kafka_ts = None
    if buf.startswith("CreateTime:") or buf.startswith("LogAppendTime:"):
        tab = buf.find("\t")
        if tab < 0:
            return None
        try:
            kafka_ts = int(buf[:tab].split(":", 1)[1]) / 1000.0
        except ValueError:
            kafka_ts = None
        if kafka_ts is not None and kafka_ts < 0:
            kafka_ts = None
        buf = buf[tab + 1 :]
    if not buf:
        return None
    if buf[0] not in '{["':
        nl = buf.find("\n")
        if nl < 0:
            return None
        return ("skip", buf[nl + 1 :], None)
    try:
        payload, idx = json.JSONDecoder().raw_decode(buf)
    except json.JSONDecodeError:
        return None
    return (payload, buf[idx:], kafka_ts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--start-file", required=True, type=Path)
    parser.add_argument("--stop-file", required=True, type=Path)
    parser.add_argument("--ready-file", required=True, type=Path)
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--done-file", type=Path)
    args = parser.parse_args()
    done_fh = args.done_file.open("a", buffering=1) if args.done_file else None

    def mark_done(tid: str) -> None:
        if done_fh is None or not tid:
            return
        done_fh.write(tid + "\n")
        done_fh.flush()

    stop = {"flag": False}

    def _stop(signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    group = f"perf-dci-records-{os.getpid()}"
    command = [
        "kubectl",
        "-n",
        NAMESPACE,
        "exec",
        POD,
        "-c",
        "kafka",
        "--",
        "stdbuf",
        "-oL",
        "-eL",
        "/opt/bitnami/kafka/bin/kafka-console-consumer.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--topic",
        TOPIC,
        "--group",
        group,
        "--consumer-property",
        "auto.offset.reset=latest",
        "--consumer-property",
        "enable.auto.commit=false",
        "--consumer-property",
        "max.partition.fetch.bytes=20971520",
        "--consumer-property",
        "fetch.max.bytes=20971520",
        "--property",
        "print.timestamp=true",
    ]
    env = os.environ.copy()
    env["KUBECONFIG"] = env.get("KUBECONFIG") or str(Path.home() / ".kube" / "perftest.yaml")
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    print(f"[served] consuming {TOPIC} on {POD}", flush=True)
    time.sleep(4)
    if proc.poll() is not None:
        print("[served] kafka consumer exited before the run started", flush=True)
        return 1
    args.ready_file.write_text("ready\n")

    log = MinuteLog(args.out)
    buf = ""
    skipped = 0
    ignored = 0
    duplicates = 0
    rejected = 0
    seen: set[str] = set()
    held: list[tuple[float | None, float, int]] = []
    last_msg = 0.0
    stop_at = 0.0
    reached = 0.0
    next_wait_log = time.monotonic() + 30
    eof = False

    def arm_clock() -> None:
        if log.epoch > 0 or stop["flag"] or not args.start_file.is_file():
            return
        raw = args.start_file.read_text().strip().splitlines()
        if not raw:
            return
        try:
            epoch = float(raw[0])
        except ValueError:
            return
        log.start(epoch)
        print(f"[served] clock started at {epoch:.3f} for {args.run_id}", flush=True)
        for kafka_ts, received_at, count in held:
            when = log.place(count, kafka_ts, received_at)
            if when is not None:
                note_reached(when)
        held.clear()

    def note_reached(when: float) -> None:
        nonlocal reached
        if reached > 0 or args.budget <= 0 or log.total < args.budget:
            return
        reached = max(0.0, when - log.epoch)
        print(
            f"[served] {args.budget} records published in "
            f"{reached / 60:.1f} min ({reached:.0f}s)",
            flush=True,
        )

    def accept(payload, kafka_ts: float | None, received_at: float) -> None:
        nonlocal skipped, ignored, duplicates, rejected, last_msg
        envelope = as_envelope(payload)
        if envelope is None:
            skipped += 1
            return
        header = envelope.get("header") or {}
        if isinstance(header, dict) and header.get("status") == "rjct":
            rejected += 1
            if rejected == 1:
                print(
                    "[served] publish rejected: "
                    f"{header.get('status_reason_code')} "
                    f"{header.get('status_reason_message')}",
                    flush=True,
                )
        tid = transaction_id(envelope)
        if not tid.startswith(args.run_id):
            ignored += 1
            return
        if tid in seen:
            duplicates += 1
            return
        seen.add(tid)
        mark_done(tid)
        count = page_record_count(envelope)
        last_msg = time.monotonic()
        if log.epoch <= 0:
            held.append((kafka_ts, received_at, count))
            return
        when = log.place(count, kafka_ts, received_at)
        if when is not None:
            note_reached(when)

    def pull() -> None:
        nonlocal buf, eof, skipped
        if proc.stdout is None or eof:
            return
        chunk = os.read(proc.stdout.fileno(), 1 << 20)
        if not chunk:
            eof = True
            return
        buf += chunk.decode("utf-8", errors="replace")
        while True:
            received_at = time.time()
            taken = take_message(buf)
            if taken is None:
                if len(buf) > 32 * 1024 * 1024:
                    buf = ""
                    skipped += 1
                return
            payload, buf, kafka_ts = taken
            if payload == "":
                return
            if payload == "skip":
                continue
            accept(payload, kafka_ts, received_at)

    while proc.poll() is None and not eof:
        arm_clock()
        ready, _, _ = select.select([proc.stdout], [], [], 0.2)
        if ready:
            pull()
        now = time.time()
        if log.epoch <= 0 and time.monotonic() >= next_wait_log and not stop["flag"]:
            next_wait_log = time.monotonic() + 30
            print("[served] waiting for Locust start", flush=True)
        if log.epoch > 0:
            closed = log.closed_minute(now)
            if closed > log._logged:
                log.write(closed, log_new=True)
        if args.stop_file.is_file() or stop["flag"]:
            if stop_at <= 0:
                stop_at = time.monotonic()
                print("[served] run stopped; draining Kafka", flush=True)
            idle = time.monotonic() - max(last_msg, stop_at)
            if idle >= QUIET_SECONDS or time.monotonic() - stop_at >= DRAIN_SECONDS:
                break

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    if log.epoch > 0:
        closed = log.closed_minute(time.time())
        last = max(closed, max(log.counts, default=0))
        if last < 1:
            last = 1
        log.write(last, log_new=True)
        if args.budget > 0 and reached <= 0:
            elapsed = time.time() - log.epoch
            print(
                f"[served] published {log.total} of {args.budget} records "
                f"in {elapsed / 60:.1f} min",
                flush=True,
            )
        print(
            f"[served] processed {log.total} records from Kafka "
            f"for {args.run_id}",
            flush=True,
        )
        print(f"[served] wrote {args.out}", flush=True)
    if rejected:
        print(f"[served] {rejected} publishes were rejected and had no farmers", flush=True)
    if ignored:
        print(f"[served] ignored {ignored} messages from other runs", flush=True)
    if duplicates:
        print(f"[served] ignored {duplicates} duplicate messages", flush=True)
    if skipped:
        print(f"[served] skipped {skipped} messages with no search body", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

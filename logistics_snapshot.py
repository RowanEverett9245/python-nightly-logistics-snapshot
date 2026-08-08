"""Build and upload a dated logistics snapshot, once or every night."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from infrai_storage import InfraiStorageClient


CONTENT_TYPE = "application/gzip"


def build_snapshot(source: Path, snapshot_date: date) -> tuple[bytes, int]:
    """Validate a JSON array and return a compact, compressed snapshot."""
    records: Any = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("The logistics source must contain a JSON array")

    document = {
        "snapshot_date": snapshot_date.isoformat(),
        "record_count": len(records),
        "records": records,
    }
    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return gzip.compress(raw, mtime=0), len(records)


def upload_snapshot(
    client: InfraiStorageClient,
    source: Path,
    bucket: str,
    snapshot_date: date,
) -> tuple[str, int, int]:
    payload, record_count = build_snapshot(source, snapshot_date)
    key = f"logistics/{snapshot_date.isoformat()}/shipments.json.gz"
    digest = hashlib.sha256(payload).hexdigest()

    client.create_bucket(bucket)
    signed_url = client.presign_put(
        bucket=bucket,
        key=key,
        content_type=CONTENT_TYPE,
        max_bytes=len(payload),
        idempotency_key=f"logistics-snapshot-{digest}",
    )
    client.put_signed(signed_url, payload, CONTENT_TYPE)
    return key, record_count, len(payload)


def next_run(now: datetime, daily_at: str) -> datetime:
    hour, minute = (int(part) for part in daily_at.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def run_daily(daily_at: str, action: Callable[[date], None]) -> None:
    while True:
        now = datetime.now().astimezone()
        scheduled = next_run(now, daily_at)
        time.sleep(max(0.0, (scheduled - now).total_seconds()))
        action(scheduled.date())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="JSON array of logistics records")
    parser.add_argument("--bucket", default="nightly-logistics-snapshots")
    parser.add_argument("--snapshot-date", type=date.fromisoformat)
    parser.add_argument(
        "--daily-at",
        metavar="HH:MM",
        help="keep running and upload each day at this local time",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("INFRAI_API_KEY", "")
    client = InfraiStorageClient(api_key)

    def run(for_date: date) -> None:
        key, records, size = upload_snapshot(client, args.source, args.bucket, for_date)
        print(json.dumps({"bucket": args.bucket, "key": key, "records": records, "bytes": size}))

    if args.daily_at:
        next_run(datetime.now().astimezone(), args.daily_at)
        run_daily(args.daily_at, run)
    else:
        run(args.snapshot_date or date.today())


if __name__ == "__main__":
    main()

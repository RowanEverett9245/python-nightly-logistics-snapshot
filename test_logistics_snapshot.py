import gzip
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from logistics_snapshot import build_snapshot, next_run


class SnapshotTest(unittest.TestCase):
    def test_snapshot_is_deterministic_and_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "shipments.json"
            source.write_text('[{"shipment_id":"S-42","status":"in_transit"}]')

            payload, count = build_snapshot(source, date(2026, 8, 3))
            decoded = json.loads(gzip.decompress(payload))

        self.assertEqual(count, 1)
        self.assertEqual(decoded["snapshot_date"], "2026-08-03")
        self.assertEqual(decoded["records"][0]["shipment_id"], "S-42")

    def test_next_run_moves_to_tomorrow_after_cutoff(self) -> None:
        now = datetime.fromisoformat("2026-08-03T02:30:00+08:00")
        self.assertEqual(
            next_run(now, "02:00"),
            datetime.fromisoformat("2026-08-04T02:00:00+08:00"),
        )


if __name__ == "__main__":
    unittest.main()

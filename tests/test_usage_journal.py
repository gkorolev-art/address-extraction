import json
import tempfile
import unittest
from pathlib import Path

from usage_journal import UsageJournal


class TestUsageJournal(unittest.TestCase):
    def test_writes_json_event_without_address_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "usage.jsonl"
            journal = UsageJournal(log_path)

            journal.write(
                "processing_completed",
                session_id="session-1",
                app_version="1.13.6",
                file_name="addresses.xlsx",
                rows=25,
                elapsed_seconds=1.2,
            )

            record = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(record["event"], "processing_completed")
            self.assertEqual(record["session_id"], "session-1")
            self.assertEqual(record["rows"], 25)
            self.assertNotIn("raw_address", record)
            self.assertNotIn("source_rows", record)

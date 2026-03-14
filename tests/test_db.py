from pathlib import Path
import tempfile
import unittest

from replayos.db import ReplayDB


class DBTests(unittest.TestCase):
    def test_insert_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = ReplayDB(Path(tmp) / "replayos.db")
            event_id = db.insert_event(
                source="demo",
                title="Launch Plan",
                content="Ship ReplayOS MVP this week",
                metadata={"team": "core"},
            )
            self.assertGreater(event_id, 0)
            hits = db.search_events("ReplayOS", limit=5)
            self.assertGreaterEqual(len(hits), 1)
            same_source = db.list_events(limit=5, source="demo")
            self.assertEqual(len(same_source), 1)
            event = db.get_event_by_id(event_id)
            self.assertIsNotNone(event)
            self.assertEqual(event.title, "Launch Plan")
            db.log_connector_run("dummy", status="ok", synced_count=1, error_message=None)
            runs = db.recent_connector_runs(limit=10, connector_id="dummy")
            self.assertEqual(len(runs), 1)
            exported = db.export_data(event_limit=10, action_limit=10)
            self.assertGreaterEqual(exported["event_count"], 1)
            self.assertGreaterEqual(exported["connector_run_count"], 1)
            deleted = db.delete_before("9999-01-01T00:00:00+00:00")
            self.assertGreaterEqual(deleted["deleted_events"], 1)
            db.close()


if __name__ == "__main__":
    unittest.main()

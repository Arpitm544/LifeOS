import unittest
from datetime import date, timezone
from uuid import UUID

from seed_demo import build_demo


class DemoFixturesTest(unittest.TestCase):
    def test_history_calendar_and_references(self):
        owner = UUID("11111111-1111-4111-8111-111111111111")
        rows = build_demo(owner, date(2026, 11, 14))
        self.assertEqual(rows, build_demo(owner, date(2026, 11, 14)))
        done = [task for task in rows["tasks"] if task["status"] == "done"]
        self.assertEqual(len(done), 28)
        self.assertEqual(len({task["completed_at"].date() for task in done}), 14)
        study = [task for task in done if task["category"] == "study"]
        self.assertTrue(all(task["effort_actual_min"] / task["effort_est_min"] == 1.6 for task in study))
        ids = {task["id"] for task in rows["tasks"]}
        self.assertTrue(all(block["task_id"] in ids for block in rows["plan_blocks"]))
        self.assertTrue(all(row["user_id"] == str(owner) for table in rows.values() for row in table))
        self.assertTrue(all(event["start_at"].tzinfo == timezone.utc for event in rows["events"]))
        self.assertEqual(len(rows["events"]), 7)  # five classes plus two shifts


if __name__ == "__main__":
    unittest.main()

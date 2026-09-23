import json
import tempfile
import unittest
from pathlib import Path

from benchx.worker import order as order_module, run as run_module

from helpers import gbench_order, make_build_dir, make_repo


class Pipeline(unittest.TestCase):
    def setUp(self):
        self._load = order_module.load

    def tearDown(self):
        order_module.load = self._load

    def _stub_order(self, order):
        order_module.load = lambda path: order

    def test_dry_run_plans_and_captures_without_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "src")
            order = gbench_order(make_build_dir(Path(tmp)), source_dir=root)
            self._stub_order(order)
            outcome = run_module.run("ignored.json", Path(tmp) / "out", dry_run=True)
            self.assertEqual(outcome.exit_code, 0)
            self.assertEqual(len(outcome.planned), 3)
            self.assertIn("clean", outcome.message)
            self.assertFalse((Path(tmp) / "out").exists())

    def test_a_run_writes_the_order_context_raw_output_and_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "src")
            order = gbench_order(make_build_dir(Path(tmp)), source_dir=root,
                                 filter="TakeChunked")
            self._stub_order(order)
            outcome = run_module.run("ignored.json", Path(tmp) / "out", timeout=60.0)

            self.assertEqual(outcome.exit_code, 0)
            run_dir = outcome.run_dir
            self.assertTrue((run_dir / "workorder.json").is_file())

            captured = json.loads((run_dir / "context.json").read_text())
            self.assertEqual(captured["subject_name"], "arrow")
            self.assertEqual(captured["revision"]["dirty"], "clean")
            self.assertEqual(captured["harness"]["name"], "google-benchmark")
            self.assertEqual(captured["environment"]["schema"], "machine/v1")

            accounting = json.loads((run_dir / "run.json").read_text())
            self.assertTrue(accounting["planned_set_known"])
            self.assertEqual(len(accounting["planned"]), 1)
            self.assertEqual(len(accounting["invocations"]), 1)
            self.assertTrue(accounting["invocations"][0]["parsed"])
            self.assertFalse(accounting["results_written"])
            self.assertEqual(len(list((run_dir / "raw").glob("*.json"))), 1)

    def test_an_unknown_harness_is_rejected_with_exit_code_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            order = gbench_order(make_build_dir(Path(tmp)))
            order.document["harness"] = {"name": "criterion"}
            self._stub_order(order)
            outcome = run_module.run("ignored.json", Path(tmp) / "out")
            self.assertEqual(outcome.exit_code, 1)
            self.assertIn("no adapter", outcome.message)

    def test_a_quantity_the_adapter_cannot_map_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            order = gbench_order(make_build_dir(Path(tmp)))
            order.document["quantities"] = ["wall-time", "peak-rss"]
            self._stub_order(order)
            outcome = run_module.run("ignored.json", Path(tmp) / "out")
            self.assertEqual(outcome.exit_code, 1)
            self.assertIn("peak-rss", outcome.message)

    def test_a_missing_suite_is_rejected_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            order = gbench_order(Path(tmp) / "no-such-build-dir")
            self._stub_order(order)
            outcome = run_module.run("ignored.json", Path(tmp) / "out")
            self.assertEqual(outcome.exit_code, 1)
            self.assertFalse((Path(tmp) / "out").exists())


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path

from benchx.adapters.gbench import drive
from benchx.worker.errors import OrderRejected, PlanFailed
from benchx.worker.target import resolve

from helpers import gbench_order, make_build_dir


def planned(order, target):
    return drive.plan(order, target)


class Applicability(unittest.TestCase):
    def test_process_level_repetitions_are_rejected(self):
        order = gbench_order(
            Path("/nonexistent"),
            protocol={"repetitions": {"mode": "fixed", "levels": [
                {"unit": "process", "n": 20}, {"unit": "value", "n": 3}]}},
        )
        with self.assertRaises(OrderRejected):
            drive.check_order(order)

    def test_counted_warmup_is_rejected(self):
        order = gbench_order(
            Path("/nonexistent"),
            protocol={"warmup": {"mode": "fixed", "n_warmup": 3}},
        )
        with self.assertRaises(OrderRejected):
            drive.check_order(order)

    def test_single_repetition_level_is_accepted(self):
        order = gbench_order(
            Path("/nonexistent"),
            protocol={"repetitions": {"mode": "fixed",
                                      "levels": [{"unit": "repetition", "n": 10}]}},
        )
        drive.check_order(order)
        self.assertEqual(drive.repetitions(order), 10)


class Planning(unittest.TestCase):
    def test_lists_cases_and_honours_the_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp))
            order = gbench_order(build_dir, filter="TakeChunked")
            cases = planned(order, resolve(order))
            self.assertEqual([c.name for c in cases], ["BM_TakeChunked/1024/2"])

    def test_lists_every_case_without_a_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp))
            order = gbench_order(build_dir)
            self.assertEqual(len(planned(order, resolve(order))), 3)

    def test_probes_the_minimum_time_spelling(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp))
            order = gbench_order(build_dir)
            target = resolve(order)
            planned(order, target)
            self.assertTrue(target.harness_options["min_time_arg"].endswith("s"))

            os.environ["FAKE_GBENCH_OLD"] = "1"
            try:
                target = resolve(order)
                planned(order, target)
            finally:
                del os.environ["FAKE_GBENCH_OLD"]
            self.assertFalse(target.harness_options["min_time_arg"].endswith("s"))

    def test_a_harness_that_cannot_list_fails_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp))
            (build_dir / "suite-benchmark").write_text("#!/bin/sh\nexit 3\n")
            (build_dir / "suite-benchmark").chmod(0o755)
            order = gbench_order(build_dir)
            with self.assertRaises(PlanFailed):
                planned(order, resolve(order))


class Invocation(unittest.TestCase):
    def _invoke(self, tmp, order=None, timeout=60.0):
        build_dir = make_build_dir(Path(tmp))
        order = order or gbench_order(build_dir)
        target = resolve(order)
        case = planned(order, target)[0]
        raw_dir = Path(tmp) / "raw"
        return drive.invoke(order, target, case, raw_dir, timeout)

    def test_captures_raw_output_stdout_and_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            invocation = self._invoke(tmp)
            self.assertEqual(invocation.returncode, 0)
            self.assertIsNotNone(invocation.raw_path)
            self.assertIn("benchmarks", invocation.raw)
            stem = invocation.raw_path.with_suffix("")
            self.assertTrue(stem.with_suffix(".stdout").is_file())
            self.assertTrue(stem.with_suffix(".stderr").is_file())

    def test_the_filter_is_anchored_to_one_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            invocation = self._invoke(tmp)
            self.assertEqual(len(invocation.raw["benchmarks"]), 1)
            self.assertIn("--benchmark_filter=^BM_Take/1024/2$", invocation.argv)

    def test_protocol_reaches_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp))
            order = gbench_order(
                build_dir,
                protocol={
                    "repetitions": {"mode": "fixed",
                                    "levels": [{"unit": "repetition", "n": 4}]},
                    "calibration": {"mode": "adaptive",
                                    "minimum_sample_seconds": 0.25},
                },
            )
            invocation = self._invoke(tmp, order)
            self.assertIn("--benchmark_repetitions=4", invocation.argv)
            self.assertIn("--benchmark_min_time=0.25s", invocation.argv)
            self.assertEqual(len(invocation.raw["benchmarks"]), 4)

    def test_fixed_calibration_asks_for_iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp))
            order = gbench_order(
                build_dir,
                protocol={"calibration": {"mode": "fixed", "n_iterations": 512}},
            )
            invocation = self._invoke(tmp, order)
            self.assertIn("--benchmark_min_time=512x", invocation.argv)

    def test_a_crash_is_recorded_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FAKE_GBENCH_MODE"] = "crash"
            try:
                invocation = self._invoke(tmp)
            finally:
                del os.environ["FAKE_GBENCH_MODE"]
            self.assertNotEqual(invocation.returncode, 0)
            self.assertIsNone(invocation.raw)
            self.assertFalse(invocation.timed_out)

    def test_a_hang_times_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FAKE_GBENCH_MODE"] = "hang"
            try:
                invocation = self._invoke(tmp, timeout=1.0)
            finally:
                del os.environ["FAKE_GBENCH_MODE"]
            self.assertTrue(invocation.timed_out)


if __name__ == "__main__":
    unittest.main()

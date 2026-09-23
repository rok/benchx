import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from benchx.adapters.pyperf import drive
from benchx.worker.errors import OrderRejected
from benchx.worker.target import resolve

from helpers import FIXTURES, make_repo, pyperf_order


def make_script(tmp) -> tuple:
    root = make_repo(Path(tmp) / "src")
    shutil.copy(FIXTURES / "fake_pyperf.py", root / "bench.py")
    return root, Path("bench.py")


class Applicability(unittest.TestCase):
    def test_a_filter_is_rejected(self):
        order = pyperf_order(sys.executable, Path("bench.py"), filter="Take.*")
        with self.assertRaises(OrderRejected):
            drive.check_order(order)

    def test_repetition_units_it_cannot_apply_are_rejected(self):
        order = pyperf_order(
            sys.executable, Path("bench.py"),
            protocol={"repetitions": {"mode": "fixed",
                                      "levels": [{"unit": "repetition", "n": 10}]}},
        )
        with self.assertRaises(OrderRejected):
            drive.check_order(order)

    def test_process_and_value_levels_are_accepted(self):
        order = pyperf_order(
            sys.executable, Path("bench.py"),
            protocol={"repetitions": {"mode": "fixed", "levels": [
                {"unit": "process", "n": 20}, {"unit": "value", "n": 3}]}},
        )
        drive.check_order(order)

    def test_timed_warmup_is_rejected(self):
        order = pyperf_order(
            sys.executable, Path("bench.py"),
            protocol={"warmup": {"mode": "time", "seconds": 1}},
        )
        with self.assertRaises(OrderRejected):
            drive.check_order(order)


class Planning(unittest.TestCase):
    def test_the_suite_is_one_unit_with_an_unknown_case_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, script = make_script(tmp)
            order = pyperf_order(sys.executable, script, source_dir=root)
            cases = drive.plan(order, resolve(order))
            self.assertEqual(len(cases), 1)
            self.assertIsNone(cases[0].name)


class Invocation(unittest.TestCase):
    def _invoke(self, tmp, order=None, timeout=60.0):
        root, script = make_script(tmp)
        order = order or pyperf_order(sys.executable, script, source_dir=root)
        target = resolve(order)
        case = drive.plan(order, target)[0]
        return drive.invoke(order, target, case, Path(tmp) / "raw", timeout)

    def test_protocol_becomes_pyperf_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, script = make_script(tmp)
            order = pyperf_order(
                sys.executable, script, source_dir=root,
                protocol={
                    "repetitions": {"mode": "fixed", "levels": [
                        {"unit": "process", "n": 4}, {"unit": "value", "n": 2}]},
                    "calibration": {"mode": "adaptive",
                                    "minimum_sample_seconds": 0.05},
                    "warmup": {"mode": "fixed", "n_warmup": 2},
                },
            )
            invocation = self._invoke(tmp, order)
            self.assertIn("--processes=4", invocation.argv)
            self.assertIn("--values=2", invocation.argv)
            self.assertIn("--warmups=2", invocation.argv)
            self.assertIn("--min-time=0.05", invocation.argv)
            runs = invocation.raw["benchmarks"][0]["runs"]
            self.assertEqual(len([r for r in runs if r["values"]]), 4)

    def test_defaults_are_passed_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            invocation = self._invoke(tmp)
            self.assertIn(f"--processes={drive.DEFAULT_PROCESSES}", invocation.argv)
            self.assertIn(f"--values={drive.DEFAULT_VALUES}", invocation.argv)
            self.assertIn(f"--min-time={drive.DEFAULT_MIN_TIME_SECONDS}",
                          invocation.argv)

    def test_fixed_calibration_fixes_the_loops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, script = make_script(tmp)
            order = pyperf_order(
                sys.executable, script, source_dir=root,
                protocol={"calibration": {"mode": "fixed", "n_iterations": 256}},
            )
            invocation = self._invoke(tmp, order)
            self.assertIn("--loops=256", invocation.argv)
            self.assertFalse(any(a.startswith("--min-time") for a in invocation.argv))

    def test_its_own_timeout_is_passed_and_its_exit_code_understood(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FAKE_PYPERF_MODE"] = "timeout"
            try:
                invocation = self._invoke(tmp, timeout=30.0)
            finally:
                del os.environ["FAKE_PYPERF_MODE"]
            self.assertIn("--timeout=30.0", invocation.argv)
            self.assertTrue(invocation.timed_out)

    def test_a_crash_is_recorded_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FAKE_PYPERF_MODE"] = "crash"
            try:
                invocation = self._invoke(tmp)
            finally:
                del os.environ["FAKE_PYPERF_MODE"]
            self.assertEqual(invocation.returncode, 1)
            self.assertIsNone(invocation.raw)


if __name__ == "__main__":
    unittest.main()

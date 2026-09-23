import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from benchx.worker.errors import OrderRejected
from benchx.worker.target import resolve

from helpers import FIXTURES, gbench_order, make_build_dir, make_repo, pyperf_order


class BuildDirTarget(unittest.TestCase):
    def test_finds_the_suite_and_the_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "src")
            build_dir = make_build_dir(root)
            target = resolve(gbench_order(build_dir))
            self.assertEqual(target.executable.name, "suite-benchmark")
            self.assertEqual(target.source_dir, root)

    def test_captures_only_allowlisted_build_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp) / "src")
            configuration = resolve(gbench_order(build_dir)).configuration
            self.assertEqual(configuration["CMAKE_BUILD_TYPE"], "Release")
            self.assertEqual(configuration["CMAKE_CXX_FLAGS"], "-O2")
            self.assertNotIn("SOMETHING_ELSE", configuration)

    def test_missing_suite_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp) / "src", suite="other-benchmark")
            with self.assertRaises(OrderRejected):
                resolve(gbench_order(build_dir))

    def test_ambiguous_suite_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_dir = make_build_dir(Path(tmp) / "src")
            nested = build_dir / "nested"
            nested.mkdir()
            shutil.copy(build_dir / "suite-benchmark", nested / "suite-benchmark")
            (nested / "suite-benchmark").chmod(0o755)
            with self.assertRaises(OrderRejected) as caught:
                resolve(gbench_order(build_dir))
            self.assertIn("2 executables", str(caught.exception))


class PythonEnvTarget(unittest.TestCase):
    def test_probes_the_interpreter_and_resolves_the_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "src")
            shutil.copy(FIXTURES / "fake_pyperf.py", root / "bench.py")
            order = pyperf_order(sys.executable, Path("bench.py"), source_dir=root)
            target = resolve(order)
            self.assertEqual(target.script, root / "bench.py")
            self.assertIn("python_version", target.configuration)
            self.assertNotIn("executable", target.configuration)

    def test_missing_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "src")
            order = pyperf_order(sys.executable, Path("absent.py"), source_dir=root)
            with self.assertRaises(OrderRejected):
                resolve(order)

    def test_interpreter_that_is_not_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            order = pyperf_order(str(Path(tmp) / "python"), Path("bench.py"))
            with self.assertRaises(OrderRejected):
                resolve(order)


if __name__ == "__main__":
    unittest.main()

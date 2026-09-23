import tempfile
import unittest
from pathlib import Path

from benchx.worker import vcs

from helpers import make_repo


class Describe(unittest.TestCase):
    def test_clean_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp) / "repo")
            described = vcs.describe(repo)
            self.assertEqual(described["dirty"], "clean")
            self.assertEqual(len(described["revision"]), 40)
            self.assertEqual(described["tree"], vcs.tree_id(repo, "clean"))

    def test_dirty_checkout_has_a_different_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp) / "repo")
            clean = vcs.describe(repo)
            (repo / "README").write_text("changed\n", encoding="utf-8")
            dirty = vcs.describe(repo)
            self.assertEqual(dirty["dirty"], "dirty")
            self.assertEqual(dirty["revision"], clean["revision"])
            self.assertNotEqual(dirty["tree"], clean["tree"])

    def test_untracked_file_counts_as_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp) / "repo")
            (repo / "scratch.txt").write_text("x\n", encoding="utf-8")
            self.assertEqual(vcs.describe(repo)["dirty"], "dirty")

    def test_writing_a_tree_leaves_the_users_index_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp) / "repo")
            (repo / "scratch.txt").write_text("x\n", encoding="utf-8")
            vcs.describe(repo)
            staged = vcs._git("diff", "--cached", "--name-only", cwd=repo)
            self.assertEqual(staged, "")

    def test_no_checkout_is_unknown_without_a_tree(self):
        described = vcs.describe(None)
        self.assertEqual(described["dirty"], "unknown")
        self.assertIsNone(described["tree"])

    def test_directory_that_is_not_a_repo_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            described = vcs.describe(Path(tmp))
            self.assertEqual(described["dirty"], "unknown")
            self.assertIsNone(described["tree"])


if __name__ == "__main__":
    unittest.main()

import unittest

from tools.engine.revision import revision


class RevisionTest(unittest.TestCase):
    def test_stamped_builds_name_the_workspace_commit_and_its_time(self) -> None:
        commit = "0123456789abcdef0123456789abcdef01234567"
        status = f"BUILD_EMBED_LABEL \nSTABLE_GIT_COMMIT {commit}\n"
        self.assertEqual(revision(status, "inputs"), ("git", commit, "0"))
        self.assertEqual(
            revision(status + "STABLE_GIT_COMMIT_TIMESTAMP 1792922661\n", "inputs"),
            ("git", commit, "1792922661"),
        )
        # A commit time without a commit names no time stamp.
        self.assertEqual(
            revision("STABLE_GIT_COMMIT_TIMESTAMP 1792922661\n", "inputs"),
            ("bazel", "inputs", "0"),
        )
        with self.assertRaisesRegex(SystemExit, "hexadecimal commit hash"):
            revision("STABLE_GIT_COMMIT abc1234-dirty\n", "inputs")
        with self.assertRaisesRegex(SystemExit, "Unix time in seconds"):
            revision(status + "STABLE_GIT_COMMIT_TIMESTAMP 2026-10-25\n", "inputs")


if __name__ == "__main__":
    unittest.main()

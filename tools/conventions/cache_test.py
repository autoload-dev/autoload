"""Regressions for what the query cache's key covers and when it runs Bazel."""

import unittest

from tools.conventions.cache import QueryCache, loading_inputs
from tools.conventions.test_support import RepositoryTest

COMMAND = ("bazel", "query", "//...")


class QueryCacheTest(RepositoryTest):
    def key(self) -> str:
        return loading_inputs(self.workspace())

    def test_loading_inputs_change_the_key_but_compiled_sources_do_not(self) -> None:
        self.write("lib/BUILD.bazel", "")
        self.write("lib/tool.py", "print(1)")
        before = self.key()
        self.write("lib/tool.py", "print(2)")
        self.assertEqual(before, self.key())
        self.write("lib/BUILD.bazel", "filegroup(name = 'all')")
        self.assertNotEqual(before, self.key())

    def test_added_files_and_links_change_the_key(self) -> None:
        before = self.key()
        self.write("lib/tool.py", "")
        added = self.key()
        self.assertNotEqual(before, added)
        (self.root / "link").symlink_to("lib")
        self.files.add("link")
        self.assertNotEqual(added, self.key())

    def test_a_query_runs_once_per_command_and_inputs(self) -> None:
        runs: list[str] = []

        def query() -> str:
            runs.append("run")
            return "<query/>"

        inputs = ["a"]
        cache = QueryCache(self.root / "cache", lambda: inputs[0])
        self.assertEqual("<query/>", cache.run(self.root, COMMAND, query))
        self.assertEqual("<query/>", cache.run(self.root, COMMAND, query))
        self.assertEqual(1, len(runs))
        cache.run(self.root, (*COMMAND, "--output=xml"), query)
        self.assertEqual(2, len(runs))
        changed = QueryCache(self.root / "cache", lambda: "b")
        changed.run(self.root, COMMAND, query)
        self.assertEqual(3, len(runs))

    def test_a_failed_query_is_not_stored(self) -> None:
        def failing() -> str:
            raise ValueError("bazel failed")

        cache = QueryCache(self.root / "cache", lambda: "a")
        with self.assertRaises(ValueError):
            cache.run(self.root, COMMAND, failing)
        self.assertEqual("ok", cache.run(self.root, COMMAND, lambda: "ok"))


if __name__ == "__main__":
    unittest.main()

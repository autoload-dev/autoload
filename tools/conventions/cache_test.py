"""Regressions for what the query cache's key covers and when it runs Bazel."""

import os
import unittest

from tools.conventions.cache import (
    KEPT,
    QueryCache,
    loading_inputs,
)
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

    def test_documentation_does_not_change_the_key(self) -> None:
        self.write("README.md", "# One")
        before = self.key()
        self.write("README.md", "# Two")
        self.assertEqual(before, self.key())

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

    def test_only_the_most_recent_loading_inputs_keep_entries(self) -> None:
        directory = self.root / "cache"
        for index in range(KEPT + 2):
            QueryCache(directory, lambda index=index: f"inputs{index}").run(
                self.root, COMMAND, lambda: "out"
            )
            stamp = 1_000_000 + index
            os.utime(directory / f"inputs{index}", (stamp, stamp))
        self.assertEqual(
            {f"inputs{index}" for index in range(2, KEPT + 2)},
            {entry.name for entry in directory.iterdir()},
        )

    def test_an_entry_naming_a_vanished_external_repository_misses(self) -> None:
        external = self.root / "output_base/external/rules_cc+"
        external.mkdir(parents=True)
        output = f'<rule location="{external}/BUILD.bazel:1:1"/>'
        cache = QueryCache(self.root / "cache", lambda: "a")
        cache.run(self.root, COMMAND, lambda: output)
        self.assertEqual(output, cache.run(self.root, COMMAND, lambda: "fresh"))
        external.rmdir()
        self.assertEqual("fresh", cache.run(self.root, COMMAND, lambda: "fresh"))


if __name__ == "__main__":
    unittest.main()

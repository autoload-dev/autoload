import contextlib
import tempfile
import unittest
from pathlib import Path

from tools.mapped_paths import resolve_paths, resolver


class MappedPathsTest(unittest.TestCase):
    def test_mapped_paths_resolve_to_the_root_of_the_staged_file(self) -> None:
        mapped = "bazel-out/cfg/bin/main/a.gd"
        manifest = {"files": {"a.gd": mapped, "b.gd": "main/b.gd"}, "list": [mapped]}
        # Path mapping staged the inputs at their mapped paths.
        self.assertEqual(
            manifest, resolve_paths(manifest, resolver(["bazel-out/cfg/bin"]))
        )
        self.assertEqual(
            {
                "files": {
                    "a.gd": "bazel-out/k8-fastbuild/bin/main/a.gd",
                    "b.gd": "main/b.gd",
                },
                "list": ["bazel-out/k8-fastbuild/bin/main/a.gd"],
            },
            resolve_paths(manifest, resolver(["bazel-out/k8-fastbuild/bin"])),
        )
        with tempfile.TemporaryDirectory() as temp, contextlib.chdir(temp):
            Path("bazel-out/one/bin/main").mkdir(parents=True)
            Path("bazel-out/two/bin/main").mkdir(parents=True)
            Path("bazel-out/two/bin/main/a.gd").touch()
            resolve = resolver(["bazel-out/one/bin", "bazel-out/two/bin"])
            self.assertEqual("bazel-out/two/bin/main/a.gd", resolve(mapped))
            Path("bazel-out/one/bin/main/a.gd").touch()
            with self.assertRaisesRegex(ValueError, "several configurations"):
                resolve(mapped)


if __name__ == "__main__":
    unittest.main()

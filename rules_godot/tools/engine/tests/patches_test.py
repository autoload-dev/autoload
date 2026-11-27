import unittest

from tools.engine import patches
from tools.engine.tests.source_files import git_patch


class TouchedTest(unittest.TestCase):
    def test_a_patch_touches_the_files_it_changes_adds_and_deletes(self) -> None:
        text = git_patch(
            ("version.py", "version.py", "@@ -1 +1 @@\n-a\n+b\n"),
            ("", "core/fork.h", "@@ -0,0 +1 @@\n+#pragma once\n"),
            ("drivers/old.cpp", "", "@@ -1 +0,0 @@\n-int x;\n"),
        )
        self.assertEqual(
            patches.touched(text, 1),
            {"version.py", "core/fork.h", "drivers/old.cpp"},
        )

    def test_header_lookalikes_inside_a_hunk_are_lines(self) -> None:
        # A removed "-- x" line and an added "++ y" line look like file headers.
        text = git_patch(
            ("a.lua", "a.lua", "@@ -1,2 +1,2 @@\n--- x\n+++ y\n context\n"),
        )
        self.assertEqual(patches.touched(text, 1), {"a.lua"})

    def test_renames_copies_and_mode_changes_touch_both_names(self) -> None:
        text = (
            "diff --git a/old.h b/new.h\nsimilarity index 100%\n"
            "rename from old.h\nrename to new.h\n"
            "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n"
        )
        self.assertEqual(patches.touched(text, 1), {"old.h", "new.h", "run.sh"})

    def test_the_strip_level_applies(self) -> None:
        text = "--- x/y/core/a.h\n+++ x/y/core/a.h\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual(patches.touched(text, 2), {"core/a.h"})


if __name__ == "__main__":
    unittest.main()

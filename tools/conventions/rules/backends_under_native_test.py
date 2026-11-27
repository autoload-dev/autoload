"""backends-under-native: an add-on's backends live in its native/backends/."""

import unittest

from tools.conventions.rules.backends_under_native import BackendsUnderNative
from tools.conventions.test_support import AddonModuleTest


class BackendsUnderNativeTest(AddonModuleTest):
    rule = BackendsUnderNative()

    def test_backends_outside_native_are_reported_once_per_directory(self) -> None:
        self.write("examples/addons/widget/backends/apple/BUILD.bazel", "")
        self.write("examples/addons/widget/backends/apple/apple_backend.mm", "")
        self.write("examples/addons/widget/native/backends/linux/BUILD.bazel", "")
        self.assertEqual(
            [
                (
                    "an add-on's backends belong in its native/backends/: "
                    "examples/addons/widget/backends"
                )
            ],
            self.messages(),
        )


if __name__ == "__main__":
    unittest.main()

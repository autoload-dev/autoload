"""Public configuration targets and libraries must keep their kinds' contracts."""

import unittest

from tools.docs.output_contracts import ConfiguredTarget
from tools.docs.public_contracts import check_public_libraries, library_errors
from tools.docs.repository_contracts_test import evidence


class LibraryErrorsTest(unittest.TestCase):
    PLUGIN_API = "//godot/platforms:android_plugin_api"

    def errors(self, *providers: str) -> list[str]:
        target = ConfiguredTarget(
            self.PLUGIN_API, 1, 0, False, frozenset(providers), frozenset()
        )
        return library_errors(self.PLUGIN_API, target, "JavaInfo")

    def test_library_with_its_provider(self) -> None:
        self.assertEqual([], self.errors("JavaInfo"))

    def test_library_without_its_provider(self) -> None:
        self.assertEqual(
            [self.PLUGIN_API + ": public library is missing JavaInfo"],
            self.errors("CcInfo"),
        )


class PublicLibrariesTest(unittest.TestCase):
    def test_each_library_in_its_own_configuration(self) -> None:
        android = {"//command_line_option:platforms": "//:android"}
        libraries = {
            "//a:api": {"settings": android, "provider": "JavaInfo"},
            "//b:api": {"settings": {}, "provider": "JavaInfo"},
        }
        facts = evidence("<query/>", (android, ["//a:api"]), ({}, ["//b:api"]))
        self.assertEqual([], check_public_libraries(facts, libraries))
        missing = {"//a:api": {"settings": android, "provider": "ToolchainInfo"}}
        self.assertEqual(
            ["//a:api: public library is missing ToolchainInfo"],
            check_public_libraries(facts, missing),
        )


if __name__ == "__main__":
    unittest.main()

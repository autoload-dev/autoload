"""
Debuggable Android builds carry the launch arguments plugin; release builds do not.

Arguments: --plugin or --no-plugin, the shell manifest, then the shell's Java sources.
"""

import sys
import unittest
from pathlib import Path

PLUGIN = "LaunchArgumentsPlugin.java"
REGISTRATION = "org.godotengine.plugin.v2.RulesGodotLaunchArguments"


class LaunchArgumentsPluginTest(unittest.TestCase):
    expected = True
    manifest = Path()
    java: tuple[Path, ...] = ()

    def test_the_build_carries_and_registers_the_plugin_or_neither(self) -> None:
        self.assertEqual(PLUGIN in [path.name for path in self.java], self.expected)
        self.assertEqual(REGISTRATION in self.manifest.read_text(), self.expected)


if __name__ == "__main__":
    LaunchArgumentsPluginTest.expected = sys.argv[1] == "--plugin"
    LaunchArgumentsPluginTest.manifest = Path(sys.argv[2])
    LaunchArgumentsPluginTest.java = tuple(Path(path) for path in sys.argv[3:])
    unittest.main(argv=sys.argv[:1])

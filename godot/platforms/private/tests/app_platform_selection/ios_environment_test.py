"""An iOS device export carries no Simulator feature; a Simulator export does."""

import sys
import unittest
from pathlib import Path

from tools.pck import pck_member, project_features


class IosEnvironmentTest(unittest.TestCase):
    def test_simulator_feature_follows_the_ios_environment(self) -> None:
        for path, simulator in [(sys.argv[1], False), (sys.argv[2], True)]:
            with self.subTest(simulator=simulator):
                data = Path(path).read_bytes()
                packed = project_features(pck_member(data, "project.binary"))
                self.assertEqual(simulator, "simulator" in packed, packed)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])

import unittest
from unittest import mock

from tools.addons import selftest
from tools.addons.new import declare
from tools.addons.test_support import RepositoryTestCase


class SelfTestTest(RepositoryTestCase):
    def test_the_checkout_is_as_before_also_after_an_interrupted_run(self) -> None:
        manifest = self.root / "MODULE.bazel"
        before = manifest.read_text()
        # A run that ended before its cleanup left the module declared.
        declare(selftest.SELFTEST, self.root)
        with mock.patch.object(selftest.lanes, "run") as lane:
            selftest.run("desktop", self.root)
        lane.assert_called_once()
        self.assertEqual(manifest.read_text(), before)
        self.assertFalse((self.root / "addons/.selftest").exists())
        self.assertFalse((self.root / "examples/addons/selftest").exists())


if __name__ == "__main__":
    unittest.main()

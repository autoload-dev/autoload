import unittest
from unittest import mock

from tools.addons import selftest
from tools.addons.declarations import SEGMENT
from tools.addons.new import generate
from tools.addons.test_support import RepositoryTestCase
from tools.setup.modules import SELFTEST


class SelfTestTest(RepositoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        generate("widget", root=self.root, release=False)
        self.lock = self.root / "MODULE.bazel.lock"
        self.lock.write_text("{}\n")

    def run_lane(self) -> str:
        """Run the self-test with a lane that returns the segment it ran with."""
        seen = []

        def lane(*_: object) -> None:
            seen.append((self.root / SEGMENT).read_text())
            self.lock.write_text('{"changed": true}\n')

        with mock.patch.object(selftest.lanes, "run", side_effect=lane):
            selftest.run("desktop", self.root)
        return seen[0]

    def test_the_lane_runs_with_the_module_declared(self) -> None:
        self.assertIn('module_name = "autoload_selftest"', self.run_lane())

    def test_the_checkout_is_as_before_also_after_an_interrupted_run(self) -> None:
        before = (self.root / SEGMENT).read_text()
        # A run that ended before its cleanup left the module and its declaration behind.
        generate(SELFTEST, root=self.root, release=False)
        selftest.declarations.write(self.root, extra=(SELFTEST,))
        self.run_lane()
        self.assertEqual((self.root / SEGMENT).read_text(), before)
        self.assertEqual(self.lock.read_text(), "{}\n")
        self.assertFalse((self.root / "addons" / SELFTEST).exists())
        self.assertFalse((self.root / "examples/addons" / SELFTEST).exists())


if __name__ == "__main__":
    unittest.main()

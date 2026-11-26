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

    def run_selftest(self) -> str:
        """Run the self-test with tests that return the segment they ran with."""
        seen = []

        def lock(root: object) -> None:
            seen.append("lock")
            self.lock.write_text('{"changed": true}\n')

        def tests(*_: object) -> None:
            seen.append((self.root / SEGMENT).read_text())

        with (
            mock.patch.object(selftest, "update_lock_file", side_effect=lock),
            mock.patch.object(selftest, "test_module", side_effect=tests),
            mock.patch.object(selftest, "test_registry_module") as registry,
            mock.patch.object(selftest, "host", return_value="linux"),
        ):
            selftest.run(self.root)
        registry.assert_called_once_with(self.root)
        self.assertEqual("lock", seen[0], "MODULE.bazel.lock is updated before the tests")
        return seen[1]

    def test_the_tests_run_with_the_module_declared(self) -> None:
        self.assertIn('module_name = "autoload_selftest"', self.run_selftest())

    def test_the_checkout_is_as_before_also_after_an_interrupted_run(self) -> None:
        before = (self.root / SEGMENT).read_text()
        # A run that ended before its cleanup left the module and its declaration behind.
        generate(SELFTEST, root=self.root, release=False)
        selftest.declarations.write(self.root, extra=(SELFTEST,))
        self.run_selftest()
        self.assertEqual((self.root / SEGMENT).read_text(), before)
        self.assertEqual(self.lock.read_text(), "{}\n")
        self.assertFalse((self.root / "addons" / SELFTEST).exists())
        self.assertFalse((self.root / "examples/addons" / SELFTEST).exists())


if __name__ == "__main__":
    unittest.main()

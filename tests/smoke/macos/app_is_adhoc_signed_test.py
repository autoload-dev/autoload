"""Check that the macOS smoke application's archive holds a valid ad hoc signature."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


class AdhocSigningTest(unittest.TestCase):
    def test_archived_bundle_signature_is_valid_and_ad_hoc(self) -> None:
        archive = Path(os.environ["TEST_SRCDIR"]) / sys.argv[1]
        # Runfiles hold symbolic links, which codesign rejects inside a bundle.
        extracted = Path(os.environ["TEST_TMPDIR"]) / "archive"
        subprocess.run(
            ["/usr/bin/ditto", "-x", "-k", str(archive), str(extracted)],
            check=True,
        )
        bundles = sorted(extracted.glob("**/*.app"))
        self.assertEqual(len(bundles), 1, bundles)
        verify = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundles[0])],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        details = subprocess.run(
            ["/usr/bin/codesign", "--display", "--verbose=2", str(bundles[0])],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(details.returncode, 0, details.stdout + details.stderr)
        self.assertIn("Signature=adhoc", details.stdout + details.stderr)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

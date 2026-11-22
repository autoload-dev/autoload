"""The godot-cpp generator wrapper passes the declared API and options to the generator."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tools.extension import bindings

# Stand-ins for godot-cpp's binding_generator.py, the sibling module it imports, and
# build_profile.py. Each records its call beside itself.
_GENERATOR = """import json, pathlib
import make_interface_header

_CALLS = pathlib.Path(__file__).with_name("calls.json")


def _record(function, args):
    _CALLS.write_text(json.dumps(
        {"function": function, "args": list(args), "sibling": make_interface_header.NAME}
    ))


def generate_bindings(*args):
    _record("generate_bindings", args)


def _generate_bindings(*args):
    _record("_generate_bindings", args)
"""
_INTERFACE_GENERATOR = 'NAME = "make_interface_header"\n'
_PROFILE_GENERATOR = """def generate_trimmed_api(api, profile):
    return {"trimmed": [api, profile]}
"""


class BindingsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        upstream = self.root / "godot-cpp"
        upstream.mkdir()
        (upstream / "binding_generator.py").write_text(_GENERATOR)
        (upstream / "make_interface_header.py").write_text(_INTERFACE_GENERATOR)
        (upstream / "build_profile.py").write_text(_PROFILE_GENERATOR)
        self.upstream = upstream
        self.output = self.root / "bin/gen-root"

    def _main(self, *options: str) -> dict[str, Any]:
        """Run the wrapper; return the recorded generator call, or {} for none."""
        argv = [
            "bindings",
            "--generator",
            str(self.upstream / "binding_generator.py"),
            "--api",
            "extension_api.json",
            "--interface",
            "gdextension_interface.json",
            "--output-root",
            str(self.output),
            *options,
        ]
        # The wrapper puts the generator's directory first on the import path.
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(sys, "path", list(sys.path)),
            mock.patch.dict(sys.modules),
        ):
            bindings.main()
        calls = self.upstream / "calls.json"
        return json.loads(calls.read_text()) if calls.exists() else {}

    def test_generator_receives_api_interface_bits_and_precision(self) -> None:
        call = self._main("--bits", "32", "--precision", "double")
        self.assertTrue(self.output.is_dir())
        self.assertEqual(
            {
                "function": "generate_bindings",
                "args": [
                    "extension_api.json",
                    "gdextension_interface.json",
                    True,
                    "32",
                    "double",
                    str(self.output),
                ],
                "sibling": "make_interface_header",
            },
            call,
        )

    def test_profile_trims_the_api_before_generation(self) -> None:
        call = self._main(
            "--profile",
            "build_profile.json",
            "--profile-generator",
            str(self.upstream / "build_profile.py"),
        )
        self.assertEqual("_generate_bindings", call["function"])
        self.assertEqual(
            [
                {"trimmed": ["extension_api.json", "build_profile.json"]},
                "extension_api.json",
                "gdextension_interface.json",
                True,
                "64",
                "single",
                str(self.output),
            ],
            call["args"],
        )

    def test_unsupported_bits_or_precision_are_rejected(self) -> None:
        for option in (["--bits", "16"], ["--precision", "half"]):
            with self.subTest(option=option):
                with (
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as raised,
                ):
                    self._main(*option)
                self.assertEqual(2, raised.exception.code)
                self.assertFalse((self.upstream / "calls.json").exists())


if __name__ == "__main__":
    unittest.main()

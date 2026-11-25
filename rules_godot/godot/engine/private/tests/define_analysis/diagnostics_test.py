import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WRAPPER_LINES = [
    "#define GODOT_DEFINE_ANALYSIS_CANARY 1",
    "#define READ_ENABLED 1",
    "#define UNREAD_ENABLED 1",
    "#undef NDEBUG",
    '#include "core/a.cpp"',
]


class DiagnosticsTest(unittest.TestCase):
    """define_analysis.awk on the diagnostics of Clang, Apple's wrapper and GCC."""

    def analyse(self, diagnostics: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / "a.wrapper.cpp"
            wrapper.write_text("\n".join(WRAPPER_LINES) + "\n")
            return subprocess.run(
                ["awk", "-v", f"wrapper={wrapper}", "-f", sys.argv[1]],
                input=diagnostics.replace("WRAPPER", str(wrapper)),
                capture_output=True,
                text=True,
                check=False,
            )

    def assert_header(self, diagnostics: str) -> None:
        result = self.analyse(diagnostics)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["#define READ_ENABLED 1", "#undef NDEBUG"],
        )

    def test_clang(self) -> None:
        self.assert_header(
            "WRAPPER:3:9: warning: macro is not used [-Wunused-macros]\n"
            "    3 | #define UNREAD_ENABLED 1\n"
            "      |         ^\n"
            "WRAPPER:1:9: warning: macro is not used [-Wunused-macros]\n"
            "2 warnings generated.\n"
        )

    def test_coloured_clang(self) -> None:
        self.assert_header(
            "\033[1mWRAPPER:3:9: \033[0m\033[0;1;35mwarning: \033[0m"
            "\033[1mmacro is not used [-Wunused-macros]\033[0m\n"
            "\033[1mWRAPPER:1:9: \033[0m\033[0;1;35mwarning: \033[0m"
            "\033[1mmacro is not used [-Wunused-macros]\033[0m\n"
        )

    def test_gcc(self) -> None:
        self.assert_header(
            'WRAPPER:1:9: warning: macro "GODOT_DEFINE_ANALYSIS_CANARY" is not used '
            "[-Wunused-macros]\n"
            'WRAPPER:3:9: warning: macro "UNREAD_ENABLED" is not used [-Wunused-macros]\n'
        )

    def test_a_silent_compiler_fails(self) -> None:
        result = self.analyse("")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not even the canary", result.stderr)

    def test_an_unknown_warning_form_fails(self) -> None:
        result = self.analyse(
            "WRAPPER:1:9: warning: macro is not used [-Wunused-macros]\n"
            "WRAPPER(3): warning: unused macro UNREAD_ENABLED [-Wunused-macros]\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected unused-macro warning", result.stderr)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])

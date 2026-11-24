"""
Print the home of the Java runtime Bazel builds with (shared.bazelrc), fetching it if needed:
the Java of the Android SDK's tools when JAVA_HOME names none.
"""

import subprocess
from pathlib import Path

RUNTIME = "@bazel_tools//tools/jdk:current_java_runtime"
JAVA_HOME = 'providers(target)["ToolchainInfo"].java_runtime.java_home'


def bazel(*arguments: str) -> str:
    """One Bazel command's output, without its progress messages."""
    return subprocess.run(
        ["bazel", *arguments], capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> None:
    # Building the runtime fetches it; its home is relative to the output base.
    bazel("build", RUNTIME)
    home = bazel("cquery", RUNTIME, "--output=starlark", "--starlark:expr=" + JAVA_HOME)
    print(Path(bazel("info", "output_base")) / home)


if __name__ == "__main__":
    main()

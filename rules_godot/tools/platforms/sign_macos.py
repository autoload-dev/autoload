"""Sign a bundle's native code inside-out, then archive the signed copy."""

import argparse
import os
import shutil
import stat
import subprocess
from pathlib import Path

from tools.platforms.package_desktop import archive_tree

MACHO = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--codesigning-tool", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--entitlements")
    args = parser.parse_args()
    root = Path(args.output)
    shutil.copytree(args.input, root, dirs_exist_ok=True)
    # Bazel tree inputs are read-only outside a sandbox. Certificate signing may
    # replace files as signatures grow, requiring writable copied directories too.
    # Change only the copy; independently obtainable unsigned outputs stay intact.
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    environment = os.environ.copy()
    environment.pop("RUNFILES_MANIFEST_FILE", None)
    environment["RUNFILES_DIR"] = str(Path(args.codesigning_tool + ".runfiles").resolve())

    def sign(path: Path, entitlements: str | None = None) -> None:
        command = [
            args.codesigning_tool,
            "--codesign",
            "/usr/bin/codesign",
            "--identity",
            args.identity,
            "--force",
            "--disable_timestamp",
            "--target_to_sign",
            str(path),
        ]
        if entitlements:
            command += ["--entitlements", entitlements]
        subprocess.run(command, env=environment, check=True)

    for path in sorted(
        root.rglob("*"), key=lambda item: (-len(item.parts), item.as_posix())
    ):
        if path.is_file():
            with path.open("rb") as source:
                is_binary = source.read(4) in MACHO
            if is_binary:
                sign(path)
        elif path.suffix == ".framework":
            sign(path)
    sign(root, args.entitlements)
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(root)], check=True
    )
    archive_tree(root, args.archive, "macos")


if __name__ == "__main__":
    main()

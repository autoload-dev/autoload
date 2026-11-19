"""Reproduce the tiny non-executable archive used for repository analysis fixtures."""

import io
import zipfile
from pathlib import Path


def write(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    entry.external_attr = 0o100755 << 16
    archive.writestr(entry, data)


def main() -> None:
    macos = io.BytesIO()
    with zipfile.ZipFile(macos, "w") as archive:
        for cpu in ["arm64", "x86_64"]:
            for variant in ["debug", "release"]:
                write(
                    archive,
                    f"macos_template.app/Contents/MacOS/godot_macos_{variant}.{cpu}",
                    b"analysis fixture only\n",
                )
    output = Path(__file__).with_name("split_templates.zip")
    with zipfile.ZipFile(output, "w") as archive:
        for cpu in ["arm64", "x86_64"]:
            for variant in ["debug", "release"]:
                write(
                    archive,
                    f"templates/linux_{variant}.{cpu}",
                    b"analysis fixture only\n",
                )
        write(archive, "templates/macos.zip", macos.getvalue())


if __name__ == "__main__":
    main()

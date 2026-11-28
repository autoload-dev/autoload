"""
The command line of //tools/editor_action:godot_export: check a pack's authored export
options, probe its shell files, and export its configuration or the pack itself.
"""

import argparse
import json
from pathlib import Path

from tools.editor_action.export import configuration, pack, validate_export_facts
from tools.editor_action.shell_assets import shell_assets
from tools.inputs.manifest import add_manifest_arguments, load_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=["check-options", "shell", "pack", "configuration"]
    )
    add_manifest_arguments(parser)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--facts", type=Path, help="Godot's facts, for check-options.")
    args = parser.parse_args()
    execroot = Path.cwd()
    manifest = load_manifest(args)
    output = args.output.absolute()
    if args.mode == "check-options" and args.facts is None:
        parser.error("check-options requires --facts")
    if args.mode in ("pack", "configuration") and args.report is None:
        parser.error(args.mode + " requires --report")
    if args.mode == "check-options":
        validate_export_facts(
            manifest, json.loads(args.facts.read_text(encoding="utf-8"))
        )
        output.write_text("checked\n", encoding="utf-8")
    elif args.mode == "shell":
        shell_assets(manifest, output, execroot)
    else:
        run = configuration if args.mode == "configuration" else pack
        run(manifest, output, args.report.absolute(), execroot)


if __name__ == "__main__":
    main()

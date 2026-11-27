"""
Write the shell files of Godot applications as Godot's exporters write them.

Each command reads what Godot decided for a pack's export (--facts: its feature
tags, export options with their defaults and project settings with the export's
feature overrides) and the values the application rule knows (--values: an
engine profile of Godot's exporters and the rule's own settings), and fills the
shell file's template from templates/.
"""

import argparse
import json
from pathlib import Path

from tools.platforms import shell_android, shell_apple, shell_overrides
from tools.platforms.shell_common import Facts

_COMMANDS = [
    "android-command-line",
    "android-main-manifest",
    "android-manifest",
    "android-themes",
    "ios-plist",
    "macos-plist",
    "privacy-manifest",
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=_COMMANDS)
    parser.add_argument("--facts", type=Path, required=True, help="Godot's facts.")
    parser.add_argument("--values", type=Path, required=True, help="The rule's values.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plist", type=Path, action="append", default=[])
    parser.add_argument(
        "--override",
        type=Path,
        action="append",
        default=[],
        help="A file of the application whose slots the shell file leaves to it.",
    )
    parser.add_argument("--launch-color", type=Path, help="iOS launch screen color set.")
    parser.add_argument(
        "--localizations",
        type=Path,
        help="iOS InfoPlist.xcstrings, or a macOS directory of *.lproj.",
    )
    return parser


def _check_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject a command without the arguments it needs."""
    if args.command == "android-main-manifest" and len(args.override) != 1:
        parser.error("android-main-manifest requires one --override manifest")
    if args.command == "ios-plist" and not args.launch_color:
        parser.error("ios-plist requires --launch-color")


def _shell_file(args: argparse.Namespace, facts: Facts, values: dict) -> str:
    """Return the shell file of a command other than ios-plist."""
    match args.command:
        case "android-manifest":
            return shell_android.manifest(facts, values)
        case "android-main-manifest":
            return shell_android.main_manifest(
                shell_android.manifest(facts, values),
                args.override[0],
                values["owned_attributes"],
            )
        case "android-themes":
            return shell_android.themes(facts, values, args.override)
        case "privacy-manifest":
            return shell_apple.privacy_manifest(facts, values)
        case _:
            return shell_apple.macos_plist(facts, values)


def _ios_plist(
    args: argparse.Namespace, facts: Facts, values: dict, fragments: list[str]
) -> tuple[str, list[str], set[str]]:
    """Write the launch screen color; return the Info.plist, fragments and the app's keys."""
    text = shell_apple.ios_plist(facts, values)
    args.launch_color.write_text(shell_apple.launch_color(facts), encoding="utf-8")
    # The application's own Info.plist fragments set their keys instead of the
    # shell, its localizations and the add-ons.
    return shell_overrides.yield_plist_keys(
        text, fragments, args.override, values["owned_plist_keys"]
    )


def _write_localizations(
    args: argparse.Namespace, facts: Facts, values: dict, yielded: set[str]
) -> None:
    """Write the Info.plist's localized values but those the application sets."""
    tables = {
        locale: {key: value for key, value in table.items() if key not in yielded}
        for locale, table in shell_apple.localizations(
            facts, values, args.command == "macos-plist"
        ).items()
    }
    if args.command == "ios-plist":
        # Xcode compiles the catalog into each locale's InfoPlist.strings.
        args.localizations.write_text(
            shell_apple.string_catalog(tables), encoding="utf-8"
        )
    else:
        shell_apple.write_strings(tables, args.localizations)


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    facts = Facts(json.loads(args.facts.read_text(encoding="utf-8")))
    values = json.loads(args.values.read_text(encoding="utf-8"))
    if args.command == "android-command-line":
        args.output.write_bytes(shell_android.command_line_file(facts, values))
        return
    fragments = [path.read_text(encoding="utf-8") for path in args.plist]
    _check_arguments(parser, args)
    yielded: set[str] = set()
    if args.command == "ios-plist":
        text, fragments, yielded = _ios_plist(args, facts, values, fragments)
    else:
        text = _shell_file(args, facts, values)
    if fragments:
        text = shell_apple.merge_plists(text, fragments)
    if args.localizations:
        _write_localizations(args, facts, values, yielded)
    args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

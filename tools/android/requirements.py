"""Check that repository provisioning covers the consuming Bazel modules."""

import argparse
import ast
import json
import sys
from pathlib import Path

from tools.addons.modules import all_modules
from tools.setup.modules import (
    RULESET,
    RULESET_DOCS,
    bazelrc_options,
    declarations,
    ignored_modules,
)

# Provisioning must cover the SDK and .bazelrc overrides of every module that builds
# applications: the ruleset's development SDK and each consumer module's SDK.
SDK = "android_sdk_repository_extension.configure"
# The SDK packages the repository provisions: API levels, build tools and NDK.
PINS = "tools/android/sdk.json"
# Pins the Linux SDK and NDK of godot_android_toolchains for remote Linux executors.
LINUX_TOOLCHAINS = f"{RULESET}/godot/platforms/private/android_toolchains.bzl"


def sdk_requirements(source: str) -> dict[str, str | int]:
    calls = [call for call in declarations(source) if call.kind == SDK]
    if len(calls) != 1:
        raise ValueError(f"Expected one {SDK} declaration")
    return {
        keyword: ast.literal_eval(value)
        for keyword, value in calls[0].keywords.items()
        if keyword in ("api_level", "build_tools_version")
    }


def api_level(root: Path, module: str) -> str:
    """The Android API level a module's MODULE.bazel configures for its SDK."""
    return str(
        sdk_requirements((root / module / "MODULE.bazel").read_text())["api_level"]
    )


def linux_pins(source: str) -> tuple[str, str, list[str]]:
    """The build tools and NDK versions and the API levels the Linux toolchains pin."""
    values = {
        target.id: node.value
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    def version(name: str) -> str:
        match values.get(name):
            case ast.Call(keywords=keywords):
                versions = [k.value for k in keywords if k.arg == "version"]
                if len(versions) == 1:
                    return ast.literal_eval(versions[0])
        raise ValueError(f"Expected {name} = struct(version = ...)")

    match values.get("_PLATFORMS"):
        case ast.Dict(keys=keys):
            levels = [ast.literal_eval(key) for key in keys if key is not None]
        case _:
            raise ValueError("Expected _PLATFORMS = {...}")
    return version("_LINUX_BUILD_TOOLS"), version("_LINUX_NDK"), levels


def application_modules(root: Path) -> list[str]:
    """
    The modules that build applications, each of which must configure its SDK: the ruleset
    with the modules nested in it but its documentation module, and the examples of every add-on module whose addon.pkl
    names an application lane. The root's tooling and the add-on modules themselves, which
    use their examples' SDK, build none.
    """
    ruleset = RULESET.as_posix()
    return [
        ruleset,
        *(
            module
            for module in ignored_modules(root, ruleset)
            if module != RULESET_DOCS.as_posix()
        ),
        *(
            f"{module.path.as_posix()}/examples"
            for module in all_modules(root)
            if module.builds_apps
        ),
    ]


def configuration_errors(root: Path) -> list[str]:
    provisioned = json.loads((root / PINS).read_text())
    apis = provisioned["api_levels"]
    build_tools = provisioned["build_tools"]
    errors = []

    def check(location: str, key: str, required: str | int | None) -> None:
        available = apis if key == "api_level" else [build_tools]
        if str(required) not in available:
            errors.append(
                f"{location}: Android {key} {required!r} is not provisioned by "
                f"{PINS} ({', '.join(available)})"
            )

    # A file several modules import, such as shared.bazelrc, is reported once.
    overrides = set()
    for module in application_modules(root):
        manifest = (Path(module) / "MODULE.bazel").as_posix()
        try:
            required = sdk_requirements((root / manifest).read_text())
        except (SyntaxError, ValueError) as error:
            errors.append(f"{manifest}: {error}")
            continue
        for key in ("api_level", "build_tools_version"):
            check(manifest, key, required.get(key))
        overrides.update(bazelrc_options(root, module))
    for location, option in sorted(overrides):
        for key in ("api_level", "build_tools_version"):
            prefix = f"--@androidsdk//:{key}="
            if option.startswith(prefix):
                check(location, key, option[len(prefix) :])
    try:
        linux_build_tools, linux_ndk, linux_apis = linux_pins(
            (root / LINUX_TOOLCHAINS).read_text()
        )
    except (SyntaxError, ValueError) as error:
        errors.append(f"{LINUX_TOOLCHAINS}: {error}")
    else:
        check(LINUX_TOOLCHAINS, "build_tools_version", linux_build_tools)
        if linux_ndk != provisioned["ndk"]:
            errors.append(
                f"{LINUX_TOOLCHAINS}: Linux NDK {linux_ndk!r} differs from {PINS} "
                f"({provisioned['ndk']})"
            )
        if sorted(linux_apis) != sorted(apis):
            errors.append(
                f"{LINUX_TOOLCHAINS}: Linux api levels {sorted(linux_apis)} differ from "
                f"{PINS} ({', '.join(apis)})"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-level",
        metavar="MODULE",
        help="print the API level a module configures, such as rules_godot/tests, and exit",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.api_level:
        print(api_level(root, args.api_level))
        return 0
    errors = configuration_errors(root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Android SDK provisioning covers the consuming Bazel modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

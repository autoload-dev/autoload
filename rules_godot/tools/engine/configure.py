"""
Translate Godot's configure-only SCons graph to rules_cc targets.

SCons is used to evaluate the upstream feature logic, not to execute a compiler,
linker, source generator, or build cache. Compiler actions belong to Bazel.

Sections: Engine version, Recipe options, Renderers, Compile options, Environment reads,
Capture, Configurations, Pinning, Command line.
"""

import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
import os
import re
import shlex
import sys
import tempfile
import textwrap
from collections import defaultdict
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from pathlib import Path
from types import FunctionType
from typing import Any, TypeGuard, cast

from tools.engine import build_profile
from tools.engine.custom_modules import shapes_graph
from tools.engine.module_graph import module_closure, module_dependencies
from tools.engine.render import Variant, render, render_unpinned
from tools.engine.source_tree import SOURCE_SUFFIXES, digest_of, relative, write_json


def file_digest(path: Path) -> str:
    """Return the SHA-256 of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_digests(
    root: Path | None, by_content: Callable[[Path], bool] = lambda _path: True
) -> dict[str, str]:
    """
    Return each file below root by its relative path, with its SHA-256 where by_content
    accepts it and empty otherwise; nothing without a root.
    """
    if root is None:
        return {}
    return {
        path.relative_to(root).as_posix(): file_digest(path) if by_content(path) else ""
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ==== Engine version ==========================================================


_VERSION_FIELDS = ("major", "minor", "patch", "status")

_MINIMUM_VERSION = (4, 7, 2)


def _version_declarations(root: Path) -> dict[str, object]:
    """Return the values that the archive's version.py assigns to the version fields."""
    assignments = (
        (target.id, statement.value)
        for statement in ast.parse((root / "version.py").read_text()).body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name) and target.id in _VERSION_FIELDS
    )
    return {name: ast.literal_eval(value) for name, value in assignments}


def _declared_version(values: Mapping[str, object]) -> tuple[int, int, int]:
    declared = tuple(values.get(key) for key in ("major", "minor", "patch"))
    if not all(type(value) is int and value >= 0 for value in declared):
        raise ValueError(
            "Godot source version.py must declare integer major, minor and patch values"
        )
    return cast("tuple[int, int, int]", declared)


def _declared_status(values: Mapping[str, object]) -> str:
    status = values.get("status", "stable")
    if not isinstance(status, str) or not re.fullmatch(
        r"stable|(?:dev|alpha|beta|rc)[0-9]*", status
    ):
        raise ValueError(f"Unrecognized Godot source version status: {status!r}")
    return status


def _is_unsupported_version(version: tuple[int, int, int], status: str) -> bool:
    """Return whether a version precedes the supported release, or is a pre-release of it."""
    return (
        version[0] != _MINIMUM_VERSION[0]
        or version < _MINIMUM_VERSION
        or (version == _MINIMUM_VERSION and status != "stable")
    )


def source_version(root: Path) -> str:
    """Validate the archive's actual version before evaluating its build graph."""
    values = _version_declarations(root)
    version = _declared_version(values)
    status = _declared_status(values)
    text = ".".join(map(str, version)) + ("" if status == "stable" else "-" + status)
    if _is_unsupported_version(version, status):
        raise ValueError(
            f"Godot {'.'.join(map(str, _MINIMUM_VERSION))} or newer Godot "
            f"{_MINIMUM_VERSION[0]} sources are required; archive contains {text}"
        )
    return text


def require_expected_version(actual: str, expected: str) -> None:
    """Reject sources whose version.py contradicts their descriptor."""
    if expected and actual != expected:
        raise ValueError(
            f"The source descriptor declares Godot {expected}, "
            f"but the extracted version.py is {actual}"
        )


def _module_selection(args: argparse.Namespace) -> dict[str, Any]:
    """The requested modules; the upstream defaults only when requested, so earlier digests hold."""
    selection: dict[str, Any] = {"modules": args.modules}
    if args.default_modules:
        selection["default_modules"] = True
    return selection


def _profile_input(args: argparse.Namespace) -> dict[str, str]:
    """The build profile's digest; nothing without one, so earlier digests hold."""
    digest = args.build_profile_digest
    return {"build_profile": digest} if digest else {}


def inputs_hash(args: argparse.Namespace) -> str:
    """
    Return the hash an unstamped source-built engine names in place of a Git commit.

    It covers the engine's declared inputs: the archive digest, the patches, the
    custom module trees and the configuration. Neither time nor host state enters
    it, so an unchanged engine keeps its hash and its cached actions. The CPU stays
    out, so the engines of one configuration for several Android ABIs name the same
    hash in their shared AAR.
    """
    inputs = {
        "source": args.source_sha256,
        "patches": [file_digest(path) for path in args.patch],
        "patch_strip": args.patch_strip,
        **_profile_input(args),
        "custom_modules": file_digests(args.custom_modules_root),
        "configuration": {
            "platform": args.platform,
            "build_target": args.build_target,
            **_module_selection(args),
            "options": sorted(args.options),
        },
    }
    # The length of a Git commit hash, which Godot shortens to 9 for display.
    return digest_of(inputs)[:40]


# Version fields the generated :revision target supplies at build time: the
# build name with the hash's origin, and the hash and time stamp in the Git
# commit's place, which a release tarball's .git/HEAD may name.
REVISION_FILES = {
    "version_info_builder": {"build": "_revision/build.txt"},
    "version_hash_builder": {
        "git_hash": "_revision/hash.txt",
        "git_timestamp": "_revision/timestamp.txt",
    },
}


def version_name(info: Mapping[str, object]) -> str:
    """
    Return an engine's version and status as its Android library manifest names them.

    The patch number is always present, as in the manifest of an official AAR.
    The build name and hash follow at build time, such as .custom-git.<hash>.
    """
    return "{major}.{minor}.{patch}.{status}{module_config}".format(**info)


# ==== Recipe options ==========================================================


_TRUE_VALUES = {"yes", "true", "1", "y", "on"}

_FALSE_VALUES = {"no", "false", "0", "n", "off"}


def _option_value(value: object) -> str:
    """Return an SCons option value as yes or no where it is a boolean, else as it is."""
    text = str(value).lower()
    if text in _TRUE_VALUES:
        return "yes"
    if text in _FALSE_VALUES:
        return "no"
    return str(value)


def profile_options_digest(profile: Path) -> str:
    """
    Return the digest of what a build profile contributes to the configured graph.

    Only its build options shape the graph, so a profile that disables classes alone needs
    no pin. Empty without options, so earlier digests hold.
    """
    options = build_profile.build_options(build_profile.read_profile(profile))
    return "sha256:" + digest_of({"disabled_build_options": options}) if options else ""


PROTECTED_OPTIONS = {
    "platform",
    "arch",
    "target",
    "modules_enabled_by_default",
    "custom_modules",
    "scu_build",
    "generate_bundle",
    "generate_android_binaries",
    # Upstream extracts separate symbols in postlink actions Bazel does not run.
    "separate_debug_symbols",
    # The recipe's explicit iOS environment owns the SDK axis.
    "simulator",
    "ios_simulator",
    # Raw file paths would be undeclared inputs; use patches, build_options or an
    # application's build profile instead.
    "profile",
    "build_profile",
}

# Options whose flags Bazel's own flags replace, with the replacement.
BAZEL_OPTIONS = {
    "debug_symbols": "-c dbg, or --copt=-g / --per_file_copt with -c opt",
    "optimize": "-c with --@autoload_rules_godot//godot:engine_optimize",
    "lto": "-c opt with --@autoload_rules_godot//godot:engine_lto",
}


def _is_controlled_option(key: str, has_value: bool) -> bool:
    """Return whether rules_godot owns an option, so a recipe may not pass it."""
    is_module_switch = key.startswith("module_") and key.endswith("_enabled")
    return not has_value or key in PROTECTED_OPTIONS or is_module_switch


def check_options(options: Iterable[str]) -> None:
    for option in options:
        key, separator, _value = option.partition("=")
        if key in BAZEL_OPTIONS:
            raise ValueError(
                f"Option {option} follows the build's settings: use {BAZEL_OPTIONS[key]}"
            )
        if _is_controlled_option(key, bool(separator)):
            raise ValueError(f"Option is controlled by rules_godot: {option}")


def require_consistent_profile(profile: Path, options: Iterable[str]) -> None:
    """
    Fail for a build profile that is no JSON object, sets an option the ruleset owns or
    contradicts the recipe's options.

    SCons assigns each of a profile's disabled_build_options over the command line's, so
    such an option would silently override what the recipe or Bazel's settings ask for. A
    profile may switch modules, as the editor's profiles do.
    """
    profiled = build_profile.build_options(build_profile.read_profile(profile))
    check_options(
        f"{key}={value}"
        for key, value in profiled.items()
        if not (key.startswith("module_") and key.endswith("_enabled"))
    )
    requested = dict(option.partition("=")[::2] for option in options)
    conflicts = sorted(
        f"{key}={_option_value(value)} (build_options: {requested[key]})"
        for key, value in profiled.items()
        if key in requested and _option_value(value) != _option_value(requested[key])
    )
    if conflicts:
        raise ValueError(
            "The build profile contradicts the recipe's build_options: "
            + ", ".join(conflicts)
        )


def require_known_options(profile: Path, known: Collection[str]) -> None:
    """
    Fail for a build profile that sets options this Godot version's SCons does not have.

    SCons assigns each of a profile's disabled_build_options whatever its name, so a name
    this version lacks, such as an option of a later version, would change nothing.
    """
    options = build_profile.build_options(build_profile.read_profile(profile))
    unknown = sorted(set(options) - set(known))
    if unknown:
        raise ValueError(
            "The build profile sets options this Godot version does not have: "
            + ", ".join(unknown)
        )


# The modules a recipe names when it names none and does not start from Godot's defaults.
_DEFAULT_MODULES = ("gdscript", "text_server_fb")


def requested_modules(modules: str, default_modules: bool) -> list[str]:
    """
    Return the modules a recipe asks for: those it names, or else the ruleset's default.

    A recipe that starts from Godot's defaults takes no default of the ruleset's: those
    already include GDScript and a text server, and a second text server cannot link.
    """
    named = [module for module in modules.split(",") if module]
    return named or ([] if default_modules else list(_DEFAULT_MODULES))


_TEXT_SERVERS = ("text_server_adv", "text_server_fb")


def require_one_text_server(modules: Iterable[str]) -> None:
    """
    Fail for an engine with more than one of Godot's text servers.

    Both define the same SVG-in-OpenType symbols, and the engine's libraries link every
    object, so the application's link would fail on them.
    """
    servers = sorted(set(modules) & set(_TEXT_SERVERS))
    if len(servers) > 1:
        raise ValueError(
            "An engine links one text server, but this configuration enables "
            + " and ".join(servers)
            + ": name one in enabled_modules, or leave text_server_fb out when "
            + "default_modules starts from Godot's defaults"
        )


def customizations(args: argparse.Namespace) -> dict[str, list[str]]:
    """The requested build customization a recipe's components record as provenance."""
    requested = {
        "patches": [path.name for path in args.patch],
        "modules": list(args.modules),
        "custom_modules": sorted(args.custom_module_names),
        "options": sorted(args.options),
    }
    if args.default_modules:
        requested["default_modules"] = ["yes"]
    if args.build_profile_digest:
        requested["build_profile"] = [args.build_profile_digest]
    if args.renderers:
        requested["renderers"] = list(args.renderers)
    return requested


# ==== Renderers ===============================================================


# Godot's rendering methods, as project settings name them, and the RenderingDevice ones.
RENDERING_METHODS = ("gl_compatibility", "mobile", "forward_plus")

_RD_METHODS = ("mobile", "forward_plus")

# Each platform's RenderingDevice driver; Apple engines leave Vulkan off, since it needs
# the MoltenVK SDK on the configuring host.
_RD_DRIVERS = {
    "ios": "metal",
    "macos": "metal",
    "android": "vulkan",
    "linuxbsd": "vulkan",
}

# Godot 4.8's switches for RenderingDevice and each of its renderers.
_RD_SWITCHES = {
    "rendering_device": _RD_METHODS,
    "forward_plus_renderer": ("forward_plus",),
    "forward_mobile_renderer": ("mobile",),
}

_RD_SWITCH_OPTION = re.compile(r'BoolVariable\(\s*"rendering_device"')


def has_renderer_switches(root: Path) -> bool:
    """Return whether the source's SConstruct can leave out each RenderingDevice renderer."""
    sconstruct = (root / "SConstruct").read_text(encoding="utf-8")
    return _RD_SWITCH_OPTION.search(sconstruct) is not None


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def renderer_options(
    renderers: Collection[str], platform: str, switches: bool
) -> list[str]:
    """
    Return the upstream options that build exactly a recipe's rendering methods.

    Without Godot 4.8's switches, RenderingDevice comes and goes with its driver, so the
    mobile and forward_plus methods come together.
    """
    unknown = sorted(set(renderers) - set(RENDERING_METHODS))
    if unknown:
        raise ValueError(
            "Unknown rendering methods: "
            + ", ".join(unknown)
            + "; use "
            + ", ".join(RENDERING_METHODS)
        )
    rd = any(method in renderers for method in _RD_METHODS)
    driver = _RD_DRIVERS[platform]
    options = ["opengl3=" + _yes("gl_compatibility" in renderers), f"{driver}={_yes(rd)}"]
    if driver == "metal":
        options.append("vulkan=no")
    if switches:
        options.extend(
            f"{switch}={_yes(any(method in renderers for method in methods))}"
            for switch, methods in _RD_SWITCHES.items()
        )
    return options


def _switched_off(platform: str, switches: bool) -> dict[str, Sequence[str]]:
    """The options that turn rendering methods off: their drivers, and 4.8's switches."""
    options: dict[str, Sequence[str]] = {
        "opengl3": ("gl_compatibility",),
        _RD_DRIVERS[platform]: _RD_METHODS,
    }
    return options | (_RD_SWITCHES if switches else {})


def profile_renderers(
    renderers: Sequence[str], options: Mapping[str, object], platform: str, switches: bool
) -> list[str]:
    """
    Return a recipe's rendering methods that a build profile's options leave.

    A profile turns a method's driver off where the project does not use it, such as Metal
    for a project on the Compatibility renderer; the recipe then builds the others.
    """
    gone = {
        method
        for option, methods in _switched_off(platform, switches).items()
        if _option_value(options.get(option, "yes")) == "no"
        for method in methods
    }
    kept = [method for method in renderers if method not in gone]
    if renderers and not kept:
        raise ValueError("The build profile leaves the recipe no rendering method")
    return kept


def engine_renderers(
    renderers: Collection[str], platform: str, environment: str, switches: bool
) -> list[str]:
    """
    Return the rendering methods an engine built for a recipe's renderers can run.

    Godot's iOS Simulator build turns Metal and Vulkan off, and without Godot 4.8's
    switches a RenderingDevice driver brings both of its renderers.
    """
    methods = set(renderers)
    if platform == "ios" and environment == "simulator":
        methods -= set(_RD_METHODS)
    elif not switches and methods & set(_RD_METHODS):
        methods |= set(_RD_METHODS)
    return [method for method in RENDERING_METHODS if method in methods]


def _needs_shader_compiler(args: argparse.Namespace) -> bool:
    """Return whether a recipe's renderers need RenderingDevice's shader compiler."""
    if args.platform == "ios" and args.environment == "simulator":
        return False
    return any(method in args.renderers for method in _RD_METHODS)


def with_renderer_modules(
    args: argparse.Namespace, graph: Mapping[str, Any]
) -> list[str]:
    """
    Return the requested modules with glslang where a RenderingDevice method is requested.

    RenderingDevice compiles its shaders at run time with glslang, which Godot builds only
    as a module, so an engine with Metal or Vulkan and without it could not render. Godot's
    iOS Simulator build has neither driver and rejects glslang.
    """
    modules = list(args.modules)
    if not _needs_shader_compiler(args) or "glslang" not in graph:
        return modules
    return modules if "glslang" in modules else [*modules, "glslang"]


def require_renderer_options_unset(
    derived: Iterable[str], options: Iterable[str]
) -> None:
    """Fail for build_options that set what a recipe's renderers decide."""
    keys = {option.partition("=")[0] for option in derived}
    taken = sorted(
        key for key in (option.partition("=")[0] for option in options) if key in keys
    )
    if taken:
        raise ValueError(
            "renderers decides " + ", ".join(taken) + "; remove them from build_options"
        )


# ==== Compile options =========================================================


_APPLE_TOOLCHAIN_WARNINGS = [
    "-Wno-thread-safety",
    "-Wno-shorten-64-to-32",
    "-Wno-undeclared-selector",
]

# Warning groups that the target platform's Bazel C++ toolchain enables by default but
# upstream's SCons build does not, and that unmodified engine sources trigger:
# apple_support's default compile and Objective-C warnings, and the NDK
# toolchain's -Wc++2a-extensions.
TOOLCHAIN_ONLY_WARNINGS = {
    "android": ["-Wno-variadic-macro-arguments-omitted", "-Wno-c++20-designator"],
    "ios": _APPLE_TOOLCHAIN_WARNINGS,
    "macos": _APPLE_TOOLCHAIN_WARNINGS,
}

# Optimization and debug information follow Bazel's compilation mode, --copt
# and --per_file_copt, and stripping follows --strip, as for any C++ library:
# upstream's flags for them are not replayed. -ObjC and other options that only
# start alike stay.
_BAZEL_OWNED_OPTION = re.compile(
    r"-O(?:\d|s|z|g|fast|size|none|unchecked)?|-g.*|-s|-Wl,-[Sx]"
)


# The link option that drops the engine's unreached code, per platform that needs one of
# its own (engine_link_options), and the compile options that give GNU ld something to drop.
_DEAD_STRIPPING = {"ios": "-Wl,-dead_strip", "linuxbsd": "-Wl,--gc-sections"}
_LINUX_SECTIONS = ("-ffunction-sections", "-fdata-sections")


def bazel_owned(option: str) -> bool:
    """Return whether Bazel's flags decide an upstream compile or link option."""
    return _BAZEL_OWNED_OPTION.fullmatch(option) is not None


def platform_compile_options(platform: str, options: list[str]) -> list[str]:
    # Disable the toolchain-only groups before the upstream flags, so an upstream
    # or patched build that enables one of them still reports it.
    options = [
        *TOOLCHAIN_ONLY_WARNINGS.get(platform, []),
        *(option for option in options if not bazel_owned(option)),
    ]
    # With debug information, the NDK toolchain records the sandbox directory as
    # the compilation directory; apple_support already records ".".
    if platform == "android":
        options.append("-fdebug-compilation-dir=.")
    # A section per function and datum, which the link drops when nothing reaches it
    # (engine_link_options).
    if platform == "linuxbsd":
        options.extend(_LINUX_SECTIONS)
    # apple_support defines OS_IOS for Objective-C. Godot uses that identifier
    # for its OS_IOS C++ class and uses IOS_ENABLED as its platform macro.
    return [*options, "-UOS_IOS"] if platform == "ios" else options


def engine_link_options(platform: str, options: list[str]) -> list[str]:
    """Return engine_library's link flags: upstream's, without those Bazel decides."""
    library = [option for option in options if not bazel_owned(option)]
    # The application links every engine object, where SCons links its libraries'
    # objects only when something reaches them. Dead stripping removes those it
    # never reaches, such as SDL's HID backend, whose PLATFORM_hid_* functions iOS
    # does not build, or the font subsetting of HarfBuzz, whose table sources Godot
    # leaves out. GNU ld then also ignores what only their code references. Upstream
    # strips on macOS and Android already.
    stripping = _DEAD_STRIPPING.get(platform)
    if stripping and stripping not in library:
        library.append(stripping)
    return library


_DEPLOYMENT_FLAGS = (
    "-mmacosx-version-min=",
    "-miphoneos-version-min=",
    "-mios-simulator-version-min=",
)


def deployment_target(options: Iterable[object]) -> str:
    """The deployment target Godot's SCons platform sets, or empty where it sets none.

    Bazel's Apple toolchains pass their own target version, so the flag is never
    replayed; the recipe records the value so macOS engines compile for Godot's floor
    whatever the build's --macos_minimum_os says.
    """
    for option in options:
        text = str(option)
        if text.startswith(_DEPLOYMENT_FLAGS):
            return text.split("=", 1)[1]
    return ""


# Options whose following argument is dropped with them: Bazel's C++ toolchain owns
# dependency discovery and its declared .d output (replaying SCons' flags duplicates
# -MD and can redirect it), the output, the architecture, the SDK and the target.
_OPTIONS_WITH_ARGUMENT = (
    "-MF",
    "-MT",
    "-MQ",
    "-o",
    "-arch",
    "-isysroot",
    "--sysroot",
    "-target",
    "--target",
)

# Options Bazel's toolchain replaces; some start a longer option, as -MF does -MFb.d.
_REPLACED_OPTIONS = ("-MD", "-MMD", "-MP", "-c")

_REPLACED_PREFIXES = (
    "-MF",
    "-MT",
    "-MQ",
    "--sysroot=",
    "--target=",
    "-fdiagnostics-color=",
    "-fcolor-diagnostics",
    *_DEPLOYMENT_FLAGS,
)


def _is_replaced_option(option: str, source: str, root: Path) -> bool:
    """Return whether Bazel's toolchain replaces a compile option, so it is not replayed."""
    # debug_paths_relative maps the configure directory, which compile actions
    # never see: they name sources relative to the execution root.
    configure_prefix_map = f"-ffile-prefix-map={root}=."
    return option in (
        *_REPLACED_OPTIONS,
        source,
        str(root / source),
        configure_prefix_map,
    ) or option.startswith(_REPLACED_PREFIXES)


def _sdk_prefixes(sdk_roots: Iterable[str | None]) -> list[str]:
    """Return the SDK roots that the recipe's platform sets, without a trailing slash."""
    return [str(sdk).rstrip("/") for sdk in sdk_roots if sdk]


def _sdk_include(include: str, sdk_prefixes: Iterable[str]) -> str | None:
    """
    Return an SDK include path as an option to replay, or None for other paths.

    Godot includes some framework headers without their framework prefix
    (e.g. <ES3/gl.h>). Preserve those search paths using apple_support's
    SDK placeholder, resolved by the selected target compiler wrapper.
    """
    for prefix in sdk_prefixes:
        if include == prefix or include.startswith(prefix + "/"):
            return "-I__BAZEL_XCODE_SDKROOT__" + include[len(prefix) :]
    return None


def _upstream_options(
    command: Iterable[object], source: str, root: Path
) -> Iterator[str]:
    """Yield the options that Bazel's toolchain does not replace, as one -I<path> each."""
    options = iter(command)
    for raw_option in options:
        option = str(raw_option)
        if option in _OPTIONS_WITH_ARGUMENT:
            next(options, None)
        elif option == "-I":
            yield "-I" + str(next(options))
        elif not _is_replaced_option(option, source, root):
            yield option


def normalize_command(
    command: Sequence[object],
    source: str,
    root: Path,
    sdk_roots: Iterable[str | None] = (),
) -> tuple[list[str], list[str]]:
    """Retain upstream flags while allowing Bazel to select compiler and SDK."""
    copts: list[str] = []
    includes: list[str] = []
    sdk_prefixes = _sdk_prefixes(sdk_roots)
    # SCons' compiler executable is deliberately not replayed.
    for option in _upstream_options(command[1:], source, root):
        if option.startswith("-I"):
            sdk_option = _sdk_include(option[2:], sdk_prefixes)
            if sdk_option is None:
                includes.append(relative(option[2:], root))
            else:
                copts.append(sdk_option)
        elif str(root) in option:
            raise ValueError(f"Absolute engine path in compiler option: {option}")
        else:
            copts.append(option)
    return copts, includes


_SWIFT_VALUE_OPTIONS = {
    "-import-objc-header": "bridging_header",
    "-emit-objc-header-path": "generated_header",
}

_SWIFT_VALUE_FLAGS = ("-module-name", "-swift-version", *_SWIFT_VALUE_OPTIONS)

# rules_swift selects the SDK and the object layout, and includes the source root
# through the declared C++ compilation context.
_SWIFT_DROPPED_WITH_VALUE = ("-target", "-sdk")

_SWIFT_DROPPED = ("-emit-object", "-wmo", "-I./")

_SWIFT_KEPT = (
    "-warnings-as-errors",
    "-cxx-interoperability-mode=default",
    "-parse-as-library",
)


def _apply_swift_value_flag(
    result: dict[str, Any], flag: str, value: str, root: Path
) -> None:
    if flag == "-module-name":
        result["module_name"] = value
    elif flag == "-swift-version":
        result["copts"].extend([flag, value])
    else:
        result[_SWIFT_VALUE_OPTIONS[flag]] = relative(value, root)


def _apply_swift_flag(
    result: dict[str, Any], flag: str, values: Iterator[str], root: Path
) -> None:
    """Fold an upstream Swift flag, and the value that follows it, into the options."""
    if flag in _SWIFT_DROPPED_WITH_VALUE:
        next(values)
    elif flag in _SWIFT_KEPT:
        result["copts"].append(flag)
    elif flag in _SWIFT_VALUE_FLAGS:
        _apply_swift_value_flag(result, flag, next(values), root)
    elif flag not in _SWIFT_DROPPED and not bazel_owned(flag):
        # The rest is dropped: rules_swift selects it from the compilation mode.
        raise ValueError("Unsupported upstream Swift compiler option: " + flag)


def swift_module_options(flags: Iterable[str], root: Path) -> dict[str, Any]:
    """Keep upstream Swift semantics while rules_swift owns SDKs and outputs."""
    result: dict[str, Any] = {
        "module_name": "godot_swift_module",
        "bridging_header": None,
        "generated_header": None,
        "copts": [],
    }
    values = iter(flags)
    for flag in values:
        _apply_swift_flag(result, flag, values, root)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", result["module_name"]):
        raise ValueError("Invalid upstream Swift module name: " + result["module_name"])
    # _apply_swift_flag sets it through the dictionary, which type checkers do not follow.
    if not result.get("bridging_header"):
        raise ValueError("Upstream Swift module has no declared bridging header")
    return result


def _header_includes(root: Path, header: str, wanted: str, seen: set[str]) -> bool:
    """Return whether a header, directly or through the headers it includes, is wanted."""
    if header == wanted:
        return True
    if header in seen:
        return False
    seen.add(header)
    for name in re.findall(
        r'^\s*#(?:include|import)\s+"([^"]+)"',
        (root / header).read_text(),
        re.MULTILINE,
    ):
        path = root / name
        if not path.is_file():
            path = root / Path(header).parent / name
        if path.is_file() and _header_includes(
            root, relative(path.resolve(), root), wanted, seen
        ):
            return True
    return False


def _check_mergeable(first: dict[str, Any], second: dict[str, Any]) -> None:
    """Reject Swift module declarations that need distinct rules_swift targets."""
    if first["module_name"] != second["module_name"] or first["copts"] != second["copts"]:
        raise ValueError(
            "Incompatible upstream Swift modules require distinct rules_swift targets"
        )
    header_names = {
        Path(option["generated_header"]).name
        for option in [first, second]
        if option["generated_header"]
    }
    if len(header_names) > 1:
        raise ValueError("Incompatible upstream Swift generated header names")


def merge_swift_module_options(
    first: dict[str, Any] | None, second: dict[str, Any], root: Path
) -> dict[str, Any]:
    """Merge upstream's overlapping driver/platform Swift module declarations."""
    root = root.resolve()
    if first is None or first == second:
        return second
    _check_mergeable(first, second)
    generated_header = first["generated_header"] or second["generated_header"]
    # The iOS bridge imports the shared Apple bridge. Compile the deduplicated
    # source set once with that superset, rather than duplicate Swift classes.
    for superset, subset in ((first, second), (second, first)):
        if _header_includes(
            root, superset["bridging_header"], subset["bridging_header"], set()
        ):
            return {
                **superset,
                "generated_header": superset["generated_header"] or generated_header,
            }
    raise ValueError("Upstream Swift bridging headers have no common declared superset")


# ==== Environment reads =======================================================


_ALLOWED_ENV_METHODS = ("get", "NoCache", "Detect")

_SCALAR_TYPES = (str, bool, int, float)


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, _SCALAR_TYPES)


def _is_env(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "env"


def _is_env_load(node: ast.AST) -> bool:
    return _is_env(node) and isinstance(getattr(node, "ctx", None), ast.Load)


def _parameter_names(arguments: ast.arguments) -> set[str]:
    positional = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    variadic = [arguments.vararg, arguments.kwarg]
    return {argument.arg for argument in [*positional, *variadic] if argument}


def _definition_names(nodes: Sequence[ast.AST]) -> set[str]:
    """Return the names that nested definitions, imports and handlers bind."""
    functions = [
        node
        for node in nodes
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    names = {node.name for node in functions[1:]}
    names.update(
        node.asname or node.name.split(".")[0]
        for node in nodes
        if isinstance(node, ast.alias)
    )
    names.update(
        node.name
        for node in nodes
        if isinstance(node, (ast.ClassDef, ast.ExceptHandler)) and node.name
    )
    return names


def _local_names(tree: ast.AST) -> set[str]:
    """
    Return the names that a generator's source binds itself.

    They are its variables, nested definitions, imports and, for its own function,
    parameters.
    """
    nodes = list(ast.walk(tree))
    names = {
        node.id
        for node in nodes
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    names |= _definition_names(nodes)
    function = next(
        (
            node
            for node in nodes
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        None,
    )
    if function is not None:
        names |= _parameter_names(function.args)
    return names


def _allowed_env_uses(tree: ast.AST) -> set[int]:
    """Return the ids of the nodes where env may appear: as an owner or as an argument."""
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Subscript, ast.Attribute)):
            allowed.add(id(node.value))
        elif isinstance(node, ast.Call):
            allowed.update(id(argument) for argument in node.args)
            allowed.update(id(keyword.value) for keyword in node.keywords)
    return allowed


def _check_env_escapes(tree: ast.AST) -> None:
    """Reject a use of env that the capture cannot follow: an alias or an escape."""
    allowed = _allowed_env_uses(tree)
    for node in ast.walk(tree):
        if _is_env_load(node) and id(node) not in allowed:
            raise ValueError(
                "Unsupported generator environment alias or escape; read env directly or pass it to a named Python helper"
            )


def _literal_key(subscript: ast.Subscript) -> str:
    key = subscript.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    raise ValueError("Godot generators must use literal environment keys")


def _env_call_key(call: ast.Call) -> str | None:
    """Return the key that an env.get call reads, rejecting the other env methods."""
    callee = call.func
    if not (isinstance(callee, ast.Attribute) and _is_env(callee.value)):
        return None
    if callee.attr not in _ALLOWED_ENV_METHODS:
        raise ValueError(f"Unsupported generator environment method: env.{callee.attr}")
    if callee.attr == "get" and call.args:
        return ast.literal_eval(call.args[0])
    return None


def _env_read(node: ast.AST, called: set[int]) -> tuple[str, bool] | None:
    """Return the environment name that a node reads, and whether it is an attribute."""
    if isinstance(node, ast.Call):
        key = _env_call_key(node)
        return None if key is None else (key, False)
    if isinstance(node, ast.Subscript) and _is_env(node.value):
        return _literal_key(node), False
    if isinstance(node, ast.Attribute):
        return (
            (node.attr, True) if _is_env(node.value) and id(node) not in called else None
        )
    return None


def _passes_env(node: ast.AST) -> TypeGuard[ast.Call]:
    """Return whether a node is a call that receives env as an argument."""
    if not isinstance(node, ast.Call):
        return False
    arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
    return any(_is_env(argument) for argument in arguments)


def _module_function(
    callee: ast.Attribute, namespace: Mapping[str, object], local_names: set[str]
) -> object:
    """Return the function that an attribute of a module in the namespace names."""
    if not isinstance(callee.value, ast.Name) or callee.value.id in local_names:
        return None
    owner = namespace.get(callee.value.id)
    return getattr(owner, callee.attr, None) if inspect.ismodule(owner) else None


def _named_function(
    call: ast.Call, namespace: Mapping[str, object], local_names: set[str]
) -> object:
    """Return the function a call names, directly or through a module, in the generator's globals."""
    callee = call.func
    if isinstance(callee, ast.Name) and callee.id not in local_names:
        return namespace.get(callee.id)
    if isinstance(callee, ast.Attribute):
        return _module_function(callee, namespace, local_names)
    return None


def _positional_env_is_named(
    call: ast.Call, parameters: Mapping[str, inspect.Parameter]
) -> bool:
    """Return whether every positional env argument binds to a parameter named env."""
    names = list(parameters)
    return all(
        not _is_env(argument) or (index < len(names) and names[index] == "env")
        for index, argument in enumerate(call.args)
    )


def _keyword_env_is_named(
    call: ast.Call, parameters: Mapping[str, inspect.Parameter]
) -> bool:
    """Return whether every keyword env argument binds to a parameter named env."""
    parameter = parameters.get("env")
    accepts = parameter is not None and parameter.kind not in (
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    )
    return all(
        not _is_env(keyword.value) or (keyword.arg == "env" and accepts)
        for keyword in call.keywords
    )


def _check_env_arguments(call: ast.Call, function: FunctionType) -> None:
    """Reject a call that does not hand env to a parameter named env of the function."""
    parameters = inspect.signature(function).parameters
    if not (
        _positional_env_is_named(call, parameters)
        and _keyword_env_is_named(call, parameters)
    ):
        raise ValueError(
            f"Generator helper {function.__name__} must receive the environment through a parameter named env"
        )
    if any(isinstance(argument, ast.Starred) for argument in call.args):
        raise ValueError(
            f"Generator helper {function.__name__} cannot forward env with dynamic positional arguments"
        )


def _env_helper(
    call: ast.Call, namespace: Mapping[str, object], local_names: set[str]
) -> FunctionType:
    """Return the Python helper that receives env in a call, once its use of env is checked."""
    function = _named_function(call, namespace, local_names)
    if not inspect.isfunction(function):
        raise ValueError(
            f"Unsupported generator helper receiving env: {ast.unparse(call.func)}; use a directly named Python function"
        )
    _check_env_arguments(call, function)
    return function


def _scalar_values(
    env: Any, keys: Collection[str], attributes: Collection[str]
) -> dict[str, str | bool | int | float | None]:
    result: dict[str, str | bool | int | float | None] = {}
    for key in sorted({*keys, *attributes}):
        if key not in attributes and key not in env:
            # Preserve absence so env.get(key, default) keeps its default.
            continue
        value = getattr(env, key) if key in attributes else env.get(key)
        if not _is_scalar(value):
            raise ValueError(f"Generator environment {key} is not a serializable scalar")
        result[key] = value
    return result


def _environment_reads(
    code: str, namespace: Mapping[str, object] | None
) -> tuple[set[str], set[str], list[FunctionType]]:
    """Return the keys and attributes of env that the code reads, and the helpers getting env."""
    tree = ast.parse(code)
    local_names = _local_names(tree)
    _check_env_escapes(tree)
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    keys: set[str] = set()
    attributes: set[str] = set()
    helpers: list[FunctionType] = []
    for node in ast.walk(tree):
        read = _env_read(node, called)
        if read is not None:
            (attributes if read[1] else keys).add(read[0])
        # Helpers receiving the same environment contribute their reads.
        # This includes upstream's production/dev Zstd compression options.
        if namespace is not None and _passes_env(node):
            helpers.append(_env_helper(node, namespace, local_names))
    return keys, attributes, helpers


def scalar_environment(
    env: Any,
    code: str,
    namespace: Mapping[str, object] | None = None,
    seen: set[FunctionType] | None = None,
) -> dict[str, str | bool | int | float | None]:
    # Capture only environment values read by a builder. In particular, changing
    # the module allowlist must not invalidate unrelated shader/font generators.
    keys, attributes, helpers = _environment_reads(code, namespace)
    result = _scalar_values(env, keys, attributes)
    seen = set() if seen is None else seen
    for function in helpers:
        if function not in seen:
            seen.add(function)
            helper_code = textwrap.dedent(inspect.getsource(function))
            result.update(
                scalar_environment(env, helper_code, function.__globals__, seen)
            )
    return result


def _normalize_string(value: str, root: Path) -> str:
    return relative(value, root) if value.startswith(str(root) + "/") else value


def normalize_value(value: object, root: Path) -> object:
    if isinstance(value, str):
        return _normalize_string(value, root)
    if isinstance(value, dict):
        return {key: normalize_value(item, root) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_value(item, root) for item in value]
    if _is_scalar(value):
        return value
    raise ValueError(f"Unsupported SCons Value payload: {type(value).__name__}")


def _shader_includes(root: Path, path: Path) -> list[str]:
    """Return the files that a shader source includes, relative to the source root."""
    if not path.is_file() or path.suffix not in (".glsl", ".glslinc", ".inc", ".h"):
        return []
    includes = re.findall(r'^\s*#include\s+"([^"]+)"', path.read_text(), re.MULTILINE)
    return [
        relative(
            (
                (root if include.startswith("thirdparty/") else path.parent) / include
            ).resolve(),
            root,
        )
        for include in includes
    ]


def include_closure(root: Path, sources: Collection[str]) -> set[str]:
    """Godot shader builders recursively read #include files themselves."""
    root = root.resolve()
    found = set(sources)
    pending = list(dict.fromkeys(sources))
    while pending:
        for logical in _shader_includes(root, root / pending.pop()):
            if logical not in found:
                found.add(logical)
                pending.append(logical)
    return found


# ==== Capture =================================================================


_OBJECT_SUFFIXES = (".o", ".os")

_CXX_SUFFIXES = (".cc", ".cpp", ".cxx", ".mm")


def _has_object_target(target_names: Iterable[str]) -> bool:
    return any(Path(name).suffix in _OBJECT_SUFFIXES for name in target_names)


def _is_swift_objects(sources: Sequence[Any], target_names: Sequence[str]) -> bool:
    """Return whether an executor compiles Swift sources into objects."""
    return (
        bool(sources)
        and all(Path(str(source)).suffix == ".swift" for source in sources)
        and _has_object_target(target_names)
    )


def _is_compiled_source(sources: Sequence[Any], target_names: Sequence[str]) -> bool:
    """Return whether an executor compiles one C-family or assembler source to an object."""
    return (
        len(sources) == 1
        and Path(str(sources[0])).suffix in SOURCE_SUFFIXES
        and _has_object_target(target_names)
    )


def _is_link_target(target_names: Iterable[str]) -> bool:
    return any(name.startswith(("bin/godot", "bin/libgodot")) for name in target_names)


def _compile_variable(suffix: str, shared: bool) -> str:
    """Return the SCons variable that holds the compile command for a source suffix."""
    if suffix in (".S", ".s"):
        return "$ASPPCOM" if suffix == ".S" else "$ASCOM"
    kind = "CXXCOM" if suffix in _CXX_SUFFIXES else "CCCOM"
    return ("$SH" if shared else "$") + kind


def _is_android_library(name: str) -> bool:
    return name.startswith("platform/android/java/lib/libs/") and name.endswith(
        ("/libgodot_android.so", "/libc++_shared.so")
    )


def _is_bazel_owned_output(platform: str, target_names: Sequence[str]) -> bool:
    """Return whether Bazel rules produce the targets, so no action replays them."""
    # rules_android owns AAR/JNI staging; do not replay SCons Move/Copy
    # actions into a mutable Gradle source tree.
    if platform == "android" and all(map(_is_android_library, target_names)):
        return True
    # rules_cc rules own archiving and retain every captured object.
    return all(Path(name).suffix in (".a", ".lib") for name in target_names)


def is_directory_action(actions: Sequence[Any]) -> bool:
    return (
        len(actions) == 1
        and getattr(getattr(actions[0], "execfunction", None), "__name__", "")
        == "MkdirFunc"
    )


def _generator_function(
    target_names: Sequence[str], actions: Sequence[Any]
) -> FunctionType:
    """Return the Python function that an executor's one action runs."""
    if len(actions) != 1 or not hasattr(actions[0], "execfunction"):
        raise ValueError(
            "Unsupported upstream Godot action for "
            + ", ".join(target_names)
            + ": "
            + ", ".join(type(action).__name__ for action in actions)
        )
    return actions[0].execfunction


def _generator_sources(
    root: Path, sources: Iterable[Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return a generator's source entries and the paths of those that are files."""
    entries: list[dict[str, Any]] = []
    files: list[str] = []
    for source in sources:
        if source.__class__.__module__ == "SCons.Node.Python":
            # Node-valued dictionaries used by custom module registration
            # are normalized to stable repository-relative paths.
            entries.append({"value": normalize_value(source.read(), root)})
        else:
            logical = relative(source, root)
            files.append(logical)
            entries.append({"path": logical})
    return entries, files


def _enabled_modules(
    link_environment: Any, selected_modules: Collection[str]
) -> list[str]:
    """Return the modules Godot enabled, which must include every selected module."""
    enabled = sorted(link_environment.module_list)
    missing = sorted(set(selected_modules) - set(enabled))
    if missing:
        raise ValueError(
            "Godot disabled requested modules for this configuration: "
            + ", ".join(missing)
        )
    require_one_text_server(enabled)
    return enabled


def _library_option(library: object) -> str | None:
    """Return the link option for a library SCons names, or None when it is no linked library."""
    if not isinstance(library, str):
        return None
    if library.startswith("-"):
        return library
    return None if library.endswith((".a", ".o", ".lib")) else "-l" + library


def _link_settings(
    link_environment: Any, platform: str, root: Path
) -> tuple[list[str], str]:
    """Return the engine's link options and its deployment target, from the link environment."""
    # SCons includes feature probes, but the action graph never retains host
    # compiler paths, SDK roots, arch flags, or an implicit SCons cache.
    linkopts = shlex.split(link_environment.subst("$LINKFLAGS $_LIBDIRFLAGS"))
    # Godot's Apple platforms put it in CCFLAGS; macOS also in LINKFLAGS.
    minimum_os = deployment_target(
        shlex.split(link_environment.subst("$CCFLAGS $LINKFLAGS"))
    )
    linkopts, _ = normalize_command(["linker", *linkopts], "", root)
    libraries = map(_library_option, link_environment.get("LIBS", []))
    linkopts.extend(option for option in libraries if option is not None)
    return engine_link_options(platform, linkopts), minimum_os


class _Capture:
    """The configured build graph, accumulated from SCons's recorded executors."""

    def __init__(self, platform: str, root: Path) -> None:
        self.platform = platform
        self.root = root
        self.groups: defaultdict[
            tuple[str, tuple[str, ...], tuple[str, ...]], list[str]
        ] = defaultdict(list)
        self.swift_sources: list[str] = []
        self.swift_options: dict[str, Any] | None = None
        self.generators: list[tuple[dict[str, Any], set[str]]] = []
        self.version = ""
        self.link_environment: Any = None
        self._emitted: set[tuple[str, ...]] = set()

    def add(self, executor: Any) -> None:
        """Record what an executor builds: an object, the link, a generator or nothing."""
        targets = executor.get_all_targets()
        sources = executor.get_all_sources()
        env = executor.get_build_env()
        actions = executor.get_action_list()
        target_names = self._claim(targets, actions)
        if target_names is None:
            return
        if _is_swift_objects(sources, target_names):
            self._add_swift_objects(targets, sources, env)
        # A source node may itself be produced by a source generator.
        elif _is_compiled_source(sources, target_names):
            self._add_compiled_source(targets, sources, env)
        elif _is_link_target(target_names):
            self.link_environment = env
        elif not _is_bazel_owned_output(self.platform, target_names):
            self._add_generator(target_names, sources, env, actions)

    def _claim(self, targets: Sequence[Any], actions: Sequence[Any]) -> list[str] | None:
        """Return the names of the targets that no action recorded before, or None."""
        if is_directory_action(actions):
            return None
        target_names = [relative(target, self.root) for target in targets]
        if not targets or tuple(target_names) in self._emitted:
            return None
        self._emitted.add(tuple(target_names))
        return target_names

    def _add_swift_objects(self, targets: Any, sources: Any, env: Any) -> None:
        self.swift_sources.extend(relative(source, self.root) for source in sources)
        if env.get("SWIFTCFLAGS"):
            command = env.subst_list("$SWIFTCFLAGS", target=targets, source=sources)[0]
            options = swift_module_options(list(map(str, command)), self.root)
            self.swift_options = merge_swift_module_options(
                self.swift_options, options, self.root
            )

    def _add_compiled_source(self, targets: Any, sources: Any, env: Any) -> None:
        source = relative(sources[0], self.root)
        suffix = Path(source).suffix
        language = "objc" if suffix in (".m", ".mm") else "cc"
        shared = targets[0].get_builder().get_name(env) == "SharedObject"
        variable = _compile_variable(suffix, shared)
        command = list(
            map(str, env.subst_list(variable, target=targets, source=sources)[0])
        )
        copts, includes = normalize_command(
            command,
            source,
            self.root,
            [
                env.get("APPLE_SDK_PATH"),
                env.get("IOS_SDK_PATH"),
                env.get("MACOS_SDK_PATH"),
            ],
        )
        copts = platform_compile_options(self.platform, copts)
        # Apple enables ARC globally, but it only applies to Objective-C.
        if language == "cc":
            copts = [option for option in copts if option != "-fobjc-arc"]
        self.groups[(language, tuple(copts), tuple(includes))].append(source)

    def _add_generator(
        self, target_names: list[str], sources: Any, env: Any, actions: Sequence[Any]
    ) -> None:
        function = _generator_function(target_names, actions)
        source_file = inspect.getsourcefile(function)
        if source_file is None:
            raise ValueError(f"Upstream Godot action {function.__name__} has no source")
        code_file = Path(source_file).resolve()
        # Postlink bundle/debug-sign actions belong to application packaging rules.
        if any(name.startswith("bin/") for name in target_names):
            return
        code = textwrap.dedent(inspect.getsource(function))
        spec: dict[str, Any] = {
            "code_file": relative(code_file, self.root),
            "function": function.__name__,
            "targets": target_names,
            "sources": [],
            "environment": scalar_environment(env, code, function.__globals__),
        }
        if code_file.suffix != ".py":
            spec["inline"] = code
        spec["sources"], files = _generator_sources(self.root, sources)
        dependencies = include_closure(self.root, files)
        if spec["function"] in REVISION_FILES:
            dependencies |= self._add_revision(spec)
        self.generators.append((spec, dependencies))

    def _add_revision(self, spec: dict[str, Any]) -> set[str]:
        """Name the files that a version generator's source supplies at build time."""
        files = REVISION_FILES[spec["function"]]
        spec["sources"][0]["files"] = files
        if spec["function"] == "version_info_builder":
            self.version = version_name(spec["sources"][0]["value"])
        return set(files.values())

    def graph(self, selected_modules: Collection[str]) -> dict[str, Any]:
        """Return the captured graph as plain data."""
        if not self.groups or self.link_environment is None:
            raise ValueError("Godot configure produced no engine compilation/link graph")
        if not self.version:
            raise ValueError(
                "Godot configure produced no version_generated.gen.h generator"
            )
        enabled = _enabled_modules(self.link_environment, selected_modules)
        linkopts, minimum_os = _link_settings(
            self.link_environment, self.platform, self.root
        )
        return {
            "groups": [
                [language, list(copts), list(includes), sources]
                for (language, copts, includes), sources in self.groups.items()
            ],
            "swift_sources": self.swift_sources,
            "swift_options": self.swift_options,
            # By their outputs, so recipes whose SCons visits generators in another order
            # share one list in a lock file.
            "generators": [
                {
                    "spec": build_profile.class_list_spec(spec),
                    "dependencies": sorted(dependencies),
                }
                for spec, dependencies in sorted(
                    self.generators, key=lambda item: item[0]["targets"]
                )
            ],
            "version": self.version,
            "modules": enabled,
            "linkopts": linkopts,
            "minimum_os": minimum_os,
        }


def collect(args: argparse.Namespace, executors: Iterable[Any]) -> dict[str, Any]:
    """
    Return the configured build graph of SCons's recorded executors as plain data.

    The graph names only paths relative to the source root and the flags Bazel replays,
    so it is the same on every host that configures the recipe, and a recipe's pin
    stores it. render() turns it into the repository's BUILD file.
    """
    capture = _Capture(args.platform, Path.cwd().resolve())
    for executor in executors:
        capture.add(executor)
    return capture.graph(args.selected_modules)


# ==== Configurations ==========================================================


def _add_environment_option(args: argparse.Namespace) -> None:
    """Pass an iOS recipe's device or simulator environment to Godot as its option."""
    if args.platform == "ios":
        if not args.environment:
            raise ValueError(
                "iOS recipes need an explicit device or simulator environment"
            )
        simulator = "yes" if args.environment == "simulator" else "no"
        args.options.append("simulator=" + simulator)
    elif args.environment:
        raise ValueError("The environment is only valid for iOS recipes")


def _add_renderer_options(args: argparse.Namespace, root: Path) -> None:
    """Add the upstream options of a recipe's renderers and the methods its engine runs."""
    args.engine_renderers = []
    if not args.renderers:
        return
    switches = has_renderer_switches(root)
    if args.build_profile:
        profiled = build_profile.read_profile(root / args.build_profile)
        args.renderers = profile_renderers(
            args.renderers, build_profile.build_options(profiled), args.platform, switches
        )
    derived = renderer_options(args.renderers, args.platform, switches)
    require_renderer_options_unset(derived, args.options)
    args.options = [*args.options, *derived]
    args.engine_renderers = engine_renderers(
        args.renderers, args.platform, args.environment, switches
    )


def _derive(args: argparse.Namespace, root: Path) -> None:
    """Add what a configuration derives from the recipe and its build profile."""
    args.options = list(args.requested.options)
    args.renderers = list(args.requested.renderers)
    args.modules = list(args.requested.modules)
    check_options(args.options)
    _add_renderer_options(args, root)
    args.modules = with_renderer_modules(args, args.module_graph)
    args.selected_modules = module_closure(
        args.modules, args.module_graph, editor=args.build_target == "editor"
    )
    # Before SCons for the modules a recipe names; Godot's defaults are checked after it.
    require_one_text_server(args.selected_modules)
    args.build_profile_digest = ""
    if args.build_profile:
        require_consistent_profile(root / args.build_profile, args.options)
        args.build_profile_digest = profile_options_digest(root / args.build_profile)
    args.customizations = customizations(args)
    _add_environment_option(args)
    args.inputs_hash = inputs_hash(args)


# ==== Pinning =================================================================


# The files whose behavior a pinned graph depends on: the capture and its translation.
# Rendering a graph, render.py and include_graph.py, changes no pin.
_PIN_TOOLS = (
    Path(__file__).resolve(),
    Path(inspect.getfile(module_closure)).resolve(),
    Path(inspect.getfile(relative)).resolve(),
    Path(inspect.getfile(build_profile)).resolve(),
    Path(inspect.getfile(shapes_graph)).resolve(),
)

# The version of a recipe pin's layout.
PIN_FORMAT = 1


def pin_inputs(args: argparse.Namespace, scons: Path) -> dict[str, Any]:
    """
    Return what a recipe's pin digest covers besides its build profile's options.

    Its runtime variants share it and differ only in their profiles, so a recipe computes
    the digests of its tools, patches and custom modules once.
    """
    tools = [file_digest(path) for path in [*_PIN_TOOLS, scons / "SCons" / "__init__.py"]]
    return {
        "format": PIN_FORMAT,
        "source": args.source_sha256,
        "patches": [file_digest(path) for path in args.patch],
        "patch_strip": args.patch_strip,
        "custom_modules": file_digests(args.custom_modules_root, shapes_graph),
        "configuration": {
            "platform": args.platform,
            "cpu": args.cpu,
            "build_target": args.build_target,
            **_module_selection(args),
            "options": sorted(args.options),
        },
        "build_name": args.build_name,
        "tools": tools,
    }


def pin_digest(
    args: argparse.Namespace, scons: Path, inputs: Mapping[str, Any] | None = None
) -> str:
    """
    Return the digest a recipe's pin records: what its configured graph depends on.

    It covers the archive digest, the patches, the custom modules' structure, the
    recipe's platform, CPU, build target, modules and options, its build profile's
    options, its build name, and the SCons release and rules_godot code that capture the
    graph. Host state is no input: a pin is valid on every host. inputs, pin_inputs()'s
    result, spares computing it again.
    """
    inputs = inputs if inputs is not None else pin_inputs(args, scons)
    return "sha256:" + digest_of({**inputs, **_profile_input(args)})


def read_lock(lock: Path) -> dict[str, Any]:
    """Return a lock file's pins; none for a missing or empty file."""
    text = lock.read_text().strip() if lock.is_file() else ""
    return json.loads(text) if text else {}


def pinned_graph(
    pins: Mapping[str, Any], recipe: str, digest: str, profile: str = ""
) -> tuple[str, dict[str, Any] | None]:
    """
    Return a recipe's status in a lock file's pins, missing, stale or pinned, and its graph.

    With a runtime profile, the status and graph of the recipe's variant for it.
    """
    if profile:
        entry = pins.get("variants", {}).get(recipe, {}).get(profile)
    else:
        entry = pins.get("recipes", {}).get(recipe)
    if entry is None:
        return "missing", None
    if entry.get("digest") != digest:
        return "stale", None
    graph = dict(entry["graph"])
    # The lock stores generator lists that recipes share once, by digest.
    graph["generators"] = pins["generators"][graph["generators"]]
    return "pinned", graph


def write_pin(path: Path, digest: str, graph: Mapping[str, Any]) -> None:
    """Write one recipe's pin, the entry a lock file holds for it."""
    write_json(path, {"digest": digest, "graph": graph})


def variant_arguments(
    args: argparse.Namespace, root: Path, profile: str
) -> argparse.Namespace:
    """
    Return a recipe's arguments for its runtime variant of a registered runtime profile.

    The repository writes the variant's profile, the recipe's build options with the runtime
    profile's, to profile below the source root.
    """
    variant = argparse.Namespace(**vars(args))
    variant.build_profile = profile
    variant.registered_profile = True
    _derive(variant, root)
    return variant


_VARIANT_REASONS = {
    "missing": "has no pin for runtime profile {profile} of",
    "stale": "pins other sources, patches, modules, options or rules_godot code for "
    "runtime profile {profile} of",
}


def locked_variants(args: argparse.Namespace, root: Path, scons: Path) -> list[Variant]:
    """Return a pinned recipe's runtime variants, with the graphs of those with current pins."""
    pins = read_lock(args.lock)
    inputs = pin_inputs(args, scons)
    result = []
    for label, profile in args.runtime_profile:
        try:
            variant = variant_arguments(args, root, profile)
        except ValueError as error:
            result.append(Variant(label, args, None, f"{args.recipe}: {error}"))
            continue
        digest = pin_digest(variant, scons, inputs)
        status, graph = pinned_graph(pins, args.recipe, digest, label)
        reason = _VARIANT_REASONS.get(status, "").format(profile=label)
        error = args.unpinned_message.format(reason=reason) if graph is None else ""
        result.append(Variant(label, variant, graph, error))
    return result


def failure(output: str) -> str:
    """The exception a failed configuration's output reports, or else its last line."""
    lines = output.strip().splitlines() or ["the configuration failed"]
    errors = [line for line in lines if "Error: " in line]
    return (errors or lines)[-1].strip()


def captured_variants(args: argparse.Namespace, root: Path) -> list[Variant]:
    """
    Return a configured recipe's runtime variants, from the pins of their configurations.

    The repository configures each variant before the recipe, into <index>.json below
    args.variant_pins, or keeps its output in <index>.error where it could not.
    """
    result = []
    for index, (label, profile) in enumerate(args.runtime_profile):
        pin = args.variant_pins / f"{index}.json"
        if not pin.is_file():
            output = (args.variant_pins / f"{index}.error").read_text(errors="replace")
            error = f"The runtime profile {label} cannot apply to this recipe: "
            result.append(Variant(label, args, None, error + failure(output)))
            continue
        variant = variant_arguments(args, root, profile)
        graph = json.loads(pin.read_text())["graph"]
        result.append(Variant(label, variant, graph))
    return result


# ==== Command line ============================================================


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--scons", required=True)
    parser.add_argument(
        "--platform", choices=("macos", "linuxbsd", "android", "ios"), required=True
    )
    parser.add_argument("--cpu", required=True)
    parser.add_argument(
        "--build-target",
        choices=("editor", "template_debug", "template_release"),
        default="template_release",
    )
    parser.add_argument("--environment", choices=("", "device", "simulator"), default="")
    parser.add_argument("--expected-version", default="")
    # Empty: the ruleset's default, see requested_modules.
    parser.add_argument("--modules", default="")
    # Start from the modules upstream enables by default, as Godot's official builds do.
    parser.add_argument("--default-modules", action="store_true")
    # The build profile's path below the source root, where the recipe repository holds it.
    parser.add_argument("--build-profile", default="")
    # Comma-separated rendering methods; empty keeps Godot's drivers and build_options'.
    parser.add_argument("--renderers", default="")
    parser.add_argument("--custom-modules", action="append", default=[])
    # A custom module below _custom_modules, where the recipe or its pin action prepared
    # it (custom_modules.py).
    parser.add_argument(
        "--custom-module-name", dest="custom_module_names", action="append", default=[]
    )
    parser.add_argument("--option", dest="options", action="append", default=[])
    parser.add_argument("--build-name", default="custom")
    parser.add_argument("--source-sha256", default="")
    parser.add_argument("--patch", type=Path, action="append", default=[])
    parser.add_argument("--patch-strip", type=int, default=1)
    parser.add_argument(
        "--generator-bzl",
        default="@autoload_rules_godot//godot/engine/private:generator.bzl",
    )
    parser.add_argument("--cc-repository", default="@rules_cc")
    parser.add_argument("--platforms-repository", default="@platforms")
    parser.add_argument("--apple-repository", default="@apple_support")
    parser.add_argument("--swift-repository", default="@rules_swift")
    # Render the recipe's graph from this lock file's entry instead of configuring; without
    # a current entry, the engine targets fail with this message, which names the reason.
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--recipe", default="")
    parser.add_argument("--unpinned-message", default="")
    parser.add_argument(
        "--pin-bzl", default="@autoload_rules_godot//godot/engine/private:pin.bzl"
    )
    # The engine's registered runtime profiles with graph-shaping build options: each one's
    # label and the path of its variant's profile below the source root.
    parser.add_argument(
        "--runtime-profile",
        nargs=2,
        action="append",
        default=[],
        metavar=("LABEL", "PATH"),
    )
    # Where the repository configured the runtime variants of a recipe without a lock file.
    parser.add_argument("--variant-pins", type=Path)
    # The setting whose value, a build profile's label, selects a runtime variant.
    parser.add_argument(
        "--build-profile-label",
        default="@autoload_rules_godot//godot/private:build_profile_label",
    )
    # Configure and write the recipe's pin here instead of its BUILD file.
    parser.add_argument("--pin-output", type=Path)
    return parser


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    args = _argument_parser().parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.build_name):
        raise ValueError(
            f"build_name must be letters, digits and underscores: {args.build_name!r}"
        )
    args.modules = requested_modules(args.modules, args.default_modules)
    return args


def _add_custom_modules(args: argparse.Namespace, root: Path) -> None:
    """Name the directory of the custom modules below _custom_modules in the arguments."""
    args.custom_modules_root = (
        root / "_custom_modules" if args.custom_module_names else None
    )
    if args.custom_module_names:
        args.custom_modules.append("_custom_modules")


def _prepare(args: argparse.Namespace, root: Path) -> None:
    """Check the source and add the custom modules: what every configuration of a recipe shares."""
    args.version = source_version(root)
    require_expected_version(args.version, args.expected_version)
    (root / "engine_manifest.json").unlink(missing_ok=True)
    _add_custom_modules(args, root)
    args.module_graph = module_dependencies(
        root, [root / path for path in args.custom_modules]
    )
    # What the recipe requests, before its build profile and renderers add to it.
    args.requested = argparse.Namespace(
        options=list(args.options),
        renderers=[method for method in args.renderers.split(",") if method],
        modules=list(args.modules),
    )
    args.registered_profile = False
    args.runtime_profiles = [label for label, _ in args.runtime_profile]


def _complete_arguments(args: argparse.Namespace, root: Path) -> None:
    """Validate the recipe and add what it derives from the source: version, modules, hash."""
    _prepare(args, root)
    _derive(args, root)


def _install_capture(
    args: argparse.Namespace, root: Path, scons: Path, digest: str
) -> Callable[[], None]:
    """
    Make SCons record its executors and, after configuration, write the pin or the BUILD file.

    Return SCons's main function.
    """
    sys.path.insert(0, str(scons))
    import SCons.Executor
    import SCons.Script.Main
    import SCons.Variables

    executors: list[Any] = []
    original = SCons.Executor.Executor.__init__
    # The names of Godot's options, its modules' among them, as SConstruct declares them.
    options: set[str] = set()
    original_update = SCons.Variables.Variables.Update

    def record(executor: Any, *values: Any, **kwargs: Any) -> None:
        original(executor, *values, **kwargs)
        executors.append(executor)

    def update(variables: Any, *values: Any, **kwargs: Any) -> None:
        options.update(variables.keys())
        original_update(variables, *values, **kwargs)

    def finish(*_args: Any) -> None:
        if args.build_profile:
            require_known_options(root / args.build_profile, options)
        captured = collect(args, executors)
        if args.pin_output:
            write_pin(args.pin_output, digest, captured)
        else:
            render(args, captured, root, captured_variants(args, root))

    SCons.Executor.Executor.__init__ = record
    SCons.Variables.Variables.Update = update
    SCons.Script.Main._build_targets = finish
    return SCons.Script.Main.main


def load_detect(root: Path, platform: str) -> Any:
    """Load a platform's detect.py; the source root must be on sys.path for its imports."""
    path = root / "platform" / platform / "detect.py"
    spec = importlib.util.spec_from_file_location("_godot_detect", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    detect = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detect)
    return detect


def require_host_platform(root: Path, platform: str) -> None:
    """
    Reject a recipe whose platform this host cannot configure.

    SConstruct offers only the platforms whose detect.py can_build() accepts the host, such
    as linuxbsd on a non-macOS POSIX host, and otherwise prints its platform list. A
    registered execution or target platform can still select such a recipe. The source
    root must be on sys.path, since detect.py imports upstream's build helpers.
    """
    if not load_detect(root, platform).can_build():
        raise ValueError(
            f"Godot's platform/{platform}/detect.py rejects this host ({sys.platform}) "
            "or its environment, such as a missing SDK or cross toolchain; build without "
            "the execution or target platform that selects this recipe here, or "
            "configure it on a host that Godot accepts"
        )


# Stand-ins for the host tools Godot's Linux detect.py probes. Every package query fails, so a
# configuration reads none of the host's packages, which compile actions would not declare:
# Godot's bundled libraries and dynamically loaded system libraries only. Without
# wayland-scanner, whose generators are shell commands, Godot builds without Wayland.
_LINUX_PROBES = {
    "pkg-config": '#!/bin/sh\nif [ "$1" = "--version" ]; then echo 0.29.2; exit 0; fi\nexit 1\n',
    "wayland-scanner": "#!/bin/sh\nexit 1\n",
}


def stand_in_host(root: Path, platform: str, directory: Path) -> None:
    """
    Replace the host state Godot's configuration probes, so it is the same on every host.

    Linux probes tools on PATH; Android only checks that the SDK and Godot's NDK version
    exist and names their compilers, which Bazel's toolchain replaces.
    """
    if platform == "linuxbsd":
        for name, script in _LINUX_PROBES.items():
            tool = directory / name
            tool.write_text(script)
            tool.chmod(0o755)
        os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"
    elif platform == "android":
        sdk = directory / "android_sdk"
        (sdk / "ndk" / load_detect(root, platform).get_ndk_version()).mkdir(parents=True)
        os.environ["ANDROID_HOME"] = str(sdk)
        os.environ.pop("ANDROID_SDK_ROOT", None)


def _scons_arguments(args: argparse.Namespace) -> list[str]:
    """Return the command line that configures Godot's build for the recipe."""
    arguments = [
        "scons",
        "--quiet",
        "--no-cache",
        f"platform={args.platform}",
        f"arch={args.cpu}",
        f"target={args.build_target}",
        "modules_enabled_by_default=" + ("yes" if args.default_modules else "no"),
        "scu_build=no",
        "generate_bundle=no",
        "debug_symbols=no",
        "separate_debug_symbols=no",
        "lto=none",
        "use_static_cpp=no",
        *args.options,
        *(f"module_{module}_enabled=yes" for module in args.selected_modules),
    ]
    if args.platform == "android":
        arguments.append("generate_android_binaries=no")
    if args.custom_modules:
        arguments.append("custom_modules=" + ",".join(args.custom_modules))
    if args.build_profile:
        arguments.append(f"build_profile={args.build_profile}")
    return arguments


def _configure(
    args: argparse.Namespace, root: Path, scons_main: Callable[[], None]
) -> None:
    """Run SCons's configuration of Godot's build for the recipe."""
    with tempfile.TemporaryDirectory(prefix="godot_configure_") as stand_ins:
        stand_in_host(root, args.platform, Path(stand_ins))
        require_host_platform(root, args.platform)
        # Upstream reads the build name from the environment; the repository's
        # build_name attribute is its only source.
        os.environ["BUILD_NAME"] = args.build_name
        sys.argv = _scons_arguments(args)
        # SCons reports status 2 if no Taskmaster ran, since this deliberately stops
        # after configuration. Success is an atomically written BUILD + manifest, or the pin.
        marker = args.pin_output or root / "engine_manifest.json"
        try:
            scons_main()
        except SystemExit as error:
            if error.code not in (None, 0, 2) or not marker.is_file():
                raise


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_arguments(argv)
    root = Path(args.source).resolve()
    scons = Path(args.scons).resolve()
    _complete_arguments(args, root)
    digest = pin_digest(args, scons)
    if args.lock:
        status, pinned = pinned_graph(read_lock(args.lock), args.recipe, digest)
        if pinned is None:
            render_unpinned(args, status, root)
        else:
            render(args, pinned, root, locked_variants(args, root, scons))
        return
    if args.pin_output:
        args.pin_output = args.pin_output.resolve()
    scons_main = _install_capture(args, root, scons, digest)
    os.chdir(root)
    sys.path.insert(0, str(root))
    _configure(args, root, scons_main)


if __name__ == "__main__":
    main()

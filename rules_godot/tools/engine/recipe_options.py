"""
Check what a source recipe asks for and translate it into options of Godot's SCons build.

A recipe names its modules, its build options and its rendering methods. The checks reject
options that the ruleset or Bazel's flags decide. Each rendering method turns into the
switches of its driver.

Sections: Recipe options, Renderers.
"""

import argparse
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.engine import build_profile
from tools.engine.source_tree import digest_of

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

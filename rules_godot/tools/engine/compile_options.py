"""
Translate the compile and link options of upstream's SCons build for Bazel's toolchains.

Bazel's C++ and Swift toolchains choose the optimization, the debug information, the SDK,
the target and the outputs themselves, so the translation drops upstream's options for them
and keeps the rest.

Sections: Compile and link options, Swift modules.
"""

import re
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from tools.engine.source_tree import relative

# Optimization and debug information follow Bazel's compilation mode, --copt
# and --per_file_copt, and stripping follows --strip, as for any C++ library:
# upstream's flags for them are not replayed. -ObjC and other options that only
# start alike stay.
_BAZEL_OWNED_OPTION = re.compile(
    r"-O(?:\d|s|z|g|fast|size|none|unchecked)?|-g.*|-s|-Wl,-[Sx]"
)


def bazel_owned(option: str) -> bool:
    """Return whether Bazel's flags decide an upstream compile or link option."""
    return _BAZEL_OWNED_OPTION.fullmatch(option) is not None


# ==== Compile and link options ================================================


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

# The link option that drops the engine's unreached code, per platform that needs one of
# its own (engine_link_options), and the compile options that give GNU ld something to drop.
_DEAD_STRIPPING = {"ios": "-Wl,-dead_strip", "linuxbsd": "-Wl,--gc-sections"}
_LINUX_SECTIONS = ("-ffunction-sections", "-fdata-sections")


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
    """
    The deployment target Godot's SCons platform sets, or empty where it sets none.

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


# ==== Swift modules ===========================================================


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


def _included_headers(root: Path, header: str) -> Iterator[str]:
    """Yield the existing headers that a header includes, relative to the source root."""
    for name in re.findall(
        r'^\s*#(?:include|import)\s+"([^"]+)"',
        (root / header).read_text(),
        re.MULTILINE,
    ):
        path = root / name
        if not path.is_file():
            path = root / Path(header).parent / name
        if path.is_file():
            yield relative(path.resolve(), root)


def _header_includes(root: Path, header: str, wanted: str, seen: set[str]) -> bool:
    """Return whether a header, directly or through the headers it includes, is wanted."""
    if header == wanted:
        return True
    if header in seen:
        return False
    seen.add(header)
    return any(
        _header_includes(root, included, wanted, seen)
        for included in _included_headers(root, header)
    )


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


def _including_declaration(
    first: dict[str, Any], second: dict[str, Any], root: Path
) -> dict[str, Any] | None:
    """Return the declaration whose bridging header includes the other's, if one does."""
    for superset, subset in ((first, second), (second, first)):
        if _header_includes(
            root, superset["bridging_header"], subset["bridging_header"], set()
        ):
            return superset
    return None


def merge_swift_module_options(
    first: dict[str, Any] | None, second: dict[str, Any], root: Path
) -> dict[str, Any]:
    """Merge upstream's overlapping driver/platform Swift module declarations."""
    root = root.resolve()
    if first is None or first == second:
        return second
    _check_mergeable(first, second)
    # The iOS bridge imports the shared Apple bridge. Compile the deduplicated
    # source set once with that superset, rather than duplicate Swift classes.
    superset = _including_declaration(first, second, root)
    if superset is None:
        raise ValueError(
            "Upstream Swift bridging headers have no common declared superset"
        )
    generated_header = first["generated_header"] or second["generated_header"]
    return {
        **superset,
        "generated_header": superset["generated_header"] or generated_header,
    }

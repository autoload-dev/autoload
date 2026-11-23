"""
Translate Godot's configure-only SCons graph to rules_cc targets.

SCons is used to evaluate the upstream feature logic, not to execute a compiler,
linker, source generator, or build cache. Compiler actions belong to Bazel.
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
import shutil
import sys
import tempfile
import textwrap
from collections import defaultdict
from collections.abc import (
    Callable,
    Collection,
    Container,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from pathlib import Path
from types import FunctionType
from typing import Any, TypeGuard, cast

try:
    from .module_graph import module_closure, module_dependencies
except ImportError:
    from module_graph import module_closure, module_dependencies


SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".m", ".mm", ".s", ".S", ".swift"}


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


def file_digest(path: Path) -> str:
    """Return the SHA-256 of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_of(value: object) -> str:
    """Return the SHA-256 of a JSON value in canonical form: sorted keys, no spaces."""
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


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


def _module_selection(args: argparse.Namespace) -> dict[str, Any]:
    """The requested modules; the upstream defaults only when requested, so earlier digests hold."""
    selection: dict[str, Any] = {"modules": args.modules}
    if args.default_modules:
        selection["default_modules"] = True
    return selection


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


def is_directory_action(actions: Sequence[Any]) -> bool:
    return (
        len(actions) == 1
        and getattr(getattr(actions[0], "execfunction", None), "__name__", "")
        == "MkdirFunc"
    )


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
    # apple_support defines OS_IOS for Objective-C. Godot uses that identifier
    # for its OS_IOS C++ class and uses IOS_ENABLED as its platform macro.
    return [*options, "-UOS_IOS"] if platform == "ios" else options


def engine_link_options(platform: str, options: list[str]) -> list[str]:
    """Return engine_library's link flags: upstream's, without those Bazel decides."""
    library = [option for option in options if not bazel_owned(option)]
    # The application links every engine object. Dead stripping removes those
    # it never reaches, such as SDL's HID backend, whose PLATFORM_hid_*
    # functions iOS does not build.
    if platform == "ios" and "-Wl,-dead_strip" not in library:
        library.append("-Wl,-dead_strip")
    return library


def target_constraints(args: argparse.Namespace) -> list[str]:
    operating_system = {
        "macos": "macos",
        "linuxbsd": "linux",
        "android": "android",
        "ios": "ios",
    }[args.platform]
    cpus = {
        "arm64": "aarch64",
        "arm32": "arm",
        "x86_32": "x86_32",
        "x86_64": "x86_64",
        "rv64": "riscv64",
    }
    if args.cpu not in cpus:
        raise ValueError(f"No Bazel CPU constraint mapping for SCons arch={args.cpu}")
    result = [
        f"{args.platforms_repository}//os:{operating_system}",
        f"{args.platforms_repository}//cpu:{cpus[args.cpu]}",
    ]
    if args.platform == "ios":
        result.append(f"{args.apple_repository}//constraints:" + args.environment)
    return result


def source_build_facts(args: argparse.Namespace) -> dict[str, str]:
    """Describe the configured source graph independently of a consumer's build request."""
    build_target = args.build_target
    if build_target not in {"editor", "template_debug", "template_release"}:
        raise ValueError(
            f"Unknown build target {build_target}; "
            "expected editor, template_debug or template_release"
        )
    return {
        "canonical_version": args.version,
        "platform": "linux" if args.platform == "linuxbsd" else args.platform,
        "cpu": args.cpu,
        "environment": args.environment,
        "role": "editor" if build_target == "editor" else "runtime",
        "variant": ""
        if build_target == "editor"
        else build_target.removeprefix("template_"),
    }


def write_json(path: Path, value: object, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Upstream builders can depend on ordered SCons Value mappings (for
    # example, module registration). Preserve their insertion order exactly.
    path.write_text(json.dumps(value, indent=indent) + "\n")


def relative(path: object, root: Path) -> str:
    value = Path(str(path).removeprefix("#"))
    if value.is_absolute():
        try:
            return value.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(f"Undeclared path outside engine source: {value}") from error
    if ".." in value.parts:
        raise ValueError(f"Path escapes engine source: {value}")
    return value.as_posix()


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


def _module_function(
    callee: ast.Attribute, namespace: Mapping[str, object], local_names: set[str]
) -> object:
    """Return the function that an attribute of a module in the namespace names."""
    if not isinstance(callee.value, ast.Name) or callee.value.id in local_names:
        return None
    owner = namespace.get(callee.value.id)
    return getattr(owner, callee.attr, None) if inspect.ismodule(owner) else None


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


_SOURCE_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+\.(?:cc|cpp|cxx))"', re.MULTILINE)


_INCLUDED_SOURCE_MARKERS = (b'.cpp"', b'.cc"', b'.cxx"')


def _resolve_source_include(root: Path, path: Path, include: str) -> str | None:
    """Resolve an include beside the including source, else below the source root."""
    for base in (path.parent, root):
        candidate = (base / include).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            return relative(candidate, root)
    return None


def _source_includes(root: Path, path: Path) -> list[str]:
    """Return the C++ sources that a source includes, relative to the source root."""
    text = path.read_bytes() if path.is_file() else b""
    if not any(marker in text for marker in _INCLUDED_SOURCE_MARKERS):
        return []
    includes = _SOURCE_INCLUDE.findall(text.decode(errors="replace"))
    resolved = (_resolve_source_include(root, path, include) for include in includes)
    return [logical for logical in resolved if logical]


def _discovered_includes(
    root: Path, sources: Collection[str], includes: Callable[[Path, Path], list[str]]
) -> set[str]:
    """Return the files the sources include, transitively, relative to the source root."""
    found: set[str] = set()
    pending = list(dict.fromkeys(sources))
    while pending:
        for logical in includes(root, root / pending.pop()):
            if logical not in found:
                found.add(logical)
                pending.append(logical)
    return found


def include_closure(root: Path, sources: Collection[str]) -> set[str]:
    """Godot shader builders recursively read #include files themselves."""
    root = root.resolve()
    return set(sources) | _discovered_includes(root, sources, _shader_includes)


def included_sources(root: Path, sources: Collection[str]) -> list[str]:
    """
    Return the C++ sources that other sources include, relative to the source root.

    Some third-party libraries, such as Embree and Convection Texture Tools, compile one
    source that includes others; those must reach each compile action as textual headers.
    """
    return sorted(_discovered_includes(root.resolve(), sources, _source_includes))


def generated_include_directories(
    sources: Iterable[str],
    generated_headers: Iterable[str],
    generated_sources: Container[str],
) -> list[str]:
    """
    Bazel outputs live apart from sources; preserve includes relative to the source.

    A source finds a generated header beside it or, by a relative path such as
    "editor/script_templates/templates.gen.h", below its own directory.
    """
    ancestors = header_ancestors(generated_headers)
    return sorted(
        {
            str(Path(source).parent)
            for source in sources
            if source in generated_sources or Path(source).parent in ancestors
        }
    )


def header_ancestors(generated_headers: Iterable[str]) -> frozenset[Path]:
    """Every directory that contains a generated header, directly or below it."""
    directories = {Path(header).parent for header in generated_headers}
    return frozenset(
        ancestor
        for directory in directories
        for ancestor in (directory, *directory.parents)
    )


def object_groups(
    groups: Mapping[tuple[str, tuple[str, ...], tuple[str, ...]], Iterable[str]],
    generated_headers: Iterable[str],
    generated_sources: Container[str],
) -> list[tuple[str, tuple[str, ...], tuple[str, ...], list[str]]]:
    """
    Split compile groups so each source sees only its own generated include directories.

    Generated headers of different directories share basenames, such as each platform's
    export/logo_svg.gen.h; a library-wide include path would resolve them to one.
    """
    ancestors = header_ancestors(generated_headers)
    result: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]] = {}
    for (language, copts, includes), sources in sorted(groups.items()):
        for source in sorted(set(sources)):
            parent = Path(source).parent
            directories = (
                [str(parent)]
                if source in generated_sources or parent in ancestors
                else []
            )
            key = (language, copts, tuple(dict.fromkeys([*includes, *directories])))
            result.setdefault(key, []).append(source)
    return [(*key, sources) for key, sources in sorted(result.items())]


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
                {"spec": spec, "dependencies": sorted(dependencies)}
                for spec, dependencies in sorted(
                    self.generators, key=lambda item: item[0]["targets"]
                )
            ],
            "version": self.version,
            "modules": enabled,
            "linkopts": linkopts,
            "minimum_os": minimum_os,
        }


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


# The modules a recipe names when it names none and does not start from Godot's defaults.
_DEFAULT_MODULES = ("gdscript", "text_server_fb")

_TEXT_SERVERS = ("text_server_adv", "text_server_fb")


def requested_modules(modules: str, default_modules: bool) -> list[str]:
    """
    Return the modules a recipe asks for: those it names, or else the ruleset's default.

    A recipe that starts from Godot's defaults takes no default of the ruleset's: those
    already include GDScript and a text server, and a second text server cannot link.
    """
    named = [module for module in modules.split(",") if module]
    return named or ([] if default_modules else list(_DEFAULT_MODULES))


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


def engine_targets(platform: str) -> list[str]:
    """The public targets render() declares for a platform's engine."""
    return (
        ["engine_library", "libgodot_android.so", "godot"]
        if platform == "android"
        else (["engine_library"] if platform == "ios" else ["engine_library", "godot"])
    )


_UNPINNED_REASONS = {
    "missing": "has no pin for",
    "stale": "pins other sources, patches, modules, options or rules_godot code for",
}


def render_unpinned(args: argparse.Namespace, status: str, root: Path) -> None:
    """Write a BUILD file whose engine targets fail with the repin command."""
    message = args.unpinned_message.format(reason=_UNPINNED_REASONS[status])
    lines = [
        f'load("{args.pin_bzl}", "godot_unpinned_recipe")',
        'package(default_visibility = ["//visibility:public"])',
        *(
            f"godot_unpinned_recipe(name = {name!r}, message = {message!r})"
            for name in engine_targets(args.platform)
        ),
    ]
    (root / "BUILD.bazel").write_text("\n".join(lines) + "\n")


def _header_rules(args: argparse.Namespace, uses_swift: bool) -> list[str]:
    """Return the loads, package defaults and revision target that open the BUILD file."""
    lines = [
        "# Generated from Godot SCons; do not edit.",
        f'load("{args.cc_repository}//cc:cc_library.bzl", "cc_library")',
        f'load("{args.cc_repository}//cc:cc_binary.bzl", "cc_binary")',
        f'load("{args.cc_repository}//cc:objc_library.bzl", "objc_library")',
    ]
    if uses_swift:
        lines.append(
            f'load("{args.swift_repository}//swift:swift_library.bzl", "swift_library")'
        )
    lines += [
        f'load("{args.generator_bzl}", "godot_source_generator", "godot_source_library", "godot_source_binary", "godot_source_revision")',
        'package(default_visibility = ["//visibility:public"])',
        'exports_files(["engine_manifest.json"])',
        f"godot_source_revision(name = 'revision', visibility = ['//visibility:private'], build_name = {args.build_name!r}, inputs_hash = {args.inputs_hash!r}, build = '_revision/build.txt', hash = '_revision/hash.txt', timestamp = '_revision/timestamp.txt')",
    ]
    return lines


def _generator_rules(
    root: Path, generators: Sequence[tuple[dict[str, Any], set[str]]]
) -> tuple[list[str], list[str]]:
    """
    Write each generator's specification and return its rules and its generated headers.

    A generator's inputs are its dependencies and the Python files of the source tree.
    """
    python_files = sorted(
        relative(path, root)
        for path in root.rglob("*.py")
        if "_scons" not in path.parts and "_bazel_generators" not in path.parts
    )
    lines: list[str] = []
    generated_headers: list[str] = []
    for index, (spec, dependencies) in enumerate(generators):
        name = f"_generate_{index:04d}"
        manifest = f"_bazel_generators/{name}.json"
        write_json(root / manifest, spec)
        inputs = {source: source for source in sorted(dependencies | set(python_files))}
        # A script's SCsub is needed for inspection provenance, but its captured
        # function is executed alone by tools/engine/generator.py.
        inputs[spec["code_file"]] = spec["code_file"]
        attributes = {
            "name": name,
            "spec": manifest,
            "inputs": inputs,
            "outs": spec["targets"],
        }
        lines.append(_multiline_rule("godot_source_generator", attributes))
        generated_headers.extend(
            name for name in spec["targets"] if Path(name).suffix not in SOURCE_SUFFIXES
        )
    return lines, generated_headers


def _headers_rule(generated_headers: Iterable[str], included: Iterable[str]) -> str:
    # Editor sources also include XPM images, such as editor/import/atlas_import_failed.xpm,
    # and glslang includes SPIR-V's C++11 header spirv.hpp11, which hdrs does not accept.
    return (
        'cc_library(\n    name = "_headers",\n    visibility = ["//visibility:private"],\n    hdrs = glob(["**/*.h", "**/*.hh", "**/*.hpp", "**/*.hxx"], exclude = ["_scons/**"], allow_empty = True) + '
        f"{list(generated_headers)!r},\n"
        '    textual_hdrs = glob(["**/*.inc", "**/*.inl", "**/*.c", "**/*.xpm", "**/*.hpp11"], exclude = ["_scons/**"], allow_empty = True) + '
        f"{list(included)!r},\n"
        '    includes = ["."],\n)'
    )


def _multiline_rule(rule: str, attributes: Mapping[str, object]) -> str:
    return (
        rule
        + "(\n"
        + "".join(f"    {key} = {value!r},\n" for key, value in attributes.items())
        + ")"
    )


def _object_rules(
    groups: Mapping[tuple[str, tuple[str, ...], tuple[str, ...]], Iterable[str]],
    generators: Sequence[tuple[dict[str, Any], set[str]]],
    generated_headers: Iterable[str],
) -> tuple[list[str], list[str]]:
    """Return the library rule of each object group and the labels of those libraries."""
    generated_sources = {
        name
        for spec, _inputs in generators
        for name in spec["targets"]
        if Path(name).suffix in SOURCE_SUFFIXES
    }
    lines: list[str] = []
    labels: list[str] = []
    for index, (language, copts, includes, sources) in enumerate(
        object_groups(groups, generated_headers, generated_sources)
    ):
        name = f"_objects_{index:04d}"
        labels.append(":" + name)
        attributes: dict[str, object] = {
            "name": name,
            "visibility": ["//visibility:private"],
            "srcs": sources,
            "copts": list(copts),
            "includes": list(includes),
            "deps": [":_headers"],
            "alwayslink": True,
        }
        lines.append(
            _multiline_rule(
                "objc_library" if language == "objc" else "cc_library", attributes
            )
        )
    return lines, labels


def _swift_rule(
    swift_sources: Iterable[str], swift_options: dict[str, Any] | None
) -> str:
    options = swift_options or {
        "module_name": "godot_swift_module",
        "bridging_header": "drivers/apple_embedded/bridging_header_apple_embedded.h",
        "generated_header": None,
        "copts": ["-swift-version", "6", "-cxx-interoperability-mode=default"],
    }
    attributes: dict[str, object] = {
        "name": "_swift",
        "visibility": ["//visibility:private"],
        "srcs": sorted(set(swift_sources)),
        "module_name": options["module_name"],
        "copts": options["copts"]
        + ["-import-objc-header", f"$(location {options['bridging_header']})"],
        "swiftc_inputs": [options["bridging_header"]],
        "deps": [":_headers"],
        "generates_header": bool(options["generated_header"]),
        "alwayslink": True,
    }
    if options["generated_header"]:
        attributes["generated_header_name"] = Path(options["generated_header"]).name
    return _multiline_rule("swift_library", attributes)


# Upstream's combined static archive cannot carry application framework dependencies;
# the iOS engine library represents them with Bazel's built-in Objective-C providers.
_IOS_FRAMEWORKS = [
    "ARKit",
    "AVFoundation",
    "AudioToolbox",
    "CoreAudio",
    "CoreGraphics",
    "CoreHaptics",
    "CoreMedia",
    "CoreMotion",
    "CoreText",
    "CoreVideo",
    "Foundation",
    "GameController",
    "Metal",
    "OpenGLES",
    "QuartzCore",
    "Security",
    "SystemConfiguration",
    "UIKit",
    "UniformTypeIdentifiers",
]


def _source_rule(
    args: argparse.Namespace, graph: Mapping[str, Any], name: str, library: str
) -> str:
    """Return the rule that publishes a built library with the engine's provenance."""
    facts = source_build_facts(args)
    metadata_arguments = ", ".join(f"{key} = {value!r}" for key, value in facts.items())
    digest = "sha256:" + args.source_sha256 if args.source_sha256 else ""
    rule = (
        "godot_source_library"
        if args.platform in {"android", "ios"}
        else "godot_source_binary"
    )
    return f"{rule}(name = {name!r}, deps = [{library!r}], version = {graph['version']!r}, build = '_revision/build.txt', hash = '_revision/hash.txt', digest = {digest!r}, customizations = {args.customizations!r}, minimum_os = {graph['minimum_os']!r}, {metadata_arguments})"


def _engine_rules(
    args: argparse.Namespace, graph: Mapping[str, Any], dependencies: list[str]
) -> list[str]:
    """Return the rules of the platform's engine targets."""
    # Android's libgodot is a shared library. iOS consumers link engine_library
    # through rules_apple; cc_binary is the desktop executable/editor.
    compatibility = target_constraints(args)
    linkopts = graph["linkopts"]
    if args.platform == "ios":
        return [
            f"objc_library(name = '_engine_library', visibility = ['//visibility:private'], deps = {dependencies!r}, linkopts = {linkopts!r}, sdk_frameworks = {_IOS_FRAMEWORKS!r}, sdk_dylibs = ['c++', 'z', 'iconv'], target_compatible_with = {compatibility!r})",
            _source_rule(args, graph, "engine_library", ":_engine_library"),
        ]
    library = f"cc_library(name = 'engine_library', deps = {dependencies!r}, linkopts = {linkopts!r}, target_compatible_with = {compatibility!r})"
    if args.platform == "android":
        return [
            library,
            f"cc_binary(name = 'libgodot_android.so', deps = [':engine_library'], linkstatic = True, linkshared = True, target_compatible_with = {compatibility!r})",
            _source_rule(args, graph, "godot", ":libgodot_android.so"),
        ]
    return [
        library,
        f"cc_binary(name = '_godot', visibility = ['//visibility:private'], deps = [':engine_library'], linkstatic = True, target_compatible_with = {compatibility!r})",
        _source_rule(args, graph, "godot", ":_godot"),
    ]


def _manifest(
    args: argparse.Namespace,
    graph: Mapping[str, Any],
    groups: Mapping[tuple[str, tuple[str, ...], tuple[str, ...]], Collection[str]],
) -> dict[str, Any]:
    swift_sources = graph["swift_sources"]
    return {
        "schema_version": 1,
        "version": args.version,
        "platform": args.platform,
        "cpu": args.cpu,
        "build_target": args.build_target,
        "requested_modules": args.modules,
        "selected_modules": graph["modules"],
        "object_actions": sum(len(set(sources)) for sources in groups.values())
        + len(set(swift_sources)),
        "swift_sources": sorted(set(swift_sources)),
        "compile_groups": len(groups),
        "generator_actions": len(graph["generators"]),
        "scons_options": args.options,
        "minimum_os": graph["minimum_os"],
    }


def render(args: argparse.Namespace, graph: Mapping[str, Any], root: Path) -> None:
    """Write the BUILD file, generator specifications and manifest of a configured graph."""
    groups = {
        (language, tuple(copts), tuple(includes)): sources
        for language, copts, includes, sources in graph["groups"]
    }
    generators = [
        (generator["spec"], set(generator["dependencies"]))
        for generator in graph["generators"]
    ]
    lines = _header_rules(args, bool(graph["swift_sources"]))
    generator_rules, generated_headers = _generator_rules(root, generators)
    lines += generator_rules
    compiled = [source for _key, sources in groups.items() for source in sources]
    lines.append(_headers_rule(generated_headers, included_sources(root, compiled)))
    object_rules, dependencies = _object_rules(groups, generators, generated_headers)
    lines += object_rules
    if graph["swift_sources"]:
        lines.append(_swift_rule(graph["swift_sources"], graph["swift_options"]))
        dependencies.append(":_swift")
    lines += _engine_rules(args, graph, dependencies)
    (root / "BUILD.bazel").write_text("\n\n".join(lines) + "\n")
    # This file is the successful-capture marker checked after SCons exits.
    write_json(root / "engine_manifest.json", _manifest(args, graph, groups))


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
    # Raw file paths would be undeclared inputs; use patches or build_options instead.
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
                f"Option {option} follows Bazel's flags: use {BAZEL_OPTIONS[key]}"
            )
        if _is_controlled_option(key, bool(separator)):
            raise ValueError(f"Option is controlled by rules_godot: {option}")


def require_expected_version(actual: str, expected: str) -> None:
    """Reject sources whose version.py contradicts their descriptor."""
    if expected and actual != expected:
        raise ValueError(
            f"The source descriptor declares Godot {expected}, "
            f"but the extracted version.py is {actual}"
        )


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
    return requested


def _is_module_name(name: str) -> bool:
    return name.replace("_", "").isalnum() and not name[0].isdigit()


def prepare_custom_modules(root: Path, declarations: Iterable[str]) -> list[str]:
    """
    Copy each `name=directory` custom module below _custom_modules and return the names.

    The copy leaves out Bazel's BUILD files, so the module is no package of its own in
    the recipe repository, and Python caches.
    """
    names = []
    for declaration in declarations:
        name, separator, directory = declaration.partition("=")
        if not separator or not _is_module_name(name):
            raise ValueError(f"Invalid custom module declaration: {declaration}")
        destination = root / "_custom_modules" / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            directory,
            destination,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "BUILD", "BUILD.bazel"),
        )
        names.append(name)
    return names


# The files whose behavior a pinned graph depends on: the capture and its translation.
_PIN_TOOLS = (Path(__file__).resolve(), Path(inspect.getfile(module_closure)).resolve())

# The version of a recipe pin's layout.
PIN_FORMAT = 1


# Custom module files whose contents can change the configured graph: Godot's build scripts
# and the shader sources whose includes a generator follows. Other files count by path.
_GRAPH_FILE_SUFFIXES = {".py", ".glsl", ".glslinc"}


def shapes_graph(path: Path) -> bool:
    """
    Whether a custom module file's contents can change the configured graph.

    SCsub and config.py decide which files compile and how, so their contents count, as do
    those of shader sources; a source or header counts only by its path, so editing a
    module's code keeps its pin.
    """
    return path.name == "SCsub" or path.suffix in _GRAPH_FILE_SUFFIXES


def pin_digest(args: argparse.Namespace, scons: Path) -> str:
    """
    Return the digest a recipe's pin records: what its configured graph depends on.

    It covers the archive digest, the patches, the custom modules' structure, the
    recipe's platform, CPU, build target, modules and options, its build name, and the
    SCons release and rules_godot code that capture the graph. Host state is no input: a
    pin is valid on every host.
    """
    tools = [file_digest(path) for path in [*_PIN_TOOLS, scons / "SCons" / "__init__.py"]]
    return "sha256:" + digest_of(
        {
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
    )


def pinned_graph(
    lock: Path, recipe: str, digest: str
) -> tuple[str, dict[str, Any] | None]:
    """Return a recipe's status in a lock file, missing, stale or pinned, and its graph."""
    text = lock.read_text().strip() if lock.is_file() else ""
    pins = json.loads(text) if text else {}
    entry = pins.get("recipes", {}).get(recipe)
    if entry is None:
        return "missing", None
    if entry.get("digest") != digest:
        return "stale", None
    graph = dict(entry["graph"])
    # The lock stores generator lists that recipes share once, by digest.
    graph["generators"] = pins["generators"][graph["generators"]]
    return "pinned", graph


# Stand-ins for the host tools Godot's Linux detect.py probes. Every package query fails, so a
# configuration reads none of the host's packages, which compile actions would not declare:
# Godot's bundled libraries and dynamically loaded system libraries only. Without
# wayland-scanner, whose generators are shell commands, Godot builds without Wayland.
_LINUX_PROBES = {
    "pkg-config": '#!/bin/sh\nif [ "$1" = "--version" ]; then echo 0.29.2; exit 0; fi\nexit 1\n',
    "wayland-scanner": "#!/bin/sh\nexit 1\n",
}


def load_detect(root: Path, platform: str) -> Any:
    """Load a platform's detect.py; the source root must be on sys.path for its imports."""
    path = root / "platform" / platform / "detect.py"
    spec = importlib.util.spec_from_file_location("_godot_detect", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    detect = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detect)
    return detect


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


def write_pin(path: Path, digest: str, graph: Mapping[str, Any]) -> None:
    """Write one recipe's pin, the entry a lock file holds for it."""
    write_json(path, {"digest": digest, "graph": graph})


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
    parser.add_argument("--custom-modules", action="append", default=[])
    parser.add_argument("--custom-module-source", action="append", default=[])
    # A custom module already below _custom_modules, as in a pin action's source tree.
    parser.add_argument("--custom-module-name", action="append", default=[])
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
    """Copy the custom modules into the source tree and name them in the arguments."""
    args.custom_module_names = [
        *prepare_custom_modules(root, args.custom_module_source),
        *args.custom_module_name,
    ]
    args.custom_modules_root = (
        root / "_custom_modules" if args.custom_module_names else None
    )
    if args.custom_module_names:
        args.custom_modules.append("_custom_modules")


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


def _complete_arguments(args: argparse.Namespace, root: Path) -> None:
    """Validate the recipe and add what it derives from the source: version, modules, hash."""
    args.version = source_version(root)
    require_expected_version(args.version, args.expected_version)
    (root / "engine_manifest.json").unlink(missing_ok=True)
    _add_custom_modules(args, root)
    graph = module_dependencies(root, [root / path for path in args.custom_modules])
    args.selected_modules = module_closure(
        args.modules, graph, editor=args.build_target == "editor"
    )
    # Before SCons for the modules a recipe names; Godot's defaults are checked after it.
    require_one_text_server(args.selected_modules)
    check_options(args.options)
    args.customizations = customizations(args)
    _add_environment_option(args)
    args.inputs_hash = inputs_hash(args)


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

    executors: list[Any] = []
    original = SCons.Executor.Executor.__init__

    def record(executor: Any, *values: Any, **kwargs: Any) -> None:
        original(executor, *values, **kwargs)
        executors.append(executor)

    def finish(*_args: Any) -> None:
        captured = collect(args, executors)
        if args.pin_output:
            write_pin(args.pin_output, digest, captured)
        else:
            render(args, captured, root)

    SCons.Executor.Executor.__init__ = record
    SCons.Script.Main._build_targets = finish
    return SCons.Script.Main.main


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
        status, pinned = pinned_graph(args.lock, args.recipe, digest)
        if pinned is None:
            render_unpinned(args, status, root)
        else:
            render(args, pinned, root)
        return
    if args.pin_output:
        args.pin_output = args.pin_output.resolve()
    scons_main = _install_capture(args, root, scons, digest)
    os.chdir(root)
    sys.path.insert(0, str(root))
    _configure(args, root, scons_main)


if __name__ == "__main__":
    main()

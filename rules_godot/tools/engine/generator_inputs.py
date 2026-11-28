"""
Read what a source generator of Godot's SCons build depends on besides its sources.

The capture records the environment values that a generator's code reads, the SCons Value
payloads it receives and the shader files its sources include. It finds the environment
reads in the generator's code without running it. Since it records only those values, a
changed value reruns only the generators that read it. Code that uses the environment in a
way the reading cannot follow fails.

Sections: Environment reads, Values and includes.
"""

import ast
import inspect
import re
import textwrap
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from types import FunctionType
from typing import Any, TypeGuard

from tools.engine.source_tree import relative

_SCALAR_TYPES = (str, bool, int, float)


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, _SCALAR_TYPES)


# ==== Environment reads =======================================================


_ALLOWED_ENV_METHODS = ("get", "NoCache", "Detect")


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


# ==== Values and includes =====================================================


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

"""Validate Bazel's evaluated API schema, including aliases and inherited attributes."""

import ast
from typing import Any

from google.protobuf import text_format
from stardoc.proto import stardoc_output_pb2

from tools.docs.output_contracts import Api, Contract, parse, provider_identity

# Stardoc's generated ModuleInfo message; its protobuf types are not visible to
# the type checker.
ModuleInfo = Any

# Stardoc API kinds and their name fields; other symbols use `name` and `doc`.
CATEGORIES = {
    "rule_info": "rule_name",
    "repository_rule_info": "rule_name",
    "macro_info": "macro_name",
    "aspect_info": "aspect_name",
    "provider_info": "provider_name",
    "func_info": "function_name",
    "module_extension_info": "extension_name",
}


def parse_module(text: str) -> ModuleInfo:
    """Parse the evaluated extractor's text output with Stardoc's own schema."""
    return text_format.Parse(text, stardoc_output_pb2.ModuleInfo())


def exported_names(source: str) -> set[str]:
    """Read names from Python-compatible Starlark syntax without executing it."""
    names: set[str] = set()

    def add(target: ast.expr) -> None:
        if isinstance(target, ast.Name) and target.id[0].isalpha():
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                add(item)

    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name[0].isalpha():
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                add(target)
    return names


def documentation_errors(module: ModuleInfo, source: str) -> list[str]:
    """Return missing descriptions or exported names, with actionable locations."""
    errors: list[str] = []
    documented: set[str] = set()

    def require(value: str, location: str) -> None:
        if not value.strip():
            errors.append(f"{location}: missing documentation")

    def attributes(items: Any, owner: str) -> None:
        # Bazel documents its own common attributes; the reference links there.
        for item in items:
            if not item.natively_defined:
                require(item.doc_string, f"{owner}.{item.name}")

    require(module.module_docstring, "module")
    for category, name_field in CATEGORIES.items():
        for item in getattr(module, category):
            name = getattr(item, name_field)
            documented.add(name)
            require(item.doc_string, name)
            if hasattr(item, "attribute"):
                attributes(item.attribute, name)
            if category == "provider_info":
                for field in item.field_info:
                    require(field.doc_string, f"{name}.{field.name}")
                if item.HasField("init"):
                    for param in item.init.parameter:
                        require(param.doc_string, f"{name}.init({param.name})")
            if category == "func_info":
                for param in item.parameter:
                    require(param.doc_string, f"{name}({param.name})")
            if category == "module_extension_info":
                for tag in item.tag_class:
                    require(tag.doc_string, f"{name}.{tag.tag_name}")
                    attributes(tag.attribute, f"{name}.{tag.tag_name}")
    for item in module.starlark_other_symbol_info:
        documented.add(item.name)
        require(item.doc, item.name)
    for name in sorted(exported_names(source)):
        if not any(
            entity == name or entity.startswith(name + ".") for entity in documented
        ):
            errors.append(
                f"{name}: exported symbol missing from extracted reference; add its supported documentation (constants use #: comments)"
            )
    return errors


def module_apis(module: ModuleInfo) -> tuple[dict[str, Api], list[str]]:
    """Parse each export's output contract once; providers produce no outputs."""
    errors = [
        f"{item.name}: unsupported evaluated API kind starlark_other_symbol_info; add explicit output classification and evidence"
        for item in module.starlark_other_symbol_info
    ]
    apis = {}
    for category, name_field in CATEGORIES.items():
        for item in getattr(module, category):
            name = getattr(item, name_field)
            origin = getattr(item, "origin_key", None)
            identity = (
                provider_identity(origin.file + "%" + origin.name)
                if origin and origin.file
                else ""
            )
            try:
                contract = (
                    Contract() if category == "provider_info" else parse(item.doc_string)
                )
            except ValueError as error:
                errors.append(f"{name}: {error}")
                continue
            apis[name] = Api(category, contract, identity)
    return apis, errors

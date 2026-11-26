"""
The API contract tests: each compares the documented contracts with Bazel's facts of the
cases that one kind of host can analyze.

A test reads three kinds of evidence, all of them declared inputs: the extracted
documentation of the public entrypoints, the loading facts of the fixtures from a genquery
and their configured facts from `contract_evidence`, one target per configuration. The
checks themselves are the repository root module's (tools/docs/contracts.py).
"""

load("@bazel_skylib//lib:collections.bzl", "collections")
load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_python//python:defs.bzl", "py_test")
load("//godot/tests/api:rules.bzl", "DOCS", "reference_name")
load(":evidence.bzl", "contract_evidence")

# What a case's host may need, by the value of its `requires`; each is a test of its own.
REQUIREMENTS = {
    # No more than the ruleset's development setup.
    "": {},
    # The Android SDK and NDK, which rules_android finds through ANDROID_HOME.
    "android_sdk": {
        "target_compatible_with": ["//godot/platforms/private/tests:requires_android_sdk"],
    },
    # Xcode, which Apple platforms need for analysis.
    "macos": {"target_compatible_with": ["@platforms//os:macos"]},
}

def _with_defaults(case):
    """A case or library with the fields it leaves out."""
    return {"companions": [], "conditions": [], "requires": "", "settings": {}} | case

def _companion_labels(case):
    package, _, root = case["target"].rpartition(":")
    return [package + ":" + pattern.replace("{name}", root, 1) for pattern in case["companions"]]

def _labels(case):
    """The fixture labels a case analyzes, its root first."""
    if "entrypoints" in case:
        return [label for labels in case["entrypoints"].values() for label in labels]
    return [case["target"]] + _companion_labels(case)

def _canonical(labels):
    """The canonical form of the labels, which genquery reports, by their apparent form."""
    return {label: str(Label(label)) for label in labels}

def _flattened(groups):
    """The labels of all groups, each once, in order."""
    return list(collections.uniq([label for labels in groups for label in labels]))

def _queries(name, loaded, tests, common):
    """Declare the genqueries of the loading facts and behavior tests, by their test flag."""
    native.genquery(
        name = name + ".loading",
        expression = "siblings(set(%s))" % " ".join(loaded),
        opts = ["--output=xml", "--xml:default_values"],
        scope = loaded,
        **common
    )
    if not tests:
        return {"--loading": ":%s.loading" % name}
    native.genquery(
        name = name + ".behavior",
        expression = "tests(set(%s))" % " ".join(tests),
        scope = tests,
        **common
    )
    return {"--loading": ":%s.loading" % name, "--behavior": ":%s.behavior" % name}

def _requiring(cases, requires):
    """The cases or libraries that need one kind of host, with their defaults, by key."""
    cases = {key: _with_defaults(case) for key, case in cases.items()}
    return {key: case for key, case in cases.items() if case["requires"] == requires}

def _configurations(cases, libraries, public_targets):
    """The labels to analyze, by the JSON of the settings of their configuration."""
    configurations = {}
    for case in cases.values():
        configurations.setdefault(json.encode(case["settings"]), []).extend(_labels(case))
    for label, library in libraries.items():
        configurations.setdefault(json.encode(library["settings"]), []).append(label)
    if public_targets:
        configurations.setdefault(json.encode({}), []).extend(public_targets)
    return configurations

def _evidence(name, configurations, common):
    """Declare one contract_evidence per configuration; return their labels."""
    evidence = []
    for index, (settings, labels) in enumerate(sorted(configurations.items())):
        labels = list(collections.uniq(labels))
        evidence.append(":%s.evidence_%d" % (name, index))
        contract_evidence(
            name = "%s.evidence_%d" % (name, index),
            labels = labels,
            settings = json.decode(settings),
            targets = labels,
            **common
        )
    return evidence

def extracted_inventories(modules):
    """
    The complete extractions of public entrypoints, as //godot/tests/api declares them.

    Args:
        modules: Labels of public entrypoints, such as `//godot:defs.bzl`.

    Returns:
        Their `_inventory.textproto` labels.
    """
    return ["//godot/tests/api:%s_inventory.textproto" % reference_name(module) for module in modules]

def api_contract_test(
        name,
        requires,
        cases,
        libraries = {},
        extracted = None,
        public_targets = [],
        manifest = None,
        behavior = {},
        main = DOCS + "contracts.py",
        **kwargs):
    """
    Check the cases and libraries that need one kind of host against their documentation.

    Declares `name`, a py_test; `<name>.loading`, the genquery of the fixtures' loading
    facts; `<name>.behavior`, that of the behavior tests; `<name>.evidence_<n>`, the
    configured facts per configuration; and `<name>.plan`, the cases as the test reads them.

    Args:
        name: Name of the test.
        requires: The key of REQUIREMENTS the cases share.
        cases: The cases by key, as API_CASES writes them; the test checks those that
            require `requires`.
        libraries: The public libraries by label, as PUBLIC_LIBRARIES writes them; the test
            checks those that require `requires`.
        extracted: The starlark_doc_extract textproto targets of the APIs to check; by
            default the public entrypoints the selected cases name.
        public_targets: Public configuration targets to check, by label.
        manifest: A JSON file with every case, behavior test and library, for the coverage
            of the whole registry; one test of the requirement-free cases checks it.
        behavior: The behavior tests by API, whose resolution this test checks.
        main: The test's Python entrypoint.
        **kwargs: Further attributes of the test.
    """
    cases = _requiring(cases, requires)
    libraries = _requiring(libraries, requires)
    configurations = _configurations(cases, libraries, public_targets)

    # The test's helper targets need what its host needs too: `//...` builds them anyway.
    common = {
        "target_compatible_with": REQUIREMENTS[requires].get("target_compatible_with", []),
        "testonly": True,
    }
    evidence = _evidence(name, configurations, common)
    loaded = _flattened(configurations.values())
    tests = _flattened(behavior.values())
    write_file(
        name = name + ".plan",
        out = name + ".plan.json",
        content = [json.encode_indent({
            "behavior": behavior,
            "canonical": _canonical(loaded + tests),
            "cases": cases,
            "libraries": libraries,
            "public_targets": public_targets,
        })],
        **common
    )
    inputs = _queries(name, loaded, tests, common) | {"--plan": ":%s.plan" % name}
    if manifest:
        inputs["--manifest"] = manifest
    if extracted == None:
        extracted = extracted_inventories(collections.uniq([key.partition("%")[0] for key in cases]))
    arguments = inputs.items() + [("--evidence", target) for target in evidence] + [
        ("--extracted", target)
        for target in extracted
    ]
    py_test(
        name = name,
        size = "small",
        srcs = [main],
        main = main,
        args = ["%s=$(rootpath %s)" % argument for argument in arguments],
        data = [target for _, target in arguments],
        deps = [DOCS + "contracts_lib"],
        # It reads what analysis reports of its fixtures and builds none of them, so it
        # starts no Godot process (RG026).
        tags = ["analysis_only"],
        **(REQUIREMENTS[requires] | kwargs)
    )

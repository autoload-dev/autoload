"""Decoding of the declared loading and configured evidence."""

import json
import unittest

from tools.conventions.context import EvidenceError
from tools.docs.evidence import (
    Evidence,
    Labels,
    decode_configured,
    decode_loading,
    invocation,
)

APP = {
    "label": "//:app",
    "files": 1,
    "runfiles": 2,
    "executable": True,
    "providers": ["CcInfo"],
    "groups": ["bundle"],
}

LABELS = Labels(
    {"@godot//toolchains:editor": "@@+godot_engines+godot//toolchains:editor"}
)

LOADING = """<?xml version="1.1" encoding="UTF-8" standalone="no"?>
<query version="2">
    <rule class="app" location="pkg/BUILD.bazel:3:4" name="//pkg:app">
        <string name="generator_location" value="pkg/BUILD.bazel:3:4"/>
        <boolean name="testonly" value="true"/>
        <list name="visibility"><label value="//visibility:public"/></list>
    </rule>
    <rule class="alias" location="pkg/BUILD.bazel:3:4" name="//pkg:app.debug_symbols">
        <string name="generator_location" value="pkg/BUILD.bazel:3:4"/>
    </rule>
    <rule class="pack" location="pkg/BUILD.bazel:9:4" name="//pkg:pack"/>
    <rule class="toolchain" location="/output/external/x/BUILD.bazel:1:1"
        name="@@+godot_engines+godot//toolchains:editor.toolchain">
        <label name="toolchain" value="@@+godot_engines+godot//toolchains:editor"/>
        <list name="visibility">
            <label value="@@+godot_engines+godot//toolchains:__pkg__"/>
        </list>
    </rule>
    <source-file location="x" name="@@+godot_engines+godot//:LICENSE.md">
        <visibility-label name="//visibility:public"/>
    </source-file>
    <source-file location="x" name="//pkg:BUILD.bazel">
        <visibility-label name="//visibility:private"/>
    </source-file>
</query>
"""


def configuration(settings: dict[str, str], *facts: dict) -> str:
    return json.dumps({"settings": settings, "facts": list(facts)})


class EvidenceTest(unittest.TestCase):
    def test_decodes_counts_and_names_by_authored_label(self) -> None:
        decoded = decode_configured(configuration({}, APP))
        target = decoded.targets["//:app"]
        self.assertEqual((1, 2, True), (target.files, target.runfiles, target.executable))
        self.assertEqual(frozenset({"bundle"}), target.groups)
        with self.assertRaisesRegex(EvidenceError, "invalid evaluated configured"):
            decode_configured(configuration({}, {"label": "//:app"}))

    def test_configured_facts_are_those_of_the_case_s_settings(self) -> None:
        android = {"//command_line_option:platforms": "//godot/platforms:android_arm64"}
        other = dict(APP, files=3)
        evidence = Evidence(
            decode_loading(LOADING, LABELS),
            (
                decode_configured(configuration({}, APP)),
                decode_configured(configuration(android, other)),
            ),
        )
        self.assertEqual(1, evidence.configured({}, ["//:app"])["//:app"].files)
        self.assertEqual(3, evidence.configured(android, ["//:app"])["//:app"].files)
        with self.assertRaisesRegex(EvidenceError, "no configured evidence for //:x"):
            evidence.configured({}, ["//:x"])
        with self.assertRaisesRegex(EvidenceError, "no configured evidence for settings"):
            evidence.configured({"//godot:variant": "editor"}, ["//:app"])

    def test_loading_facts_name_repositories_as_the_cases_do(self) -> None:
        loading = decode_loading(LOADING, LABELS)
        toolchain = loading.rules["@godot//toolchains:editor.toolchain"]
        self.assertEqual("@godot//toolchains:editor", toolchain.labels["toolchain"])
        self.assertEqual(
            ("@godot//toolchains:__pkg__",), toolchain.label_lists["visibility"]
        )
        self.assertEqual(frozenset({"@godot//:LICENSE.md"}), loading.sources)
        self.assertTrue(loading.rules["//pkg:app"].booleans["testonly"])

    def test_an_invocation_is_the_rules_of_its_root_s_authored_call(self) -> None:
        loading = decode_loading(LOADING, LABELS)
        self.assertEqual(
            ["//pkg:app", "//pkg:app.debug_symbols"],
            [target.label for target in invocation("//pkg:app", loading.rules.values())],
        )
        with self.assertRaisesRegex(EvidenceError, "unresolved evaluated invocation"):
            invocation("//pkg:missing", loading.rules.values())


if __name__ == "__main__":
    unittest.main()

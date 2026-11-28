"""An adapter_test whose adapter is the fake adapter of fixtures/fake_adapter."""

load("//godot/testing:adapter.bzl", "adapter_test")

visibility([
    "//godot/private/tests/strict_warnings",
    "//godot/testing/tests/adapter",
])

def _fake_adapter_test_impl(name, visibility, cases, **kwargs):
    adapter_test(
        name = name,
        visibility = visibility,
        deps = cases,
        adapter = Label("//godot/testing/tests/adapter/fixtures/fake_adapter:run.gd"),
        main = "addons/fake_adapter/run.gd",
        cases = "addons/fake_adapter/cases.txt",
        **kwargs
    )

fake_adapter_test = macro(
    doc = "Declare an adapter_test of the fake adapter over cases.",
    implementation = _fake_adapter_test_impl,
    inherit_attrs = adapter_test,
    attrs = {
        "deps": None,
        "adapter": None,
        "main": None,
        "cases": attr.label_list(
            doc = "godot_resources targets whose own files the adapter lists.",
            mandatory = True,
        ),
    },
)

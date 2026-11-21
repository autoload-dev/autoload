"""A consumer-owned module extension: one macOS source build through godot_engine_source_build."""

load("@autoload_rules_godot//godot/engine/private:repositories.bzl", "godot_engine_source_build")

def _impl(module_ctx):
    godot_engine_source_build(
        name = "godot_source_build_fixture",
        source = Label("@godot_sources//:source.json"),
        platforms = ["macos"],
        cpus = ["arm64"],
        build_targets = ["editor", "template_release"],
        # One policy for every row: template-only options such as disable_3d would fail
        # the editor recipe, so they belong in a separate source build.
        build_options = {
            "vulkan": "no",
            "metal": "no",
            "opengl3": "no",
        },
    )
    return module_ctx.extension_metadata(reproducible = True)

source_build_fixture = module_extension(
    doc = "Declare the fixture source build during repository declaration.",
    implementation = _impl,
)

"""Small acquired datasets exercise real repository generators without native compilation."""

load("//godot/engine/private:archives.bzl", "godot_export_templates_archive")

def _fixtures_impl(ctx):
    archive = ctx.path(Label(":split_templates.zip"))
    godot_export_templates_archive(
        name = "godot_split_templates",
        urls = ["file://" + str(archive)],
        integrity = "sha256-kfwGFsjCwq4s8Og4Cj91SmF79iQwxKPaknknuekHtnA=",
        platform = "macos",
        cpus = ["arm64", "x86_64"],
        version = "4.7.2",
    )
    return ctx.extension_metadata(reproducible = True)

repository_fixtures = module_extension(implementation = _fixtures_impl)

"""
PROTOTYPE(web): the web application backend of godot_app.

Packages the pack's PCK with the runtime's web template, a ZIP of Godot's
godot.html/.js/.wasm and audio worklets, into a directory a static HTTP server serves,
and a deterministic ZIP of it. Extension libraries, threads, the PWA files and the
rendered icons and splash are open decisions; see docs/internal/web-prototype.md.
"""

load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:providers.bzl", "GodotRuntimeInfo")
load(":launch.bzl", "LAUNCH_ATTRS", "launcher")

visibility(["//godot", "//godot/platforms", "//godot/platforms/private/tests"])

def _web_application_impl(ctx):
    if ctx.attr.platform_deps or ctx.attr.platform_resources:
        fail("godot_app web does not support platform_deps or platform_resources")
    runtime = ctx.attr.runtime[GodotRuntimeInfo]
    if runtime.platform != "web":
        fail("%s runtime cannot package a web app" % runtime.platform)
    pack = ctx.attr.pack[GodotPackInfo]
    if pack.project.runtime_extensions:
        # PROTOTYPE(web): GDExtensions need the dlink templates and side modules built
        # with Emscripten; see the prototype notes.
        fail("godot_app web does not package extension libraries yet: %s" % [
            extension.descriptor_path
            for extension in pack.project.runtime_extensions
        ])
    name = ctx.attr.app_name or ctx.label.name
    site = ctx.actions.declare_directory(ctx.label.name + "/" + name + ".web")
    archive = ctx.actions.declare_file(ctx.label.name + "/" + name + ".zip")
    args = ctx.actions.args()
    args.add("--template", runtime.executable)
    args.add("--pack", pack.pack_file)
    args.add("--facts", pack.facts)
    args.add("--splash", ctx.file._default_splash)
    args.add("--variant", pack.variant)
    args.add("--output", site.path)
    args.add("--archive", archive)
    ctx.actions.run(
        executable = ctx.executable._packager,
        arguments = [args],
        inputs = depset(
            [pack.pack_file, pack.facts, ctx.file._default_splash],
            transitive = [runtime.files],
        ),
        outputs = [site, archive],
        mnemonic = "GodotWebPackage",
        progress_message = "Packaging web application %{label}",
    )
    executable = ctx.actions.declare_file(ctx.label.name + "/" + name + ".run")
    runfiles = launcher(ctx, executable, {"platform": "web", "site": site})
    return [
        DefaultInfo(executable = executable, files = depset([site, archive]), runfiles = runfiles),
        OutputGroupInfo(bundle = depset([site]), archive = depset([archive]), debug_symbols = depset()),
    ]

godot_web_application = rule(
    doc = "PROTOTYPE(web): package a PCK and a web template into a static site.",
    implementation = _web_application_impl,
    executable = True,
    attrs = {
        "platform_deps": attr.label_list(),
        "platform_resources": attr.label_list(allow_files = True),
        "pack": attr.label(mandatory = True, providers = [GodotPackInfo]),
        "runtime": attr.label(mandatory = True, providers = [GodotRuntimeInfo]),
        "app_name": attr.string(),
        "_packager": attr.label(
            default = Label("//tools/platforms:package_web"),
            executable = True,
            cfg = "exec",
        ),
        "_default_splash": attr.label(
            default = Label("//godot/private/engine:godot_4_7_splash.png"),
            allow_single_file = True,
        ),
    } | LAUNCH_ATTRS,
)

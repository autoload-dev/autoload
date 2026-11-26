"""
The rules of source recipe pins that generated engine repositories declare.

A recipe repository declares `:pin`, the action that configures its recipe on an execution
platform Godot accepts for it, and an engine's hub declares `:pin`, which merges its
recipes' pins into the lock file, and `:pin_<platform>` for each platform, which merges one
platform's into it and keeps the others. Generated repositories with consumer-chosen names load
this file, so its load visibility is public.
"""

load("//godot/private:paths.bzl", "runfile_key")

visibility("public")

_PIN_TOOL = Label("//tools/engine:pin")

def _recipe_pin_impl(ctx):
    files = ctx.actions.args()
    files.set_param_file_format("multiline")
    files.add_all(ctx.files.srcs)
    listing = ctx.actions.declare_file(ctx.label.name + ".inputs")
    ctx.actions.write(listing, files)
    output = ctx.actions.declare_file(ctx.label.name + ".json")
    args = ctx.actions.args()
    args.add("recipe")
    args.add("--root", ctx.label.workspace_root)
    args.add("--files", listing)
    args.add("--archive", ctx.file.archive)
    args.add("--strip-prefix", ctx.attr.strip_prefix)
    args.add_all(ctx.files.patches, before_each = "--patch")
    args.add("--output", output)
    args.add_all(ctx.attr.arguments)
    ctx.actions.run(
        executable = ctx.executable._pin,
        arguments = [args],
        inputs = [listing, ctx.file.archive] + ctx.files.patches + ctx.files.srcs,
        outputs = [output],
        mnemonic = "GodotPinRecipe",
        progress_message = "Configuring %{label}",
    )
    return [DefaultInfo(files = depset([output]))]

godot_recipe_pin = rule(
    doc = "Configure one source recipe on its execution platform and write its pin.",
    implementation = _recipe_pin_impl,
    attrs = {
        "archive": attr.label(doc = "The recipe's source archive.", allow_single_file = True, mandatory = True),
        "strip_prefix": attr.string(doc = "The archive's top-level directory, which extraction removes."),
        "patches": attr.label_list(doc = "The recipe's patches, applied in order.", allow_files = True),
        "srcs": attr.label_list(doc = "The recipe repository's custom modules and SCons.", allow_files = True),
        "arguments": attr.string_list(doc = "The recipe's configure arguments, without paths."),
        "_pin": attr.label(default = _PIN_TOOL, cfg = "exec", executable = True),
    },
)

_LAUNCHER = """#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${{BUILD_WORKSPACE_DIRECTORY:-}}" ]]; then
  echo "Run the pin with bazel run" >&2
  exit 1
fi
runfiles="${{RUNFILES_DIR:-$0.runfiles}}"
export RUNFILES_DIR="$runfiles"
mkdir -p "$(dirname "$BUILD_WORKSPACE_DIRECTORY/{lock}")"
{write}
chmod 644 "$BUILD_WORKSPACE_DIRECTORY/{lock}"
echo "Pinned {count} recipes and runtime variants in {lock}"
"""

# Replaces the lock file with every recipe's pins.
_REPLACE = 'cp "$runfiles/{merged}" "$BUILD_WORKSPACE_DIRECTORY/{lock}"'

# Merges some recipes' pins into the lock file and keeps the others.
_UPDATE = '"$runfiles/{tool}" update --lock "$BUILD_WORKSPACE_DIRECTORY/{lock}" --pins "$runfiles/{merged}"'

def _engine_pin_impl(ctx):
    merged = ctx.actions.declare_file(ctx.label.name + ".lock.json")
    args = ctx.actions.args()
    args.add("merge")
    args.add("--output", merged)
    for target, key in ctx.attr.recipes.items():
        args.add("--recipe", "%s=%s" % (key, target[DefaultInfo].files.to_list()[0].path))
    for target, variant in ctx.attr.variants.items():
        key, profile = json.decode(variant)
        args.add_all(["--variant", key, profile, target[DefaultInfo].files.to_list()[0]])
    ctx.actions.run(
        executable = ctx.executable._pin,
        arguments = [args],
        inputs = ctx.files.recipes + ctx.files.variants,
        outputs = [merged],
        mnemonic = "GodotPinLock",
        progress_message = "Merging the recipe pins of %{label}",
    )
    launcher = ctx.actions.declare_file(ctx.label.name + ".sh")
    tool = ctx.attr._update[DefaultInfo]
    write = (_UPDATE if ctx.attr.partial else _REPLACE).format(
        lock = ctx.attr.lock,
        merged = runfile_key(ctx, merged),
        tool = runfile_key(ctx, ctx.executable._update),
    )
    ctx.actions.write(launcher, _LAUNCHER.format(
        lock = ctx.attr.lock,
        write = write,
        count = len(ctx.attr.recipes) + len(ctx.attr.variants),
    ), is_executable = True)
    runfiles = ctx.runfiles(files = [merged])
    if ctx.attr.partial:
        runfiles = runfiles.merge(tool.default_runfiles)
    return [DefaultInfo(
        executable = launcher,
        files = depset([merged]),
        runfiles = runfiles,
    )]

godot_engine_pin = rule(
    doc = "Pin an engine's recipes into its lock file: bazel run @<hub>//:pin, or :pin_<platform> for one platform's.",
    implementation = _engine_pin_impl,
    executable = True,
    attrs = {
        "recipes": attr.label_keyed_string_dict(doc = "Each recipe's :pin target and its key in the lock file."),
        "variants": attr.label_keyed_string_dict(doc = "Each runtime variant's :pin target, with its recipe's key and its runtime profile as a JSON list."),
        "lock": attr.string(doc = "Path of the lock file relative to the workspace root.", mandatory = True),
        "partial": attr.bool(doc = "Whether the recipes are some of the lock file's, whose other pins it keeps."),
        "_pin": attr.label(default = _PIN_TOOL, cfg = "exec", executable = True),
        "_update": attr.label(default = _PIN_TOOL, cfg = "target", executable = True),
    },
)

def _unpinned_recipe_impl(ctx):
    fail(ctx.attr.message)

godot_unpinned_recipe = rule(
    doc = "Stand in for a recipe's engine targets while its lock file has no current pin for it.",
    implementation = _unpinned_recipe_impl,
    attrs = {"message": attr.string(mandatory = True)},
)

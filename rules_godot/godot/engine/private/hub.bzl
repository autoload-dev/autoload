"""
The generated repositories of engines: each engine's hub, one component per slot, and the
extension's toolchains repository of every engine's components.
"""

load("//godot/private:supply_chain.bzl", "BUNDLED_PACKAGES", "PACKAGE_METADATA", "source_purl", "write_metadata_package")
load("//godot/private:versions.bzl", "godot_series")
load("//godot/private/config:settings.bzl", "CPU_TABLE")
load("//godot/private/engine:profiles.bzl", "emscripten_release")

visibility(["//godot/..."])

def component(role, name, payload, platform, cpu, version, variant = "", environment = "", digest = "", untuned_only = False):
    """
    Return a hub slot description.

    Args:
        role: editor or runtime.
        name: Component target name inside the hub's toolchains package.
        payload: Label string of the payload in a sibling repository.
        platform: Slot operating system.
        cpu: Slot CPU, a CPU table key such as arm64 or x86_64.
        version: Canonical Godot version of the payload.
        variant: debug or release for runtimes.
        environment: device or simulator for iOS runtimes.
        digest: Integrity of the artifact behind an opaque runtime payload.
        untuned_only: For runtimes, whether the component serves only builds whose runtime
            needs no tuning, as godot_runtime_component's.

    Returns:
        A dict the hub repository rule serializes into a component declaration.
    """
    return {
        "role": role,
        "name": name,
        "payload": payload,
        "platform": platform,
        "cpu": cpu,
        "version": version,
        "variant": variant,
        "environment": environment,
        "digest": digest,
        "untuned_only": untuned_only,
    }

# The optional attributes of a component, which a slot leaves out when they are empty.
_OPTIONAL = ["variant", "environment", "digest", "untuned_only", "visibility"]

def _call(function, values):
    """A generated BUILD file's call of a macro or rule with the given (name, value) pairs."""
    attributes = ["    %s = %s," % (key, repr(value)) for key, value in values]
    return "\n%s(\n%s\n)\n" % (function, "\n".join(attributes))

def _engine_values(engine, default_engine):
    """The engine attributes of a component or its toolchains; none for an unnamed engine."""
    if not engine:
        return []
    return [("engine", engine)] + ([("default_engine", True)] if default_engine else [])

def _declaration(slot, engine, default_engine):
    values = [("name", slot["name"]), (slot["role"], slot["payload"])]
    values += [("platform", slot["platform"]), ("cpu", slot["cpu"])]
    values += [(key, slot[key]) for key in _OPTIONAL if slot.get(key)]
    values.append(("version", slot["version"]))
    return _call("godot_%s_component" % slot["role"], values + _engine_values(engine, default_engine))

def _android_runtime(variant, runtime):
    attributes = ["    name = %r," % variant, "    shell = %r," % runtime["shell"]]
    if runtime.get("visibility"):
        attributes.append("    visibility = %r," % runtime["visibility"])
    engine_libraries = runtime.get("engine_libraries", {})
    if not engine_libraries:
        # The shell's own engine libraries serve: the hub carries their bundled packages. A
        # source-built engine library carries its recipe's.
        attributes.append("    bundled_packages = [%r]," % BUNDLED_PACKAGES)
    else:
        # One label per variant serves every CPU; each platform slice repacks its own
        # engine library.
        attributes.append("    engine_library = select({\n%s    })," % "".join([
            "        %r: %r,\n" % (str(CPU_TABLE[cpu].constraint), label)
            for cpu, label in sorted(engine_libraries.items())
        ]))
    return "\ngodot_android_runtime(\n%s\n)\n" % "\n".join(attributes)

_PIN = """
load({pin_bzl}, "godot_engine_pin")

# Pins every recipe of this engine and its runtime variants into its lock file:
# bazel run //:pin. Each :pin_<platform> pins one platform's into it and keeps the others,
# for a host whose execution platforms configure only some platforms' recipes.
"""

_PIN_TARGET = """
godot_engine_pin(
    name = {name},
    recipes = {recipes},
    variants = {variants},
    lock = {lock},
    partial = {partial},
    visibility = ["//visibility:public"],
)
"""

def _pin_target(ctx, name, recipes, variants, partial):
    return _PIN_TARGET.format(
        name = repr(name),
        recipes = repr(recipes),
        variants = repr({label: json.encode(variant) for label, variant in variants.items()}),
        lock = repr(ctx.attr.lock),
        partial = repr(partial),
    )

_PINNED = """
# Fails with the pin command while a recipe or one of its runtime variants has no current pin
# in the lock file. Every host builds it, whatever platform the recipes are for.
filegroup(
    name = "pinned",
    srcs = {recipes},
    visibility = ["//visibility:public"],
)
"""

def _pin(ctx):
    """
    The hub's pin targets.

    :pin and :pin_<platform> write the lock file of the hub's recipes and runtime variants;
    :pinned fails while one of them has no current pin.
    """
    recipes = json.decode(ctx.attr.pin_recipes)
    variants = json.decode(ctx.attr.pin_variants or "{}")
    platforms = json.decode(ctx.attr.pin_platforms)
    targets = [_PIN.format(pin_bzl = repr(str(ctx.attr._pin_bzl))), _pin_target(ctx, "pin", recipes, variants, False)]
    targets.append(_PINNED.format(recipes = repr(sorted([
        label.rpartition(":")[0] + ":pinned"
        for label in recipes
    ]))))
    for platform in sorted({platform: True for platform in platforms.values()}):
        targets.append(_pin_target(
            ctx,
            "pin_" + platform,
            {label: key for label, key in recipes.items() if platforms[key] == platform},
            {label: variant for label, variant in variants.items() if platforms[variant[0]] == platform},
            True,
        ))
    return "".join(targets)

def _hub_impl(ctx):
    slots = json.decode(ctx.attr.components)
    names = {}
    for slot in slots:
        if slot["name"] in names:
            fail("Godot hub %s declares slot %s twice" % (ctx.name, slot["name"]))
        names[slot["name"]] = True
    pin = _pin(ctx) if ctx.attr.pin_recipes else ""
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{NAME}": ctx.attr.display_name,
        "{PIN}": pin,
        "{TOOLCHAINS_REPOSITORY}": '        "@%s//",\n' % ctx.attr.toolchains_repository if ctx.attr.toolchains_repository else "",
    })
    android = json.decode(ctx.attr.android_runtimes) if ctx.attr.android_runtimes else {}
    if android:
        write_metadata_package(
            ctx,
            source_purl("godot", ctx.attr.version),
            bundled_packages = ctx.attr.bundled_packages,
        )
        ctx.template("android/BUILD.bazel", ctx.attr._android_template, substitutions = {
            "{ANDROID_BZL}": repr(str(ctx.attr._android_bzl)),
            "{PACKAGE_METADATA}": repr(PACKAGE_METADATA),
            "{RUNTIMES}": "".join([
                _android_runtime(variant, android[variant])
                for variant in sorted(android)
            ]),
        })
    ctx.template("toolchains/BUILD.bazel", ctx.attr._toolchains_template, substitutions = {
        "{DEFS_BZL}": repr(str(ctx.attr._defs_bzl)),
        "{COMPONENTS}": "".join([_declaration(slot, ctx.attr.engine, ctx.attr.default_engine) for slot in sorted(slots, key = lambda s: s["name"])]),
    })

engine_hub = repository_rule(
    implementation = _hub_impl,
    attrs = {
        "components": attr.string(doc = "JSON list of slot descriptions from component().", mandatory = True),
        "display_name": attr.string(doc = "Apparent hub name for the generated comment.", mandatory = True),
        "engine": attr.string(doc = "Name of the engine every component belongs to; empty for the default engine."),
        "default_engine": attr.bool(doc = "Whether the named engine is also the default engine, which builds that name none take."),
        "version": attr.string(doc = "Godot version of the engine, which the package metadata of the hub's Android runtimes names."),
        "bundled_packages": attr.label(doc = "The `:bundled_packages` of the godot_bundled_packages repository of the version's COPYRIGHT.txt, which the hub's Android runtimes around official shells carry; none without."),
        "toolchains_repository": attr.string(doc = "The extension's repository of every engine's toolchains, which registers the hub's components."),
        "android_runtimes": attr.string(doc = """
            JSON object of variant to {"shell": label, "engine_libraries": {CPU: label}};
            each becomes //android:<variant>.
            """),
        "pin_recipes": attr.string(doc = "JSON object of each recipe's :pin label to its key in the lock file."),
        "pin_variants": attr.string(doc = "JSON object of each runtime variant's :pin label to its recipe's key and runtime profile."),
        "pin_platforms": attr.string(doc = "JSON object of each recipe's key to its platform, which groups the :pin_<platform> targets."),
        "lock": attr.string(doc = "Workspace-relative path of the lock file that //:pin writes."),
        "_pin_bzl": attr.label(default = Label("//godot/engine/private:pin.bzl")),
        "_android_template": attr.label(default = Label("//godot/engine/private:hub_android.BUILD.tpl")),
        "_defs_bzl": attr.label(default = Label("//godot/engine:defs.bzl")),
        "_android_bzl": attr.label(default = Label("//godot/platforms/private:android.bzl")),
        "_build_template": attr.label(default = Label("//godot/engine/private:hub.BUILD.tpl")),
        "_toolchains_template": attr.label(default = Label("//godot/engine/private:hub_toolchains.BUILD.tpl")),
    },
)

# The extension's toolchains repository, which rules_godot registers.

_TOOLCHAINS = """# Generated by godot_engines: the toolchains of every registered engine's components, which
# rules_godot's module registers with @godot_engines_toolchains//:all. Each engine's
# components lie in its hub, @<engine>//toolchains; their toolchains sort by engine, then by
# slot, so a slot's tuned component follows its prebuilt one.
load({REGISTRATION_BZL}, "component_toolchains", "emscripten_toolchains", "unpinned_emscripten_toolchains")
{TOOLCHAINS}"""

def _component_toolchains(engine, slot):
    values = [
        ("name", "%s__%s" % (engine["name"], slot["name"])),
        ("component", "@%s//toolchains:%s" % (engine["name"], slot["name"])),
        ("role", slot["role"]),
        ("platform", slot["platform"]),
        ("cpu", slot["cpu"]),
    ]
    values += [(key, slot[key]) for key in ["environment", "variant", "untuned_only"] if slot.get(key)]
    return _call("component_toolchains", values + _engine_values(engine["name"], engine["default_engine"]))

def _emscripten_toolchains(engine):
    """
    The registration of an engine's Emscripten toolchains.

    Without a pinned release, one web toolchain whose analysis says so.
    """
    emscripten = emscripten_release(engine["version"])
    name = [("name", "%s__emscripten" % engine["name"])]
    engine_values = _engine_values(engine["name"], engine["default_engine"])
    if not emscripten:
        version = [("engine_version", engine["version"]), ("series", godot_series(engine["version"]))]
        return _call("unpinned_emscripten_toolchains", name + version + engine_values)
    return _call("emscripten_toolchains", name + [("version", emscripten["version"])] + engine_values)

def _engine_toolchains_impl(ctx):
    engines = sorted(json.decode(ctx.attr.engines), key = lambda engine: engine["name"])
    ctx.file("REPO.bazel", "")
    ctx.file("BUILD.bazel", _TOOLCHAINS.format(
        REGISTRATION_BZL = repr(str(ctx.attr._registration_bzl)),
        TOOLCHAINS = "".join([
            _component_toolchains(engine, slot)
            for engine in engines
            for slot in sorted(engine["slots"], key = lambda slot: slot["name"])
        ] + [_emscripten_toolchains(engine) for engine in engines]),
    ))

engine_toolchains = repository_rule(
    doc = "Generate the toolchains of every engine's components in one repository, which rules_godot registers.",
    implementation = _engine_toolchains_impl,
    attrs = {
        "engines": attr.string(doc = """
            JSON list of each engine's {"name", "default_engine", "slots"}, its hub's slot
            descriptions from component().
            """),
        "_registration_bzl": attr.label(default = Label("//godot/engine/private:registration.bzl")),
    },
)

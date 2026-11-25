"""One generated hub layout for prebuilt engines and source builds: one component per slot."""

load("//godot/private/config:settings.bzl", "CPU_TABLE")

visibility(["//godot/..."])

def component(role, name, payload, platform, cpu, version, variant = "", environment = "", digest = "", without_build_profile = False):
    """
    Return a hub slot description.

    Args:
        role: editor or runtime.
        name: Component target name inside the hub's toolchains package.
        payload: Label string of the payload in a sibling repository.
        platform: Slot operating system.
        cpu: Slot CPU, a CPU table key such as arm64 or x86_64.
        version: Canonical Godot version of the payload; empty takes the hub's
            version_source descriptor.
        variant: debug or release for runtimes.
        environment: device or simulator for iOS runtimes.
        digest: Integrity of the artifact behind an opaque runtime payload.
        without_build_profile: For runtimes, whether the component serves only applications
            without a build profile, as godot_runtime_component's.

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
        "without_build_profile": without_build_profile,
    }

# The optional attributes of a component, which a slot leaves out when they are empty.
_OPTIONAL = ["variant", "environment", "digest", "without_build_profile", "visibility"]

def _declaration(slot, engine):
    values = [("name", slot["name"]), (slot["role"], slot["payload"])]
    values += [("platform", slot["platform"]), ("cpu", slot["cpu"])]
    values += [(key, slot[key]) for key in _OPTIONAL if slot.get(key)]
    values.append(("version", slot["version"]))
    if engine:
        values.append(("engine", engine))
    attributes = ["    %s = %s," % (key, repr(value)) for key, value in values]
    return "\ngodot_%s_component(\n%s\n)\n" % (slot["role"], "\n".join(attributes))

def _android_runtime(variant, runtime):
    attributes = ["    name = %r," % variant, "    shell = %r," % runtime["shell"]]
    if runtime.get("visibility"):
        attributes.append("    visibility = %r," % runtime["visibility"])
    engine_libraries = runtime.get("engine_libraries", {})
    if engine_libraries:
        # One label per variant serves every CPU; each platform slice repacks its own
        # engine library.
        attributes.append("    engine_library = select({\n%s    })," % "".join([
            "        %r: %r,\n" % (str(CPU_TABLE[cpu].constraint), label)
            for cpu, label in sorted(engine_libraries.items())
        ]))
    return "\ngodot_android_runtime(\n%s\n)\n" % "\n".join(attributes)

_PIN = """
load({pin_bzl}, "godot_engine_pin")

# Pins every recipe of this source build and its runtime variants into its lock file:
# bazel run //:pin.
godot_engine_pin(
    name = "pin",
    recipes = {recipes},
    variants = {variants},
    lock = {lock},
    visibility = ["//visibility:public"],
)
"""

def _pin(ctx):
    """The :pin target that writes the lock file of the hub's recipes and runtime variants."""
    variants = json.decode(ctx.attr.pin_variants or "{}")
    return _PIN.format(
        pin_bzl = repr(str(ctx.attr._pin_bzl)),
        recipes = repr(json.decode(ctx.attr.pin_recipes)),
        variants = repr({label: json.encode(variant) for label, variant in variants.items()}),
        lock = repr(ctx.attr.lock),
    )

def _hub_impl(ctx):
    slots = json.decode(ctx.attr.components)
    if ctx.attr.version_source:
        version = json.decode(ctx.read(ctx.path(ctx.attr.version_source)))["version"]
        slots = [slot | {"version": slot["version"] or version} for slot in slots]
    names = {}
    for slot in slots:
        if slot["name"] in names:
            fail("Godot hub %s declares slot %s twice" % (ctx.name, slot["name"]))
        names[slot["name"]] = True
    pin = _pin(ctx) if ctx.attr.pin_recipes else ""
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{NAME}": ctx.attr.display_name,
        "{PIN}": pin,
    })
    android = json.decode(ctx.attr.android_runtimes) if ctx.attr.android_runtimes else {}
    if android:
        ctx.template("android/BUILD.bazel", ctx.attr._android_template, substitutions = {
            "{ANDROID_BZL}": repr(str(ctx.attr._android_bzl)),
            "{RULES_ANDROID_BZL}": repr(str(ctx.attr._rules_android_bzl)),
            "{RUNTIMES}": "".join([
                _android_runtime(variant, android[variant])
                for variant in sorted(android)
            ]),
            # Every variant's shell library has the same classes; plugins compile against
            # the release one when it exists.
            "{PLUGIN_API_RUNTIME}": "release" if "release" in android else sorted(android)[0],
        })
    ctx.template("toolchains/BUILD.bazel", ctx.attr._toolchains_template, substitutions = {
        "{DEFS_BZL}": repr(str(ctx.attr._defs_bzl)),
        "{COMPONENTS}": "".join([_declaration(slot, ctx.attr.engine) for slot in sorted(slots, key = lambda s: s["name"])]),
    })

engine_hub = repository_rule(
    implementation = _hub_impl,
    attrs = {
        "components": attr.string(doc = "JSON list of slot descriptions from component().", mandatory = True),
        "display_name": attr.string(doc = "Apparent hub name for the generated comment.", mandatory = True),
        "engine": attr.string(doc = "Name of the engine every component belongs to; empty for the default engine."),
        "android_runtimes": attr.string(doc = """
            JSON object of variant to {"shell": label, "engine_libraries": {CPU: label}};
            each becomes //android:<variant>, and //android:plugin_api exports one of them
            for compilation only.
            """),
        "version_source": attr.label(doc = "A source descriptor whose version fills slots without one."),
        "pin_recipes": attr.string(doc = "JSON object of each recipe's :pin label to its key in the lock file."),
        "pin_variants": attr.string(doc = "JSON object of each runtime variant's :pin label to its recipe's key and runtime profile."),
        "lock": attr.string(doc = "Workspace-relative path of the lock file that //:pin writes."),
        "_pin_bzl": attr.label(default = Label("//godot/engine/private:pin.bzl")),
        "_android_template": attr.label(default = Label("//godot/engine/private:hub_android.BUILD.tpl")),
        "_rules_android_bzl": attr.label(default = Label("@rules_android//rules:rules.bzl")),
        "_defs_bzl": attr.label(default = Label("//godot/engine:defs.bzl")),
        "_android_bzl": attr.label(default = Label("//godot/platforms/private:android.bzl")),
        "_build_template": attr.label(default = Label("//godot/engine/private:hub.BUILD.tpl")),
        "_toolchains_template": attr.label(default = Label("//godot/engine/private:hub_toolchains.BUILD.tpl")),
    },
)

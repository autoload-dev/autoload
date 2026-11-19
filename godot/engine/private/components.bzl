"""Engine components: one editor or runtime slot with its provenance and toolchain registration."""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("//godot:providers.bzl", "GodotComponentInfo", "GodotRuntimeInfo")
load("//godot/engine/private:generator.bzl", "GodotEngineVersionInfo")
load("//godot/engine/private:prebuilt.bzl", "PrebuiltArtifactInfo")
load("//godot/engine/private:resolution.bzl", "EDITOR_TOOLCHAIN_TYPE", "RUNTIME_TOOLCHAIN_TYPE", "engine_toolchain")
load("//godot/platforms/private:android_runtime_bridge.bzl", "ANDROID_PAYLOAD_ASPECTS")
load("//godot/platforms/private:ios_runtime_bridge.bzl", "IOS_PAYLOAD_ASPECTS")
load("//godot/private:versions.bzl", "require_supported_godot_version", "require_supported_source_version")
load("//godot/private/config:settings.bzl", "CPU_CONSTRAINTS", "CPU_TABLE", "ENVIRONMENT_CONSTRAINTS", "OPERATING_SYSTEM_CONSTRAINTS")

visibility(["//godot/..."])

_VARIANT_SETTINGS = {
    "debug": Label("//godot:debug"),
    "release": Label("//godot:release"),
}

_ENGINE_FLAG = Label("//godot:engine")
_DEFAULT_ENGINE = Label("//godot:default_engine")

def _fields(value):
    return {name: getattr(value, name) for name in dir(value) if name not in ["to_json", "to_proto"]}

def _forwarded(target, role, label, engine):
    """
    Return the toolchain value of a payload that is itself a component, or None.

    The forwarded payload belongs to the forwarding component's engine, which its
    provenance names.
    """
    if platform_common.ToolchainInfo not in target:
        return None
    godot = getattr(target[platform_common.ToolchainInfo], "godot", None)
    if not godot or getattr(godot, "role", None) == None:
        fail("%s payload %s provides a foreign ToolchainInfo" % (label, target.label))
    if godot.role != role:
        fail("%s payload %s is a %s component, not a %s component" % (label, target.label, godot.role, role))
    provenance = GodotComponentInfo(**(_fields(godot.provenance) | {"engine": engine}))
    return struct(**(_fields(godot) | {"provenance": provenance}))

def _require_slot(ctx, payload, facts):
    """
    Fail when a payload's own slot facts contradict the component's declared slot.

    Args:
        ctx: Rule context of the component.
        payload: Label of the payload, for the diagnostic.
        facts: dict of attribute name to the payload's value; empty values are unknown.
    """
    for name, value in facts.items():
        declared = getattr(ctx.attr, name, "")
        if name == "cpu":
            # A universal macOS template fills every macOS CPU slot.
            value = "" if value == "universal" else value
        if value and declared and value != declared:
            fail("%s: payload %s is for %s %r, but the component declares %r" % (
                ctx.label,
                payload,
                name,
                value,
                declared,
            ))

def _require_forwarded_slot(ctx, target, godot):
    facts = {"platform": godot.provenance.platform, "cpu": godot.provenance.cpu}
    if godot.role == "runtime":
        facts["environment"] = godot.provenance.environment
        facts["variant"] = godot.provenance.variant
    _require_slot(ctx, target.label, facts)

def _require_version(version, kind):
    if kind == "source":
        require_supported_source_version(version)
    else:
        require_supported_godot_version(version)

def _artifact(target):
    """The archive digest of a prebuilt payload, or empty when the payload names none."""
    return target[PrebuiltArtifactInfo].digest if PrebuiltArtifactInfo in target else ""

def _producer(target):
    """Source-recipe metadata of a payload, or None for prebuilt and opaque payloads."""
    return target[GodotEngineVersionInfo] if GodotEngineVersionInfo in target else None

def _provenance(ctx, role, version, kind, origin, producer = None, artifact_digest = ""):
    return GodotComponentInfo(
        component = str(ctx.label),
        engine = ctx.attr.engine,
        role = role,
        platform = ctx.attr.platform,
        cpu = ctx.attr.cpu,
        environment = getattr(ctx.attr, "environment", ""),
        variant = getattr(ctx.attr, "variant", ""),
        version = version,
        kind = kind,
        # The declared origin describes the component; the payload's is the fallback.
        origin = ctx.attr.origin or origin,
        # A producer or prebuilt payload names its own digest; an opaque payload, such as
        # an XCFramework or AAR import, takes the declared one.
        digest = producer.digest if producer else (artifact_digest or getattr(ctx.attr, "digest", "")),
        customizations = producer.customizations if producer else {},
    )

def _editor_component_impl(ctx):
    target = ctx.attr.editor
    godot = _forwarded(target, "editor", ctx.label, ctx.attr.engine)
    if godot:
        _require_forwarded_slot(ctx, target, godot)
    else:
        info = target[DefaultInfo]
        if not info.files_to_run or not info.files_to_run.executable:
            fail("%s editor %s must be an executable target" % (ctx.label, target.label))
        producer = _producer(target)
        kind = "source" if producer else "prebuilt"
        version = producer.canonical_version if producer else ctx.attr.version
        _require_version(version, kind)
        godot = struct(
            role = "editor",
            editor = info.files_to_run,
            files = depset(transitive = [info.files, info.default_runfiles.files]),
            version = version,
            provenance = _provenance(ctx, "editor", version, kind, str(target.label), producer, _artifact(target)),
        )
    return [
        platform_common.ToolchainInfo(godot = godot),
        godot.provenance,
        DefaultInfo(files = godot.files),
    ]

_editor_component = rule(
    implementation = _editor_component_impl,
    attrs = {
        "editor": attr.label(mandatory = True, allow_files = True, cfg = "exec"),
        "platform": attr.string(mandatory = True),
        "cpu": attr.string(mandatory = True),
        "version": attr.string(mandatory = True),
        "origin": attr.string(),
        "engine": attr.string(),
    },
)

def _declared_runtime(ctx, target):
    """GodotRuntimeInfo for a plain desktop template file without producer metadata."""
    files = target[DefaultInfo].files
    payload = files.to_list()
    if len(payload) != 1:
        fail("%s desktop runtime %s must be one template file or carry GodotRuntimeInfo" % (ctx.label, target.label))
    return GodotRuntimeInfo(
        executable = payload[0],
        files = files,
        platform = ctx.attr.platform,
        cpu = ctx.attr.cpu,
        environment = "",
        facts_source = "declared",
        origin = str(target.label),
        version = ctx.attr.version,
        bundle_files = {},
        variant = ctx.attr.variant,
        debug_symbols = None,
        minimum_os = "",
    )

# The provider each runtime bridge forwards to rules_android or rules_apple, and what
# supplies it.
_MOBILE_PAYLOAD_PROVIDERS = {
    "android": (JavaInfo, "JavaInfo", "a godot_android_runtime"),
    "ios": (CcInfo, "CcInfo", "an XCFramework import or a source recipe's :engine_library"),
}

def _runtime_component_impl(ctx):
    target = ctx.attr.runtime
    godot = _forwarded(target, "runtime", ctx.label, ctx.attr.engine)
    contract = _MOBILE_PAYLOAD_PROVIDERS.get(ctx.attr.platform)
    if not godot and contract and contract[0] not in target:
        fail("%s: the %s runtime payload %s has no %s; use %s" % (
            ctx.label,
            ctx.attr.platform,
            target.label,
            contract[1],
            contract[2],
        ))
    if godot:
        _require_forwarded_slot(ctx, target, godot)
    else:
        runtime = target[GodotRuntimeInfo] if GodotRuntimeInfo in target else None
        if runtime:
            _require_slot(ctx, target.label, {
                "platform": runtime.platform,
                "cpu": runtime.cpu,
                "environment": runtime.environment,
                "variant": runtime.variant,
            })
        elif ctx.attr.platform in ["linux", "macos"]:
            runtime = _declared_runtime(ctx, target)
        producer = _producer(target)
        kind = "source" if producer or (runtime and runtime.facts_source == "source") else "prebuilt"
        if runtime:
            version = runtime.version
        else:
            version = producer.canonical_version if producer else ctx.attr.version
        _require_version(version, kind)
        godot = struct(
            role = "runtime",
            payload = target,
            runtime = runtime,
            files = target[DefaultInfo].files,
            version = version,
            provenance = _provenance(
                ctx,
                "runtime",
                version,
                kind,
                runtime.origin if runtime else str(target.label),
                producer,
                _artifact(target),
            ),
        )
    return [
        platform_common.ToolchainInfo(godot = godot),
        godot.provenance,
        DefaultInfo(files = godot.files),
    ]

_RUNTIME_ATTRS = {
    "engine": attr.string(),
    "platform": attr.string(mandatory = True),
    "cpu": attr.string(mandatory = True),
    "environment": attr.string(),
    "variant": attr.string(mandatory = True),
    "version": attr.string(mandatory = True),
    "origin": attr.string(),
    "digest": attr.string(),
}

_runtime_component = rule(
    implementation = _runtime_component_impl,
    attrs = _RUNTIME_ATTRS | {"runtime": attr.label(mandatory = True, allow_files = True)},
)

# Android payloads replay rules_android's aspects before they enter ToolchainInfo.
_android_runtime_component = rule(
    implementation = _runtime_component_impl,
    attrs = _RUNTIME_ATTRS | {
        "runtime": attr.label(mandatory = True, allow_files = True, aspects = ANDROID_PAYLOAD_ASPECTS),
    },
)

# iOS payloads replay rules_apple's propagation aspects before they enter ToolchainInfo.
_ios_runtime_component = rule(
    implementation = _runtime_component_impl,
    attrs = _RUNTIME_ATTRS | {
        "runtime": attr.label(mandatory = True, allow_files = True, aspects = IOS_PAYLOAD_ASPECTS),
    },
)

def _engine_setting(name, engine, visibility, tags):
    """
    Return the setting a component's toolchain requires: its engine is the selected one.

    A component that names no engine belongs to the default engine; a named one gets its
    own `<name>.engine` setting on --@rules_godot//godot:engine.
    """
    if not engine:
        return _DEFAULT_ENGINE
    native.config_setting(
        name = name + ".engine",
        flag_values = {_ENGINE_FLAG: engine},
        visibility = visibility,
        tags = tags,
    )
    return ":%s.engine" % name

def _editor_macro_impl(name, visibility, editor, platform, cpu, version, origin, engine, tags):
    _editor_component(
        name = name,
        editor = editor,
        platform = platform,
        cpu = cpu,
        version = version,
        origin = origin,
        engine = engine,
        visibility = visibility,
        tags = tags,
    )
    native.toolchain(
        name = name + ".toolchain",
        toolchain = ":" + name,
        toolchain_type = EDITOR_TOOLCHAIN_TYPE,
        exec_compatible_with = [OPERATING_SYSTEM_CONSTRAINTS[platform], CPU_CONSTRAINTS[cpu]],
        target_settings = [_engine_setting(name, engine, visibility, tags)],
        visibility = visibility,
        tags = tags,
    )

def runtime_slot_error(name, platform, environment, _fail = fail):
    """
    Check the iOS environment of a godot_runtime_component's slot.

    Args:
        name: Name of the godot_runtime_component.
        platform: Its platform attribute.
        environment: Its environment attribute, empty when unset.
        _fail: Called with the error; the function then returns.
    """
    if platform == "ios" and environment not in ["device", "simulator"]:
        _fail("%s: iOS runtimes require environment = device or simulator" % name)
        return
    if platform != "ios" and environment:
        _fail("%s: environment is only valid for iOS runtimes" % name)
        return

def _runtime_macro_impl(name, visibility, runtime, platform, cpu, variant, version, environment, origin, digest, engine, tags):
    runtime_slot_error(name, platform, environment)
    constraints = [OPERATING_SYSTEM_CONSTRAINTS[platform], CPU_CONSTRAINTS[cpu]]
    if environment:
        constraints.append(ENVIRONMENT_CONSTRAINTS[environment])
    component = {
        "android": _android_runtime_component,
        "ios": _ios_runtime_component,
    }.get(platform, _runtime_component)
    component(
        name = name,
        runtime = runtime,
        platform = platform,
        cpu = cpu,
        environment = environment,
        variant = variant,
        version = version,
        origin = origin,
        digest = digest,
        engine = engine,
        visibility = visibility,
        tags = tags,
    )
    native.toolchain(
        name = name + ".toolchain",
        toolchain = ":" + name,
        toolchain_type = RUNTIME_TOOLCHAIN_TYPE,
        tags = tags,
        target_compatible_with = constraints,
        target_settings = [_VARIANT_SETTINGS[variant], _engine_setting(name, engine, visibility, tags)],
        visibility = visibility,
    )

def _resolved_runtime_impl(ctx):
    godot = engine_toolchain(ctx, "runtime")
    if not godot.runtime:
        fail("%s: the selected runtime component %s has no GodotRuntimeInfo for desktop packaging" % (
            ctx.label,
            godot.provenance.component,
        ))
    return [godot.runtime, godot.provenance, DefaultInfo(files = godot.runtime.files)]

resolved_runtime = rule(
    doc = "Forward the GodotRuntimeInfo of the runtime component resolved in this configuration.",
    implementation = _resolved_runtime_impl,
    toolchains = [config_common.toolchain_type(RUNTIME_TOOLCHAIN_TYPE, mandatory = False)],
)

_COMMON = {
    "cpu": attr.string(
        doc = "CPU of the slot as Godot's CPU tag: arm32, arm64, x86_32, x86_64 or rv64.",
        mandatory = True,
        configurable = False,
        values = sorted(CPU_TABLE),
    ),
    "version": attr.string(
        doc = "Canonical Godot version of the payload; producer metadata takes precedence where present.",
        mandatory = True,
        configurable = False,
    ),
    "origin": attr.string(
        doc = "Optional human-readable origin recorded in provenance; never part of selection.",
        configurable = False,
    ),
    "engine": attr.string(
        doc = """
        Name of the engine the slot belongs to; the component fills it only in builds whose
        --@rules_godot//godot:engine names that engine. Empty, the default, joins the
        default engine, which builds use when the flag is empty.
        """,
        configurable = False,
    ),
    "tags": attr.string_list(
        doc = "Conventional Bazel tags for both generated targets, such as manual for a payload only some builds need.",
        configurable = False,
    ),
}

godot_editor_component = macro(
    doc = """
    Declare one execution-platform editor slot and its toolchain registration.

    Creates the provenance-carrying toolchain implementation `<name>` and Bazel's
    built-in `toolchain()` `<name>.toolchain`, constrained to the operating system and CPU
    of the execution platform and to the engine selected by `--@rules_godot//godot:engine`.
    A registration set is a package of components: register it with its `:all` pattern;
    the first registered candidate of the selected engine for a slot wins. The
    editor may be an executable target, such as a prebuilt editor archive's `:editor` or
    a source recipe's `:godot`, or another editor component, whose payload and provenance
    are forwarded.

    Example:
    ```starlark
    godot_editor_component(
        name = "editor_macos_arm64",
        editor = "@godot_editor_macos//:editor",
        platform = "macos",
        cpu = "arm64",
        version = "4.7.2",
    )
    ```

    ### Default outputs
    | kind | cardinality | availability | behavior |
    | --- | --- | --- | --- |
    | files | many | always | build the editor payload and its runfiles; no run behavior |

    ### Output groups
    none

    ### Generated targets
    | name | kind | purpose | reason | visibility | testonly | prerequisites | availability |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | {name}.toolchain | metadata | analysis_boundary | register the slot with editor_toolchain_type; toolchain resolution is a separate boundary | caller | inherit | none | always |
    | {name}.engine | metadata | analysis_boundary | the config_setting on --@rules_godot//godot:engine that the toolchain requires for a named engine | caller | inherit | none | engine named |

    ### Providers
    | name | role | availability |
    | --- | --- | --- |
    | ToolchainInfo | godot editor files, executable, version and provenance | always |
    | GodotComponentInfo | Provenance of the declared slot | always |
    """,
    implementation = _editor_macro_impl,
    attrs = _COMMON | {
        "editor": attr.label(
            doc = "Executable editor for the execution platform, or another editor component.",
            mandatory = True,
        ),
        "platform": attr.string(
            doc = "Operating system of the slot's editor platform: linux or macos.",
            mandatory = True,
            configurable = False,
            values = ["linux", "macos"],
        ),
    },
)

godot_runtime_component = macro(
    doc = """
    Declare one target-platform runtime slot and its toolchain registration.

    Creates the provenance-carrying toolchain implementation `<name>` and Bazel's
    built-in `toolchain()` `<name>.toolchain`, constrained to the target platform's operating
    system, CPU and iOS environment, with `target_settings` on
    `--@rules_godot//godot:variant` for the template variant and on
    `--@rules_godot//godot:engine` for the engine. The runtime may be a
    desktop template file, a target with GodotRuntimeInfo, an iOS XCFramework import or
    `:engine_library`, an Android runtime, a `select()` between prepared same-slot
    payloads, or another runtime component, whose payload and provenance are forwarded.
    Every selected branch must fill the declared slot; slot facts are not configurable.

    Example:
    ```starlark
    godot_runtime_component(
        name = "runtime_ios_arm64_simulator_debug",
        runtime = "@godot_ios_arm64_simulator_debug//:engine_library",
        platform = "ios",
        cpu = "arm64",
        environment = "simulator",
        variant = "debug",
        version = "4.7.2",
    )
    ```

    ### Default outputs
    | kind | cardinality | availability | behavior |
    | --- | --- | --- | --- |
    | files | many | always | build the runtime payload; no run behavior |

    ### Output groups
    none

    ### Generated targets
    | name | kind | purpose | reason | visibility | testonly | prerequisites | availability |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | {name}.toolchain | metadata | analysis_boundary | register the slot with runtime_toolchain_type; toolchain resolution is a separate boundary | caller | inherit | none | always |
    | {name}.engine | metadata | analysis_boundary | the config_setting on --@rules_godot//godot:engine that the toolchain requires for a named engine | caller | inherit | none | engine named |

    ### Providers
    | name | role | availability |
    | --- | --- | --- |
    | ToolchainInfo | godot runtime payload, GodotRuntimeInfo where known, version and provenance | always |
    | GodotComponentInfo | Provenance of the declared slot | always |
    """,
    implementation = _runtime_macro_impl,
    attrs = _COMMON | {
        "runtime": attr.label(
            doc = "Runtime payload for the declared slot, a select() over prepared payloads, or another runtime component.",
            mandatory = True,
        ),
        "platform": attr.string(
            doc = "Operating system of the slot's target platform: linux, macos, android or ios.",
            mandatory = True,
            configurable = False,
            values = ["linux", "macos", "android", "ios"],
        ),
        "variant": attr.string(
            doc = "Godot template variant the payload implements: debug or release.",
            mandatory = True,
            configurable = False,
            values = ["debug", "release"],
        ),
        "environment": attr.string(
            doc = "iOS environment, device or simulator; required for iOS and empty otherwise.",
            configurable = False,
            values = ["", "device", "simulator"],
        ),
        "digest": attr.string(
            doc = """
            Optional digest of the artifact behind an opaque payload, such as the archive of
            an XCFramework import or an Android shell AAR, recorded in provenance. Source
            recipes and prebuilt template files supply their own, which take precedence.
            """,
            configurable = False,
        ),
    },
)

"""
The tag evaluation of the godot_engines module extension.

The planner takes the extension's modules and returns the repositories to declare; the
extension instantiates them. Errors go through `_fail`, so a Starlark unit test with mocked
modules collects them; the planner returns None after an error.
"""

load("//godot/engine/private:catalogue.bzl", "EDITOR_PLATFORMS", "RELEASES", "TEMPLATE_CPUS")
load("//godot/engine/private:hub.bzl", "component")
load("//godot/engine/private:source_build_rows.bzl", "ROWS", "plan_rows", "recipe_declarations", "slot_name")
load("//godot/private:versions.bzl", "godot_version_error")

visibility(["//godot/..."])

def _release_urls(tag, slug):
    """Godot's CDN URL, then the GitHub release URL, of Godot_v<tag>_<slug>."""
    version, flavor = tag.split("-", 1)
    return [
        "https://downloads.godotengine.org/?version=%s&flavor=%s&slug=%s" % (version, flavor, slug),
        "https://github.com/godotengine/godot-builds/releases/download/%s/Godot_v%s_%s" % (tag, tag, slug),
    ]

def prebuilt_plan(tag, *, _fail = fail):
    """
    Return editor archives, the templates archive and macOS layout of a prebuilt tag.

    Args:
        tag: A godot_engines.prebuilt tag.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        A struct of editors, the source archive that builds missing runtimes, templates,
        Android shells and iOS simulator CPUs, or None after an error.
    """
    error = godot_version_error(tag.version)
    if error:
        return _fail(error)
    release = RELEASES.get(tag.version)
    editor_platforms = sorted(tag.editor_urls) if tag.editor_urls else (release["editor_platforms"] if release else [])
    if not editor_platforms:
        return _fail((
            "Godot %s has no built-in pins; set editor_urls/editor_integrity/editor_binaries " +
            "and templates_urls/templates_integrity on godot_engines.prebuilt(name = %r)"
        ) % (tag.version, tag.name))
    editors = {}
    for editor_platform in editor_platforms:
        if editor_platform not in EDITOR_PLATFORMS:
            return _fail("godot_engines.prebuilt %r: unknown editor platform %r; expected one of %s" % (tag.name, editor_platform, sorted(EDITOR_PLATFORMS)))
        layout = EDITOR_PLATFORMS[editor_platform]
        if tag.editor_urls:
            if editor_platform not in tag.editor_integrity:
                return _fail("godot_engines.prebuilt %r: editor_integrity lacks %r" % (tag.name, editor_platform))
            urls = tag.editor_urls[editor_platform]
            integrity = tag.editor_integrity[editor_platform]
            binary = tag.editor_binaries.get(editor_platform, layout.binary.format(tag = release["tag"]) if release else "")
            if not binary:
                return _fail("godot_engines.prebuilt %r: editor_binaries lacks %r" % (tag.name, editor_platform))
        else:
            urls = _release_urls(release["tag"], layout.suffix + ".zip")
            integrity = release[editor_platform]
            binary = layout.binary.format(tag = release["tag"])
        editors[editor_platform] = struct(urls = urls, integrity = integrity, binary = binary, layout = layout)
    for attribute in ["templates_macos_cpus", "templates_linux_cpus"]:
        if getattr(tag, attribute) and not tag.templates_urls:
            return _fail("godot_engines.prebuilt %r: %s describes templates_urls; set both" % (tag.name, attribute))
    if tag.templates_urls:
        if not tag.templates_integrity:
            return _fail("godot_engines.prebuilt %r: templates_integrity is required with templates_urls" % tag.name)
        templates = struct(
            urls = tag.templates_urls,
            integrity = tag.templates_integrity,
            macos_cpus = tag.templates_macos_cpus or ["universal"],
            linux_cpus = tag.templates_linux_cpus or TEMPLATE_CPUS["linux"],
        )
    elif release:
        templates = struct(
            urls = _release_urls(release["tag"], "export_templates.tpz"),
            integrity = release["templates"],
            macos_cpus = release["macos_cpus"],
            linux_cpus = release.get("linux_cpus", TEMPLATE_CPUS["linux"]),
        )
    else:
        return _fail("godot_engines.prebuilt %r: Godot %s needs templates_urls and templates_integrity" % (tag.name, tag.version))
    if tag.android_shell_urls:
        if not tag.android_shell_integrity:
            return _fail("godot_engines.prebuilt %r: android_shell_integrity is required with android_shell_urls" % tag.name)
        android_shell = struct(urls = tag.android_shell_urls, integrity = tag.android_shell_integrity)
    elif release and "android_shell" in release:
        android_shell = struct(**release["android_shell"])
    else:
        android_shell = None
    if tag.android_debug_shell_urls:
        if not tag.android_debug_shell_integrity:
            return _fail("godot_engines.prebuilt %r: android_debug_shell_integrity is required with android_debug_shell_urls" % tag.name)
        android_debug_shell = struct(urls = tag.android_debug_shell_urls, integrity = tag.android_debug_shell_integrity)
    else:
        android_debug_shell = None
    if tag.ios_simulator_cpus:
        simulator_cpus = tag.ios_simulator_cpus
    elif release:
        simulator_cpus = release["ios_simulator_cpus"]
    else:
        simulator_cpus = []
    return struct(
        editors = editors,
        source = (release or {}).get("source") if tag.build_missing_runtimes else None,
        templates = templates,
        android_shell = android_shell,
        android_debug_shell = android_debug_shell,
        ios_simulator_cpus = simulator_cpus,
        android_cpus = (release or {}).get("android_cpus", TEMPLATE_CPUS["android"]),
    )

def prebuilt_slots(tag, plan):
    """
    Return the hub slots of a prebuilt plan.

    Args:
        tag: The godot_engines.prebuilt tag of the plan.
        plan: The result of prebuilt_plan.

    Returns:
        A list of hub component descriptions.
    """
    slots = []
    for editor_platform, editor in plan.editors.items():
        for cpu in editor.layout.cpus:
            slots.append(component(
                role = "editor",
                name = "editor_%s_%s" % (editor.layout.platform, cpu),
                payload = "@%s_editor_%s//:editor" % (tag.name, editor_platform),
                platform = editor.layout.platform,
                cpu = cpu,
                version = tag.version,
            ))
    templates = "@%s_templates//:" % tag.name
    for variant in ["release", "debug"]:
        for cpu in plan.templates.linux_cpus:
            slots.append(component(
                role = "runtime",
                name = "runtime_linux_%s_%s" % (cpu, variant),
                payload = templates + "linux_%s_%s" % (cpu, variant),
                platform = "linux",
                cpu = cpu,
                version = tag.version,
                variant = variant,
            ))
        for cpu in ["arm64", "x86_64"]:
            if plan.templates.macos_cpus == ["universal"]:
                payload = templates + "macos_" + variant
            elif cpu in plan.templates.macos_cpus:
                payload = templates + "macos_%s_%s" % (cpu, variant)
            else:
                continue
            slots.append(component(
                role = "runtime",
                name = "runtime_macos_%s_%s" % (cpu, variant),
                payload = payload,
                platform = "macos",
                cpu = cpu,
                version = tag.version,
                variant = variant,
            ))
    for variant in ["release", "debug"]:
        slots.append(component(
            role = "runtime",
            name = "runtime_ios_arm64_device_" + variant,
            payload = templates + "ios_" + variant,
            platform = "ios",
            cpu = "arm64",
            version = tag.version,
            variant = variant,
            environment = "device",
            digest = plan.templates.integrity,
        ))
        for cpu in plan.ios_simulator_cpus:
            slots.append(component(
                role = "runtime",
                name = "runtime_ios_%s_simulator_%s" % (cpu, variant),
                payload = templates + "ios_" + variant,
                platform = "ios",
                cpu = cpu,
                version = tag.version,
                variant = variant,
                environment = "simulator",
                digest = plan.templates.integrity,
            ))

    # The Android shell AARs of official releases are template_release builds with every
    # ABI's engine library; a debug shell is an explicit pin.
    for variant, shell in [("release", plan.android_shell), ("debug", plan.android_debug_shell)]:
        if not shell:
            continue
        for cpu in plan.android_cpus:
            slots.append(component(
                role = "runtime",
                name = "runtime_android_%s_%s" % (cpu, variant),
                payload = "//android:" + variant,
                platform = "android",
                cpu = cpu,
                version = tag.version,
                variant = variant,
                digest = shell.integrity,
            ))
    return slots

# The build policy of the runtimes a prebuilt engine builds from its release's sources: the
# modules of Godot's official builds.
_MISSING_RUNTIME_POLICY = {
    "enabled_modules": [],
    "default_modules": True,
    "custom_modules": {},
    "patches": [],
    "patch_strip": 1,
    "build_options": {},
    "build_name": "custom",
    "python": None,
    "configure_timeout": 600,
}

# Platform options of those runtimes. Vulkan would need the MoltenVK SDK on the configuring
# Mac; Metal and OpenGL stay.
_MISSING_RUNTIME_OPTIONS = {"ios": {"vulkan": "no"}}

def missing_runtimes(tag, plan, slots):
    """
    Return the source declarations, slots and Android runtimes of the runtimes a prebuilt lacks.

    Args:
        tag: The godot_engines.prebuilt tag of the plan.
        plan: The result of prebuilt_plan.
        slots: The prebuilt slots of the plan.

    Returns:
        A struct of `declarations`, the source archive and recipe repositories, `slots`,
        the source-built hub slots, and `android`, their Android runtimes by variant; None
        without a missing runtime or a source archive.
    """
    if not plan.source:
        return None
    covered = {slot["name"]: True for slot in slots}
    rows = [row for row in ROWS if row.build_target != "editor" and slot_name(row) not in covered]
    if not rows:
        return None
    name = tag.name + "_source"
    source = "@%s_archive//:source.json" % name

    # The catalogue knows the sources' version, so the hub need not read the archive.
    rows_plan = plan_rows(name, rows, version = plan.source["version"])
    declarations = [_declaration("godot_engine_source", name = name + "_archive", **plan.source)]
    for declaration in recipe_declarations(name, source, rows_plan, _MISSING_RUNTIME_POLICY):
        options = _MISSING_RUNTIME_OPTIONS.get(declaration.attrs.get("platform"))
        if options:
            declaration.attrs["build_options"] = declaration.attrs["build_options"] | options
        declarations.append(declaration)
    return struct(
        declarations = declarations,
        slots = rows_plan.slots,
        android = rows_plan.android,
    )

def _scalar(value):
    return str(value) if type(value) == "Label" else value

def _plain(value):
    """A JSON-encodable form of a tag value; labels compare by their canonical form."""
    if type(value) == "list":
        return [_scalar(item) for item in value]
    if type(value) == "dict":
        return {str(key): _scalar(item) for key, item in value.items()}
    return _scalar(value)

def _signature(kind, tag, attributes):
    values = {"kind": kind}
    for attribute in sorted(attributes):
        values[attribute] = _plain(getattr(tag, attribute))
    return json.encode(values)

def selected_tags(modules, *, tag_attributes, _fail = fail):
    """
    Select one request per name.

    Root requests own their names, identical dependency requests coalesce, and conflicting
    ones fail.

    Args:
        modules: module_ctx.modules.
        tag_attributes: The attribute names of each tag class, keyed by tag class.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        A list of structs with kind, tag, module and is_root, sorted by name, or None after
        an error.
    """
    requests = {}
    for mod in modules:
        # The three tags share one namespace of names.
        for kind in ["prebuilt", "source", "source_build"]:
            for tag in getattr(mod.tags, kind):
                requests.setdefault(tag.name, []).append(struct(
                    kind = kind,
                    tag = tag,
                    signature = _signature(kind, tag, tag_attributes[kind]),
                    module = mod.name,
                    is_root = mod.is_root,
                ))
    selected = []
    for name in sorted(requests):
        candidates = requests[name]
        effective = [candidate for candidate in candidates if candidate.is_root] or candidates
        first = effective[0]
        for candidate in effective[1:]:
            if candidate.signature != first.signature:
                return _fail((
                    "Conflicting Godot requests named %r from %s and %s. " +
                    "Pin one configuration with this name in the root module."
                ) % (name, first.module, candidate.module))
        selected.append(first)
    return selected

def _declaration(rule, **attrs):
    return struct(rule = rule, attrs = attrs)

def plan_engines(modules, *, tag_attributes, _fail = fail):
    """
    Return the repositories the godot_engines extension declares.

    Args:
        modules: module_ctx.modules.
        tag_attributes: The attribute names of each tag class, keyed by tag class.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        A list of structs with `rule`, the name of a repository rule or macro, and `attrs`,
        its keyword arguments; None after an error.
    """
    selections = selected_tags(modules, tag_attributes = tag_attributes, _fail = _fail)
    if selections == None:
        return None
    declarations = []
    for selection in selections:
        tag = selection.tag
        if selection.kind == "source":
            declarations.append(_declaration(
                "godot_engine_source",
                name = tag.name,
                urls = tag.urls,
                sha256 = tag.sha256,
                strip_prefix = tag.strip_prefix,
                version = tag.version,
            ))
            continue
        if selection.kind == "source_build":
            declarations.append(_declaration(
                "godot_engine_source_build",
                name = tag.name,
                source = tag.source,
                platforms = tag.platforms,
                cpus = tag.cpus,
                build_targets = tag.build_targets,
                ios_environments = tag.ios_environments,
                enabled_modules = tag.enabled_modules,
                default_modules = tag.default_modules,
                custom_modules = tag.custom_modules,
                patches = tag.patches,
                patch_strip = tag.patch_strip,
                build_options = tag.build_options,
                build_name = tag.build_name,
                python = tag.python,
                configure_timeout = tag.configure_timeout,
                lock_file = tag.lock_file,
                engine = tag.engine,
            ))
            continue
        plan = prebuilt_plan(tag, _fail = _fail)
        if plan == None:
            return None
        for editor_platform, editor in plan.editors.items():
            declarations.append(_declaration(
                "godot_editor_archive",
                name = "%s_editor_%s" % (tag.name, editor_platform),
                urls = editor.urls,
                integrity = editor.integrity,
                binary = editor.binary,
                version = tag.version,
            ))
        declarations.append(_declaration(
            "godot_export_templates_archive",
            name = tag.name + "_templates",
            urls = plan.templates.urls,
            integrity = plan.templates.integrity,
            version = tag.version,
            macos_cpus = plan.templates.macos_cpus,
            linux_cpus = plan.templates.linux_cpus,
        ))
        android_runtimes = {}
        if plan.android_shell:
            declarations.append(_declaration(
                "http_file",
                name = tag.name + "_android_shell",
                urls = plan.android_shell.urls,
                integrity = plan.android_shell.integrity,
                downloaded_file_path = "shell.aar",
            ))
            android_runtimes["release"] = {"shell": "@%s_android_shell//file" % tag.name}
        if plan.android_debug_shell:
            declarations.append(_declaration(
                "http_file",
                name = tag.name + "_android_debug_shell",
                urls = plan.android_debug_shell.urls,
                integrity = plan.android_debug_shell.integrity,
                downloaded_file_path = "shell.aar",
            ))
            android_runtimes["debug"] = {"shell": "@%s_android_debug_shell//file" % tag.name}
        slots = prebuilt_slots(tag, plan)
        missing = missing_runtimes(tag, plan, slots)
        if missing:
            declarations.extend(missing.declarations)
            slots = slots + missing.slots
            android_runtimes = missing.android | android_runtimes
        declarations.append(_declaration(
            "engine_hub",
            name = tag.name,
            display_name = tag.name,
            components = json.encode(slots),
            android_runtimes = json.encode(android_runtimes),
            engine = tag.engine,
        ))
    return declarations

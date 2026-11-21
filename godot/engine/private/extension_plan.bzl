"""
The tag evaluation of the godot_engines module extension.

The planner takes the extension's modules and returns the repositories to declare; the
extension instantiates them. Errors go through `_fail`, so a Starlark unit test with mocked
modules collects them; the planner returns None after an error.
"""

load("//godot/engine/private:archives.bzl", "template_target")
load("//godot/engine/private:catalogue.bzl", "EDITOR_PLATFORMS", "RELEASES", "TEMPLATE_CPUS")
load("//godot/engine/private:hub.bzl", "component")
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
        A struct of editors, templates, the Android shells by variant and iOS simulator
        CPUs, or None after an error.
    """
    error = godot_version_error(tag.version)
    if error:
        return _fail(error)
    release = RELEASES.get(tag.version)
    editors = _editors(tag, release, _fail)
    if editors == None:
        return None
    templates = _templates(tag, release, _fail)
    if templates == None:
        return None
    error = _shell_error(tag)
    if error:
        return _fail(error)
    return struct(
        editors = editors,
        templates = templates,
        android_shells = _android_shells(tag, release),
        ios_simulator_cpus = tag.ios_simulator_cpus or (release["ios_simulator_cpus"] if release else []),
        android_cpus = (release or {}).get("android_cpus", TEMPLATE_CPUS["android"]),
    )

def _editors(tag, release, _fail):
    """Return the editor archives of a prebuilt tag by editor platform, or None after an error."""
    editor_platforms = sorted(tag.editor_urls) if tag.editor_urls else (release["editor_platforms"] if release else [])
    if not editor_platforms:
        return _fail((
            "Godot %s has no built-in pins; set editor_urls/editor_integrity/editor_binaries " +
            "and templates_urls/templates_integrity on godot_engines.prebuilt(name = %r)"
        ) % (tag.version, tag.name))
    editors = {}
    for editor_platform in editor_platforms:
        editor = _editor(tag, release, editor_platform, _fail)
        if editor == None:
            return None
        editors[editor_platform] = editor
    return editors

def _editor(tag, release, editor_platform, _fail):
    """Return the archive of one editor platform: pinned on the tag or catalogued; None after an error."""
    if editor_platform not in EDITOR_PLATFORMS:
        return _fail("godot_engines.prebuilt %r: unknown editor platform %r; expected one of %s" % (tag.name, editor_platform, sorted(EDITOR_PLATFORMS)))
    layout = EDITOR_PLATFORMS[editor_platform]
    if not tag.editor_urls:
        return struct(
            urls = _release_urls(release["tag"], layout.suffix + ".zip"),
            integrity = release[editor_platform],
            binary = layout.binary.format(tag = release["tag"]),
            layout = layout,
        )
    if editor_platform not in tag.editor_integrity:
        return _fail("godot_engines.prebuilt %r: editor_integrity lacks %r" % (tag.name, editor_platform))
    binary = tag.editor_binaries.get(editor_platform, layout.binary.format(tag = release["tag"]) if release else "")
    if not binary:
        return _fail("godot_engines.prebuilt %r: editor_binaries lacks %r" % (tag.name, editor_platform))
    return struct(
        urls = tag.editor_urls[editor_platform],
        integrity = tag.editor_integrity[editor_platform],
        binary = binary,
        layout = layout,
    )

def _templates(tag, release, _fail):
    """Return the export-template archive of a prebuilt tag and its layout, or None after an error."""
    if tag.templates_urls:
        return _pinned_templates(tag, _fail)
    layouts = [attribute for attribute in ["templates_macos_cpus", "templates_linux_cpus"] if getattr(tag, attribute)]
    if layouts:
        return _fail("godot_engines.prebuilt %r: %s describes templates_urls; set both" % (tag.name, layouts[0]))
    if release:
        return struct(
            urls = _release_urls(release["tag"], "export_templates.tpz"),
            integrity = release["templates"],
            macos_cpus = release["macos_cpus"],
            linux_cpus = release.get("linux_cpus", TEMPLATE_CPUS["linux"]),
        )
    return _fail("godot_engines.prebuilt %r: Godot %s needs templates_urls and templates_integrity" % (tag.name, tag.version))

def _pinned_templates(tag, _fail):
    """Return the export-template archive a tag pins with templates_urls, or None after an error."""
    if not tag.templates_integrity:
        return _fail("godot_engines.prebuilt %r: templates_integrity is required with templates_urls" % tag.name)
    return struct(
        urls = tag.templates_urls,
        integrity = tag.templates_integrity,
        macos_cpus = tag.templates_macos_cpus or ["universal"],
        linux_cpus = tag.templates_linux_cpus or TEMPLATE_CPUS["linux"],
    )

# The Android shell AARs of a prebuilt engine: the variant each serves and the prefix of
# its tag attributes, catalogue key and repository name. The shells of official releases
# are template_release builds with every ABI's engine library; a debug shell is an
# explicit pin.
_SHELL_PINS = [("release", "android_shell"), ("debug", "android_debug_shell")]

def _shell_error(tag):
    """The error of a shell AAR pinned without its integrity, or None."""
    for _, pin in _SHELL_PINS:
        if getattr(tag, pin + "_urls") and not getattr(tag, pin + "_integrity"):
            return "godot_engines.prebuilt %r: %s_integrity is required with %s_urls" % (tag.name, pin, pin)
    return None

def _android_shells(tag, release):
    """
    Return the shell AARs of a prebuilt tag by variant, in _SHELL_PINS order.

    Each is pinned on the tag with `<pin>_urls` and `<pin>_integrity` or catalogued under
    `<pin>`; a struct of its pin, urls and integrity.
    """
    shells = {}
    for variant, pin in _SHELL_PINS:
        urls = getattr(tag, pin + "_urls")
        if urls:
            shells[variant] = struct(pin = pin, urls = urls, integrity = getattr(tag, pin + "_integrity"))
        elif release and pin in release:
            shells[variant] = struct(pin = pin, **release[pin])
    return shells

def prebuilt_slots(tag, plan):
    """
    Return the hub slots of a prebuilt plan.

    Args:
        tag: The godot_engines.prebuilt tag of the plan.
        plan: The result of prebuilt_plan.

    Returns:
        A list of hub component descriptions.
    """
    return (
        _editor_slots(tag, plan.editors) +
        _desktop_runtime_slots(tag, plan.templates) +
        _ios_runtime_slots(tag, plan.templates, plan.ios_simulator_cpus) +
        _android_runtime_slots(tag, plan)
    )

def _editor_slots(tag, editors):
    return [
        component(
            role = "editor",
            name = "editor_%s_%s" % (editor.layout.platform, cpu),
            payload = "@%s_editor_%s//:editor" % (tag.name, editor_platform),
            platform = editor.layout.platform,
            cpu = cpu,
            version = tag.version,
        )
        for editor_platform, editor in editors.items()
        for cpu in editor.layout.cpus
    ]

def _runtime_slot(tag, platform, cpu, variant, payload, environment = "", digest = ""):
    """A runtime slot, named runtime_<platform>_<cpu>[_<environment>]_<variant>."""
    return component(
        role = "runtime",
        name = "_".join(["runtime", platform, cpu] + ([environment] if environment else []) + [variant]),
        payload = payload,
        platform = platform,
        cpu = cpu,
        version = tag.version,
        variant = variant,
        environment = environment,
        digest = digest,
    )

def _templates_repository(tag, platform):
    """The name of the repository of a Godot platform's export templates."""
    return "%s_templates_%s" % (tag.name, platform)

def _template_payload(tag, platform, target):
    """The label of a target in the export-template repository of a platform."""
    return "@%s//:%s" % (_templates_repository(tag, platform), target)

def _macos_target(macos_cpus, cpu, variant):
    """The macOS runtime target that serves a CPU, or None when the templates lack it."""
    if macos_cpus == ["universal"]:
        return template_target("macos", "universal", variant)
    return template_target("macos", cpu, variant) if cpu in macos_cpus else None

def _desktop_runtime_slots(tag, templates):
    slots = []
    for variant in ["release", "debug"]:
        targets = [("linux", cpu, template_target("linux", cpu, variant)) for cpu in templates.linux_cpus] + [
            ("macos", cpu, _macos_target(templates.macos_cpus, cpu, variant))
            for cpu in ["arm64", "x86_64"]
        ]
        slots.extend([
            _runtime_slot(tag, platform, cpu, variant, _template_payload(tag, platform, target))
            for platform, cpu, target in targets
            if target
        ])
    return slots

def _ios_runtime_slots(tag, templates, simulator_cpus):
    """The device slot and one simulator slot per CPU of each variant; one XCFramework serves them all."""
    return [
        _runtime_slot(
            tag,
            "ios",
            cpu,
            variant,
            _template_payload(tag, "ios", template_target("ios", "", variant)),
            environment = environment,
            digest = templates.integrity,
        )
        for variant in ["release", "debug"]
        for cpu, environment in [("arm64", "device")] + [(cpu, "simulator") for cpu in simulator_cpus]
    ]

def _android_runtime_slots(tag, plan):
    return [
        _runtime_slot(tag, "android", cpu, variant, "//android:" + variant, digest = shell.integrity)
        for variant, shell in plan.android_shells.items()
        for cpu in plan.android_cpus
    ]

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
    for request in _requests(modules, tag_attributes):
        requests.setdefault(request.tag.name, []).append(request)
    selected = []
    for name in sorted(requests):
        candidates = requests[name]
        effective = [candidate for candidate in candidates if candidate.is_root] or candidates
        first = effective[0]
        conflicts = [candidate for candidate in effective[1:] if candidate.signature != first.signature]
        if conflicts:
            return _fail((
                "Conflicting Godot requests named %r from %s and %s. " +
                "Pin one configuration with this name in the root module."
            ) % (name, first.module, conflicts[0].module))
        selected.append(first)
    return selected

def _requests(modules, tag_attributes):
    """Every tag of the three tag classes, which share one namespace of names, with its module."""
    return [
        struct(
            kind = kind,
            tag = tag,
            signature = _signature(kind, tag, tag_attributes[kind]),
            module = mod.name,
            is_root = mod.is_root,
        )
        for mod in modules
        for kind in ["prebuilt", "source", "source_build"]
        for tag in getattr(mod.tags, kind)
    ]

def _declaration(rule, **attrs):
    return struct(rule = rule, attrs = attrs)

# The file name of a downloaded export-template archive. The platform repositories
# extract the file itself, so they name it rather than the archive repository's //file
# target.
_ARCHIVE_FILE = "export_templates.tpz"

def _templates_declarations(tag, templates):
    """
    Return the export-template repositories of a prebuilt tag.

    One repository downloads the archive, and one per Godot platform extracts that
    platform's templates from it: a build extracts only the templates of the platforms it
    uses, and downloads the archive once however many it uses.

    Args:
        tag: The godot_engines.prebuilt tag.
        templates: The templates of the tag's prebuilt plan.

    Returns:
        The http_file declaration of the archive, then the godot_export_templates_archive
        declarations.
    """
    archive = _templates_repository(tag, "archive")
    return [_declaration(
        "http_file",
        name = archive,
        urls = templates.urls,
        integrity = templates.integrity,
        downloaded_file_path = _ARCHIVE_FILE,
    )] + [
        _declaration(
            "godot_export_templates_archive",
            name = _templates_repository(tag, platform),
            archive = "@%s//file:%s" % (archive, _ARCHIVE_FILE),
            integrity = templates.integrity,
            version = tag.version,
            platform = platform,
            cpus = cpus,
        )
        for platform, cpus in [("linux", templates.linux_cpus), ("macos", templates.macos_cpus), ("ios", [])]
    ]

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
        if selection.kind in _SOURCE_RULES:
            attrs = {attribute: getattr(tag, attribute) for attribute in tag_attributes[selection.kind]}
            declarations.append(_declaration(_SOURCE_RULES[selection.kind], **attrs))
            continue
        prebuilt = _prebuilt_declarations(tag, _fail)
        if prebuilt == None:
            return None
        declarations.extend(prebuilt)
    return declarations

# The repository rule that each source tag class declares.
_SOURCE_RULES = {
    "source": "godot_engine_source",
    "source_build": "godot_engine_source_build",
}

def _prebuilt_declarations(tag, _fail):
    """Return the editor, template, shell and hub repositories of a prebuilt tag, or None after an error."""
    plan = prebuilt_plan(tag, _fail = _fail)
    if plan == None:
        return None
    shells, android_runtimes = _shell_declarations(tag, plan.android_shells)
    hub = _declaration(
        "engine_hub",
        name = tag.name,
        display_name = tag.name,
        components = json.encode(prebuilt_slots(tag, plan)),
        android_runtimes = json.encode(android_runtimes),
        engine = tag.engine,
    )
    return _editor_declarations(tag, plan.editors) + _templates_declarations(tag, plan.templates) + shells + [hub]

def _editor_declarations(tag, editors):
    return [
        _declaration(
            "godot_editor_archive",
            name = "%s_editor_%s" % (tag.name, editor_platform),
            urls = editor.urls,
            integrity = editor.integrity,
            binary = editor.binary,
            version = tag.version,
        )
        for editor_platform, editor in editors.items()
    ]

def _shell_declarations(tag, shells):
    """
    Return the repositories of a prebuilt tag's shell AARs and the hub's Android runtimes.

    Args:
        tag: The godot_engines.prebuilt tag.
        shells: The shell AARs of the tag's prebuilt plan, by variant.

    Returns:
        A tuple of the http_file declarations and, by variant, the Android runtime of the
        hub: a dict whose `shell` is the label of the AAR.
    """
    declarations = []
    android_runtimes = {}
    for variant, shell in shells.items():
        name = "%s_%s" % (tag.name, shell.pin)
        declarations.append(_declaration(
            "http_file",
            name = name,
            urls = shell.urls,
            integrity = shell.integrity,
            downloaded_file_path = "shell.aar",
        ))
        android_runtimes[variant] = {"shell": "@%s//file" % name}
    return declarations, android_runtimes

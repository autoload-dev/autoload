"""
The engines the godot_engines extension registers: one configuration per name.

Each engine is one `engine` tag and the `source`, `binaries`, `build` and `editor` tags of
the same module that name it. Errors go through `_fail`, so a Starlark unit test with mocked
modules collects them; the functions return None after an error.
"""

visibility(["//godot/engine/private/..."])

# The tag classes that complete an engine, each at most once per engine.
_PARTS = ["source", "binaries", "build", "editor"]

def _scalar(value):
    return str(value) if type(value) == "Label" else value

def _plain(value):
    """A JSON-encodable form of a tag value; labels compare by their canonical form."""
    if type(value) == "list":
        return [_scalar(item) for item in value]
    if type(value) == "dict":
        return {str(key): _scalar(item) for key, item in value.items()}
    return _scalar(value)

def _signature(parts, tag_attributes):
    """The JSON of an engine's tags, which identical requests share."""
    return json.encode({
        kind: {attribute: _plain(getattr(tag, attribute)) for attribute in sorted(tag_attributes[kind])}
        for kind, tag in sorted(parts.items())
    })

def _is_identifier(name):
    """Whether a name has only letters, digits and underscores and starts with a letter."""
    return bool(name) and name[0].isalpha() and all([character.isalnum() or character == "_" for character in name.elems()])

def _registration_error(mod, engines, tag):
    """The error of an engine tag with an invalid or repeated name, or None."""
    if not _is_identifier(tag.name):
        return "godot_engines.engine name %r: use letters, digits and underscores, starting with a letter" % tag.name
    if tag.name in engines:
        return "%s registers the Godot engine %r twice" % (mod.name, tag.name)
    return None

def _part_error(mod, engines, kind, tag):
    """The error of a tag that completes no engine of its module, or one already complete; None otherwise."""
    parts = engines.get(tag.engine)
    if parts == None:
        return "godot_engines.%s(engine = %r) in %s names no engine that module registers" % (kind, tag.engine, mod.name)
    if kind in parts:
        return "%s declares godot_engines.%s twice for the engine %r" % (mod.name, kind, tag.engine)
    return None

def _registered_engines(mod, _fail):
    """Return the engine tags of a module by name, or None after an error."""
    engines = {}
    for tag in mod.tags.engine:
        error = _registration_error(mod, engines, tag)
        if error:
            return _fail(error)
        engines[tag.name] = {"engine": tag}
    return engines

def _completed_engines(mod, engines, _fail):
    """Add each part tag of a module to the engine it names; return None after an error."""
    for kind, tag in [(kind, tag) for kind in _PARTS for tag in getattr(mod.tags, kind)]:
        error = _part_error(mod, engines, kind, tag)
        if error:
            return _fail(error)
        engines[tag.engine][kind] = tag
    return engines

def _module_engines(mod, _fail):
    """Return the tags of each engine a module registers, by name, or None after an error."""
    engines = _registered_engines(mod, _fail)
    if engines == None:
        return None
    return _completed_engines(mod, engines, _fail)

def _requests(modules, tag_attributes, _fail):
    """Return each engine name's requests, one per module that registers it, or None after an error."""
    requests = {}
    for mod in modules:
        engines = _module_engines(mod, _fail)
        if engines == None:
            return None
        for name, parts in engines.items():
            requests.setdefault(name, []).append(struct(
                name = name,
                parts = parts,
                signature = _signature(parts, tag_attributes),
                module = mod.name,
                is_root = mod.is_root,
            ))
    return requests

def _settled(name, candidates, _fail):
    """
    Return the request that owns a name: the root module's, or the dependencies' identical one.

    Returns None after an error.
    """
    effective = [candidate for candidate in candidates if candidate.is_root] or candidates
    first = effective[0]
    conflicts = [candidate for candidate in effective[1:] if candidate.signature != first.signature]
    if conflicts:
        return _fail((
            "Conflicting Godot engines named %r from %s and %s. " +
            "Pin one configuration with this name in the root module."
        ) % (name, first.module, conflicts[0].module))
    return first

def _defaults(selected, _fail):
    """
    Return the names of the default engines, or None after an error.

    The root module's default engine wins; a dependency's default counts only when the root
    names none, such as the engine an add-on module registers for its own builds.
    """
    defaults = [selection for selection in selected if selection.parts["engine"].default]
    root = [selection.name for selection in defaults if selection.is_root]
    names = root or [selection.name for selection in defaults]
    if len(names) > 1:
        return _fail("More than one default Godot engine: %s; mark one with default = True" % ", ".join(names))
    return names

def selected_engines(modules, *, tag_attributes, _fail = fail):
    """
    Select one configuration per engine name.

    Each module completes only the engines it registers. Root requests own their names,
    identical dependency requests coalesce, and conflicting ones fail.

    Args:
        modules: module_ctx.modules.
        tag_attributes: The attribute names of each tag class, keyed by tag class.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        A list of structs with the engine's name, its tags by tag class as `parts`, its
        module, whether that is the root module, and whether it is the default engine,
        sorted by name; None after an error.
    """
    requests = _requests(modules, tag_attributes, _fail)
    if requests == None:
        return None
    selected = []
    for name in sorted(requests):
        selection = _settled(name, requests[name], _fail)
        if selection == None:
            return None
        selected.append(selection)
    defaults = _defaults(selected, _fail)
    if defaults == None:
        return None
    return [
        struct(
            name = selection.name,
            parts = selection.parts,
            module = selection.module,
            is_root = selection.is_root,
            default = selection.name in defaults,
        )
        for selection in selected
    ]

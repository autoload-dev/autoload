"""
Selecting an engine by name for one target and what it reaches.

An operation or application names its engine with `engine`; an incoming transition sets
`--@autoload_rules_godot//godot:engine` to it, so the editor and runtime components the
target and its dependencies resolve are that engine's. An empty name keeps the build's
engine: the default engine, or the one the flag names.
"""

visibility(["//godot/..."])

ENGINE = str(Label("//godot:engine"))

ENGINE_DOC = """
The engine this target uses, by the engine name its components declare, such as the
`engine` of a godot_engines tag. Empty keeps the build's engine: the default engine, or
the one --@autoload_rules_godot//godot:engine names.
"""

# The attribute of every rule that selects an engine with engine_transition.
ENGINE_ATTRS = {
    "engine": attr.string(doc = ENGINE_DOC),
}

def selected_engine(settings, attr):
    """The engine setting a target with an `engine` attribute selects; empty keeps the build's."""
    return {ENGINE: getattr(attr, "engine", "") or settings[ENGINE]}

engine_transition = transition(
    implementation = selected_engine,
    inputs = [ENGINE],
    outputs = [ENGINE],
)

def _engine_name(name):
    return "the engine " + name if name else "the default engine"

def require_pack_engine(label, pack, component, _fail = fail):
    """
    Fail when a pack runs or ships with another engine than the one whose editor exported it.

    Engines differ in their modules and patches: a pack whose scripts name a module's class
    parses only on an engine with that module, and Godot reports the failure only in its
    log, with exit status 0.

    Args:
        label: The target that runs or ships the pack, for the message.
        pack: GodotPackInfo of the pack, or None; a pack without an export, such as a text
            pack, is not compared.
        component: The provenance of the editor or runtime that runs or ships the pack.
        _fail: Replaces fail in Starlark unit tests.
    """
    exported = getattr(pack, "editor_component", None) if pack else None
    if not exported or exported.engine == component.engine:
        return
    _fail("%s: the pack was exported with the editor of %s, but this target's %s is %s's; give it engine = %r, as its pack has" % (
        label,
        _engine_name(exported.engine),
        component.role,
        _engine_name(component.engine),
        exported.engine,
    ))

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
    """The engine setting a target with an `engine` attribute selects."""
    return {ENGINE: attr.engine or settings[ENGINE]}

engine_transition = transition(
    implementation = selected_engine,
    inputs = [ENGINE],
    outputs = [ENGINE],
)

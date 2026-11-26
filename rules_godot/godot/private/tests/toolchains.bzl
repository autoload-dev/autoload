"""
How the ruleset's tests select an engine and its toolchains.

A test selects in one of three ways, each for one kind of subject:

- Registered toolchains: the default development engine `@godot` and the Android SDK and NDK
  toolchains, among others, are registered in MODULE.bazel.
  A test that needs only them selects nothing; an analysis test merges `own_toolchains()`
  so that the caller's extra toolchains and execution platforms do not change what it
  analyzes.
- A whole engine by name: another complete development engine, such as `@beta`, is
  registered under an engine name, and a test selects it with `--//godot:engine`, as a
  consumer selects a named engine. `DEVELOPMENT_ENGINES` lists them; the `engine` attribute
  of `configured_outputs` and of the compatibility tests' `engine_test` takes its keys.
- A registration set ahead of the registered engines: a fixture set of a few slots, a
  source-built hub that replaces slots of an engine, or a test whose subject is registration
  order or `--extra_toolchains` itself uses `--extra_toolchains`, the consumer's per-invocation
  override, whose last entry wins. `own_toolchains` replaces the caller's list for an
  analysis test; the `extra_toolchains` attribute of `configured_outputs` appends to it for a
  build-output test, so a remote execution config keeps its C++ toolchain. The difference
  comes from where each sets the option: an analysis test's `config_settings` can only
  overwrite it, while a transition can read the caller's list. Appending leaves the caller's
  execution platforms alone; `own_toolchains` sets them to the host.

A build setting such as `--//godot:engine` stays out of the exec configuration of the tools a
test analyzes; each distinct `--extra_toolchains` list gives them an exec configuration of
their own, so a whole engine is selected by name rather than by its hub.
"""

visibility([
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/config/tests/...",
    "//godot/private/tests/...",
])

_TOOLCHAINS = "//command_line_option:extra_toolchains"
_EXECUTION_PLATFORMS = "//command_line_option:extra_execution_platforms"

# The host as shared.bazelrc spells it. Options keep their spelling, and both survive the
# exec transition, so another spelling of the same platform would split the tools that the
# command line's own configuration builds into a second exec configuration.
_HOST = "@platforms//host"

# The build setting that names the engine a build uses; a transition lists it as an output.
ENGINE = str(Label("//godot:engine"))

# The root module's development engines, by the key tests name them with: the hub MODULE.bazel
# registers and the engine name that selects it, empty for the default engine. Selection uses
# the name only; `hub` serves the engine upgrade tests, which need its repository name.
DEVELOPMENT_ENGINES = {
    "beta": struct(hub = Label("@beta//toolchains:all"), name = "beta"),
    "stable": struct(hub = Label("@godot//toolchains:all"), name = ""),
}

def development_engine(engine):
    """
    Return the settings that select one of the development engines.

    Args:
        engine: A key of DEVELOPMENT_ENGINES, such as "beta".

    Returns:
        A dict of the engine build setting to the engine's name, for a transition's result
        or an analysis test's config_settings.
    """
    return {ENGINE: DEVELOPMENT_ENGINES[engine].name}

def own_toolchains(toolchains = [], execution_platforms = None):
    """
    Return config_settings that replace the caller's extra toolchains and execution platforms.

    Setting extra_toolchains replaces the command line's list, including the C++ toolchains
    of a remote execution platform such as BuildBuddy's, while that platform would stay an
    execution platform for the tools the test analyzes. The test therefore names its
    execution platforms too.

    Args:
        toolchains: Labels of the toolchains or registration sets the test registers ahead of
            the registered ones, the last with priority; empty for none.
            Strings resolve in rules_godot; another repository passes Label objects.
        execution_platforms: Labels of the execution platforms; by default the host, spelled
            as the command line names it, so the tools share its exec configuration.

    Returns:
        A dict to merge into an analysistest's config_settings.
    """
    return {
        _TOOLCHAINS: [str(Label(toolchain)) for toolchain in toolchains],
        _EXECUTION_PLATFORMS: [
            str(Label(platform))
            for platform in execution_platforms
        ] if execution_platforms else [_HOST],
    }

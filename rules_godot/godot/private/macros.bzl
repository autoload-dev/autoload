"""Helpers for macros that declare targets beside their main one."""

visibility("//godot/...")

# The notice that ends the documentation of public API that may still change, as rules_python
# marks its volatile API (rules_godot/docs/internal/api-reference.md). Its lines keep the
# indentation of the doc strings it ends.
VOLATILE_API = (
    "\n\n    Volatile API: public, but it may still change incompatibly in a release of" +
    "\n    rules_godot. A module that builds on it pins the rules_godot release it works with.\n"
)

_COMMON = ["tags", "testonly", "target_compatible_with", "exec_compatible_with"]

# The visibility of a macro's internal target that its caller's package may inspect, as the
# analysis tests of the calling package do, such as a run's view. A relative label resolves in
# the package of the target, which is the caller's, also for a symbolic macro's targets.
CALLER_PACKAGE = [":__pkg__"]

def common_kwargs(kwargs):
    """
    Return the attributes a macro's helper targets share with its main target.

    Args:
        kwargs: The macro's keyword arguments.

    Returns:
        The common attributes among kwargs.
    """
    return {key: kwargs[key] for key in _COMMON if key in kwargs}

def filegroup_kwargs(common):
    """
    Return common attributes a filegroup accepts; it has no execution platform.

    Args:
        common: Attributes from common_kwargs.

    Returns:
        The common attributes without exec_compatible_with.
    """
    return {key: value for key, value in common.items() if key != "exec_compatible_with"}

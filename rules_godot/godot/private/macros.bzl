"""Helpers for macros that declare targets beside their main one."""

visibility("//godot/...")

_COMMON = ["tags", "testonly", "target_compatible_with", "exec_compatible_with"]

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

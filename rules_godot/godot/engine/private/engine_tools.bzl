"""
How the engine's repository rules run the Python tools in //tools/engine.

A repository rule cannot build a py_binary, so it starts a tool's module with the host's
Python and puts the ruleset's root on PYTHONPATH, as rules_python does for its own
repository tools. The tools then import each other as tools.engine modules. Python's -P
keeps the repository's own directory off the path, so a tools package among the engine's
sources cannot take the place of the ruleset's.
"""

visibility("private")

_PACKAGE = "tools/engine/"

def engine_tool(ctx, tool):
    """
    Return how to start one engine tool: its command prefix and its environment.

    Args:
        ctx: Repository context with a _python attribute, the host's Python.
        tool: The tool's file, a label of //tools/engine such as ctx.attr._tree_link.

    Returns:
        A struct of command (the Python, its options and the tool's module) and environment
        (PYTHONPATH, the directory that holds tools/).
    """
    path = str(ctx.path(tool))
    name = path.rpartition("/")[2]

    # The directory that holds tools/engine/, never empty.
    root = path.removesuffix("/" + _PACKAGE + name)
    if not name.endswith(".py") or root in [path, ""]:
        fail("%s is no tool of %s" % (tool, _PACKAGE))
    return struct(
        command = [
            str(ctx.path(ctx.attr._python)),
            "-P",
            "-m",
            _PACKAGE.replace("/", ".") + name.removesuffix(".py"),
        ],
        environment = {"PYTHONPATH": root},
    )

"""
How the engine's repository rules run the Python tools in //tools/engine.

A repository rule cannot build a py_binary, so it starts a tool's module with the host's
Python and puts the ruleset's root on PYTHONPATH, as rules_python does for its own
repository tools. The tools then import each other as tools.engine modules.
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
        A struct of command (the Python, -m and the tool's module) and environment
        (PYTHONPATH, the directory that holds tools/).
    """
    path = str(ctx.path(tool))
    name = path.rpartition("/")[2]
    if not path.endswith(_PACKAGE + name) or not name.endswith(".py"):
        fail("%s is no tool of %s" % (tool, _PACKAGE))
    return struct(
        command = [
            str(ctx.path(ctx.attr._python)),
            "-m",
            _PACKAGE.replace("/", ".") + name.removesuffix(".py"),
        ],
        environment = {"PYTHONPATH": path.removesuffix(_PACKAGE + name).removesuffix("/")},
    )

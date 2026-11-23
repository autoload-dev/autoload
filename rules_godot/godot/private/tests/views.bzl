"""The view an operation declares over a project and the resources it names."""

load("//godot:defs.bzl", "godot_run")

visibility(["//godot/private/tests/..."])

def run_view(name, project, deps):
    """
    Declare a source run over project and deps and return the label of its view.

    A source run starts the game: an autoload or main scene the project names that deps
    lack fails the run's analysis, not its view's.

    Args:
        name: Name of the run; its view is `<name>.view`.
        project: The godot_project the run uses.
        deps: The resources the run contains.

    Returns:
        The label string of the run's view, relative to the package.
    """
    godot_run(name = name, project = project, tags = ["manual"], deps = deps)
    return name + ".view"

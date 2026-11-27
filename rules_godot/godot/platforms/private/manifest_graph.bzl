"""The dependency graph of Android libraries, for the manifest priority of a Gradle build."""

load("@rules_android//providers:providers.bzl", "StarlarkAndroidResourcesInfo")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")

visibility("//godot/...")

ManifestGraphInfo = provider(
    doc = "The Android libraries a platform library is or reaches, with their dependencies.",
    fields = {
        "libraries": """
        list of struct(label, nodes, dependencies), each library once: the target itself
        when it has Android resources, else the libraries it reaches first. nodes are the
        library's own resource nodes, dependencies the same structs of its dependencies.
        """,
    },
)

_EDGES = ["deps", "exports", "runtime_deps"]

def _reached_libraries(ctx):
    """The libraries the target's dependencies are or reach, each once, in the order reached."""
    reached = {}
    for library in [
        library
        for edge in _EDGES
        for dep in getattr(ctx.rule.attr, edge, [])
        if ManifestGraphInfo in dep
        for library in dep[ManifestGraphInfo].libraries
    ]:
        reached.setdefault(library.label, library)
    return reached.values()

def _manifest_graph_aspect_impl(target, ctx):
    # The Android runtime bridge forwards the graph of the runtime it resolves.
    if ManifestGraphInfo in target:
        return []
    reached = _reached_libraries(ctx)
    if StarlarkAndroidResourcesInfo not in target:
        return [ManifestGraphInfo(libraries = reached)]
    return [ManifestGraphInfo(libraries = [struct(
        label = target.label,
        nodes = [
            node
            for node in target[StarlarkAndroidResourcesInfo].direct_resources_nodes.to_list()
            if node.label == target.label
        ],
        dependencies = reached,
    )])]

manifest_graph_aspect = aspect(
    implementation = _manifest_graph_aspect_impl,
    attr_aspects = _EDGES,
    required_providers = [JavaInfo],
    doc = "Record the dependency graph of the Android libraries a platform library reaches.",
)

def _rank_level(level, ranked, nodes):
    """Rank the libraries of one level that are not ranked yet, and return their dependencies."""
    following = []
    for library in level:
        if library.label not in ranked:
            ranked[library.label] = True
            nodes.extend(library.nodes)
            following.extend(library.dependencies)
    return following

def ranked_resources_nodes(libraries):
    """
    The resource nodes of the libraries in the Android Gradle plugin's manifest priority.

    AGP ranks the libraries an application names, in their order, then their dependencies
    breadth-first, each library once.

    Args:
        libraries: The named platform libraries, in order.

    Returns:
        The resource nodes, highest priority first.
    """
    level = [
        library
        for target in libraries
        if ManifestGraphInfo in target
        for library in target[ManifestGraphInfo].libraries
    ]
    ranked = {}
    nodes = []

    # Starlark has no while loop; the bound exceeds the depth of any library graph.
    for _ in range(10000):
        if not level:
            break
        level = _rank_level(level, ranked, nodes)
    return nodes

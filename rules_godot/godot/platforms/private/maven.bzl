"""The Maven modules an Android application's Java closure resolves to."""

load("@rules_java//java/common:java_info.bzl", "JavaInfo")

visibility(["//godot/platforms/private/tests"])

MavenCoordinatesInfo = provider(
    doc = "The Maven coordinates of a target's Java closure.",
    fields = {
        "coordinates": "depset of group:artifact:version strings.",
    },
)

_TAG = "maven_coordinates="
_EDGES = ["deps", "exports", "runtime_deps"]

def _maven_coordinates_aspect_impl(target, ctx):
    # Native dependencies, such as an application's cc_library, carry no Maven modules.
    if JavaInfo not in target:
        return [MavenCoordinatesInfo(coordinates = depset())]

    # rules_jvm_external tags every target it generates for a Maven module with its
    # coordinates; a coordinate redirected with maven.override has no such tag.
    own = []
    for tag in getattr(ctx.rule.attr, "tags", []):
        if tag.startswith(_TAG):
            # group:artifact[:packaging[:classifier]]:version, the version suffixed with
            # @packaging for an AAR.
            parts = tag[len(_TAG):].split(":")
            version = parts[-1].split("@")[0]
            own.append("%s:%s:%s" % (parts[0], parts[1], version))
    transitive = []
    for edge in _EDGES:
        for dep in getattr(ctx.rule.attr, edge, []) or []:
            if type(dep) == "Target" and MavenCoordinatesInfo in dep:
                transitive.append(dep[MavenCoordinatesInfo].coordinates)
    return [MavenCoordinatesInfo(coordinates = depset(own, transitive = transitive))]

maven_coordinates_aspect = aspect(
    implementation = _maven_coordinates_aspect_impl,
    attr_aspects = _EDGES,
    doc = "Collect the maven_coordinates tags of the Java dependencies a target reaches.",
)

"""The CI lanes by name, which the lanes' work and the add-on modules share."""

LANES = ("quality", "desktop", "source-engine", "android", "ios")
# The variable that selects the Bazel profile of the root module's commands (tools/bazel).
PROFILE = "AUTOLOAD_BAZEL_PROFILE"
# The lanes whose work runs under a Bazel configuration of its own, each a profile: the
# mobile lanes' applications carry theirs (godot_configured_app).
PROFILE_LANES = ("source-engine",)


def profile(lane: str | None) -> str | None:
    """The profile of a lane's work; none for the desktop default."""
    return lane if lane in PROFILE_LANES else None

"""The CI lanes by name, which the lanes' work and the ruleset's API contract cases share."""

LANES = ("quality", "docs", "desktop", "source-engine", "android", "ios")
# The lanes that need a machine of their own, each with API contract cases: contracts:<lane>.
CONTRACT_LANES = ("desktop", "source-engine", "android", "ios")
# The variable that selects the Bazel profile of the root module's commands (tools/bazel).
PROFILE = "AUTOLOAD_BAZEL_PROFILE"
# The lanes whose work runs under a Bazel configuration of its own, each a profile: the
# mobile lanes' applications carry theirs (godot_configured_app).
PROFILE_LANES = ("source-engine",)
# The lanes whose API contract cases evaluate under the lane's Bazel configuration, each in
# a profile of that name.
CONTRACT_PROFILE_LANES = ("source-engine", "android", "ios")


def profile(lane: str | None) -> str | None:
    """The profile of a lane's work; none for the desktop default."""
    return lane if lane in PROFILE_LANES else None


def contract_profile(lane: str) -> str | None:
    """The profile in which a lane's API contract cases evaluate."""
    return lane if lane in CONTRACT_PROFILE_LANES else None

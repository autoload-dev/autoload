"""The CI lanes by name, which the lanes' work and the ruleset's API contract cases share."""

LANES = ("quality", "docs", "desktop", "source-engine", "android", "ios")
# The lanes that need a machine of their own, each with API contract cases: contracts:<lane>.
CONTRACT_LANES = ("desktop", "source-engine", "android", "ios")
# The variable that selects the Bazel profile of the root module's commands (tools/bazel).
PROFILE = "AUTOLOAD_BAZEL_PROFILE"
# The lanes whose Bazel configuration differs from the desktop default, each a profile.
PROFILE_LANES = ("source-engine", "android", "ios")


def profile(lane: str | None) -> str | None:
    """The profile of a lane's Bazel configuration; none for the desktop default."""
    return lane if lane in PROFILE_LANES else None

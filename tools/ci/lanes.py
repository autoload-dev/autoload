"""The CI lanes by name, which the lanes' work and the ruleset's API contract cases share."""

LANES = ("quality", "docs", "desktop", "source-engine", "android", "ios")
# The lanes that need a machine of their own, each with API contract cases: contracts:<lane>.
CONTRACT_LANES = ("desktop", "source-engine", "android", "ios")

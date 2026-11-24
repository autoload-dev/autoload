"""The gate that keeps Petri's targets out of builds with the prebuilt engine."""

# Petri's scripts name the reaction_diffusion module's class, so its checks, exports and
# tests need the source-built engine. --config=petri registers that engine and selects it;
# without it the targets are incompatible and //examples/... skips them.
SOURCE_ENGINE_ONLY = select({
    "//examples/projects/petri:with_source_engine": [],
    "//conditions:default": ["@platforms//:incompatible"],
})

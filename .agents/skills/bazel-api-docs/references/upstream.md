# Upstream practices and local decisions

Reviewed against primary sources on 2026-10-24. Recheck their current contents
when changing tooling or attributing additional behavior to upstream. These
projects demonstrate practices; they do not prescribe one universal CI policy.

| Source | Observed practice | Application here |
| --- | --- | --- |
| [Bazel .bzl style guide](https://bazel.build/rules/bzl-style#docstring) | Module/public-function docstrings; `doc` for rules/aspects/attributes and providers/fields | Follow Bazel's documentation conventions in Starlark |
| [Bazel load visibility](https://bazel.build/concepts/visibility#load-visibility) | `visibility()` restricts Starlark loads independently of BUILD source visibility | Restrict private implementation loads; generated-repository contracts may need external access |
| [Stardoc writing guide](https://github.com/bazelbuild/stardoc/blob/master/docs/writing_stardoc.md) | Rule/attribute docs, provider field dictionaries, function/macro `Args:` | Keep descriptions beside definitions and generate signatures/tables |
| [Stardoc generation guide](https://github.com/bazelbuild/stardoc/blob/master/docs/generating_stardoc.md) | Declared Starlark dependencies via `bzl_library`; re-export hubs | Generate from real load entrypoints and their complete dependency graph |
| [rules_rust docs BUILD](https://github.com/bazelbuild/rules_rust/blob/main/docs/BUILD.bazel) | Stardoc targets for rule, provider, toolchain and Bzlmod reference pages | Cover APIs beyond ordinary build rules |
| [rules_python docs BUILD](https://github.com/bazel-contrib/rules_python/blob/main/docs/BUILD.bazel) | Sphinx/Stardoc API source inventory and a docs `build_test` | Build the reference in CI; preserve setup and conceptual guides separately |
| [bazel-skylib docs BUILD](https://github.com/bazelbuild/bazel-skylib/blob/main/docs/BUILD) and [its private helper](https://github.com/bazelbuild/bazel-skylib/blob/main/docs/private/stardoc_with_diff_test.bzl) | Generate committed Markdown, compare with `diff_test`, provide an updater | Not followed: the registry renders the documentation, so the repository commits none |
| [rules-template release script](https://github.com/bazel-contrib/rules-template/blob/main/.github/workflows/release_prep.sh) and [bazel-lib's](https://github.com/bazel-contrib/bazel-lib/blob/main/.github/workflows/release_prep.sh) | No committed reference; the release attaches `starlark_doc_extract` metadata that `docs_url` names and the registry renders | Publish the API documentation only through the registry |
| [Buildifier warnings](https://github.com/bazelbuild/buildtools/blob/main/WARNINGS.md#function-docstring) | Documentation lint; public functions below five statements can escape mandatory-docstring checks | Add coverage for short public functions and their parameters |
| [Bazel 9.3.0 starlark_doc_extract](https://bazel.build/versions/9.3.0/reference/be/general#starlark_doc_extract) | Evaluated metadata, binary/text Protobuf outputs, public exports/namespaces; generated output may vary by Bazel version | Inspect evaluated metadata using Stardoc's schema; pin Bazel for golden diffs |

The following are deliberate **rules_godot requirements**, rather than claims
about universal upstream enforcement:

- Complete public-module discovery independent of the handwritten inventory.
- Unfiltered export inventories for coverage; explicit primary symbol selection
  only for the registry's metadata, checked against the complete evaluated surface.
- Exactly one public load path and contract per evaluated symbol identity.
  Generated-repository helpers are implementation details excluded from the
  BCR metadata, even though they need public load
  visibility. Other private implementation modules restrict load visibility.
- Update all repository consumers directly when moving an unpublished API;
  do not retain previous entrypoints.
- Curated public primary metadata for the BCR docs archive;
  implementation helpers and duplicate re-exports are excluded from that artifact.
- Descriptions for every public API, parameter, attribute, provider field and
  extension tag; include short functions and shared/overridden attributes.
- Review semantic correctness and examples separately from automated presence
  checks.

The registry's rendering of the release's metadata is the ruleset's API documentation;
the repository commits no reference pages, so nothing generated can go stale.

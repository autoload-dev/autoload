# Releasing

A release is a version tag. Pushing a tag `vX.Y.Z` runs
[release.yaml](../../.github/workflows/release.yaml), which:

1. **Release:** bazel-contrib's
   [release_ruleset](https://github.com/bazel-contrib/.github/blob/master/.github/workflows/release_ruleset.yaml)
   workflow tests the [registry test module](../../e2e/smoke), runs
   [release_prep.sh](../../.github/workflows/release_prep.sh) to build
   `rules_godot-vX.Y.Z.tar.gz` with `git archive` and the API documentation archive
   `rules_godot-vX.Y.Z.docs.tar.gz`, attests them and opens a draft GitHub release with
   both archives and the `bazel_dep` snippet. The documentation archive holds the curated
   Stardoc metadata of `//docs/public/api:bcr_docs` ([API reference
   maintenance](api-reference.md#metadata-for-the-bcr-documentation-archive)); the
   registry renders it from the `docs_url` of the registry entry.
2. **Publish:** [publish.yaml](../../.github/workflows/publish.yaml) runs
   [Publish to BCR](https://github.com/bazel-contrib/publish-to-bcr). It fills the
   templates in [.bcr](../../.bcr) and opens a draft pull request against the
   [Bazel Central Registry](https://github.com/bazelbuild/bazel-central-registry) from the
   `autoload-dev/bazel-central-registry` fork.
3. **Finalize:** the draft GitHub release is published.

Publish to BCR sets the registry entry's `version` from the tag, so `module(version = ...)`
in [MODULE.bazel](../../MODULE.bazel) needs no bump for the registry. Bump it anyway, so that
local and override builds report the released version.

## Cutting a release

```sh
git switch main && git pull
git tag v0.2.0
git push origin v0.2.0
```

Then open the registry pull request, check the presubmit and click **Ready for review**:
the registry counts the module maintainer's ready-for-review as approval, since an author
cannot approve their own pull request. A failed publish can be retried from the Actions tab
with the **Publish to BCR** workflow and the tag.

## What the archive contains

[.gitattributes](../../.gitattributes) keeps development-only directories out of the
archive: `examples/`, `tests/`, `.github/` and the agent tool directories.
`e2e/` stays in, because the registry's presubmit builds `e2e/smoke` from the archive.

The registry runs the test module on Linux and macOS with Bazel 9
([presubmit.yml](../../.bcr/presubmit.yml)). A first submission and any later change to
`presubmit.yml` beyond platforms and Bazel versions wait for a registry maintainer to start
the presubmit.

## One-time setup

- The repository is public: the registry downloads the release archive.
- `autoload-dev/bazel-central-registry` is a fork of `bazelbuild/bazel-central-registry`.
- The repository or organization secret `BCR_PUBLISH_TOKEN` holds a classic personal access
  token with the `repo` and `workflow` scopes, of an account that can push to the fork.
  Fine-grained tokens cannot open pull requests against the registry.

# Releasing

Each Bazel module of this repository is released on its own: the ruleset
`autoload_rules_godot` in [`rules_godot/`](../../rules_godot) and the add-on modules in
[`addons/`](../../addons). A release is a tag `autoload_<module>-vX.Y.Z`, such as
`autoload_rules_godot-v0.2.0` or `autoload_firebase-v0.1.0`: the module's name from its
`MODULE.bazel`, `-v` and the version. The release workflow runs for every tag that matches
`*-v*.*.*`.
[release_module.py](../../tools/ci/release_module.py) derives the rest from the tag: the
module's directory, from the module that declares the name; its release test, the registry
test module for the ruleset and `python3 -m tools.addons.lanes desktop <module>` for an add-on;
and whether the Bazel Central Registry gets it, which its templates in [.bcr](../../.bcr)
decide. No list names the modules. Pushing a tag runs
[release.yaml](../../.github/workflows/release.yaml), which:

1. **Release:** bazel-contrib's
   [release_ruleset](https://github.com/bazel-contrib/.github/blob/master/.github/workflows/release_ruleset.yaml)
   workflow runs the module's release test: its registry test module in `bcr/`, such as
   the ruleset's [bcr/smoke](../../rules_godot/bcr/smoke), run inside the module's release
   archive as the registry runs it (`python3 -m tools.ci.release_archive <module directory>`,
   or `aspect work release:archives` for every module); then it runs
   [release_prep.sh](../../.github/workflows/release_prep.sh) to build
   `<module>-X.Y.Z.tar.gz` with `git archive` of the module's directory and, for the
   ruleset, the API documentation archive `autoload_rules_godot-X.Y.Z.docs.tar.gz`, attests
   them and opens a draft GitHub release with the archives and the `bazel_dep` snippet. The
   documentation archive holds the curated Stardoc metadata of `//godot/tests/api:bcr_docs`,
   which the ruleset's own module builds ([API documentation
   maintenance](../../rules_godot/docs/internal/api-reference.md#metadata-for-the-bcr-documentation-archive));
   the registry renders it from the `docs_url` of the registry entry.
2. **Publish**, for a module with templates in `.bcr` (every module has them):
   [publish.yaml](../../.github/workflows/publish.yaml) runs
   [Publish to BCR](https://github.com/bazel-contrib/publish-to-bcr) for the tag's module
   alone (`module_roots`, `tag_prefix`). It fills the module's templates in
   [.bcr](../../.bcr) (`.bcr/<directory>/` for an add-on) and opens a draft pull request against the
   [Bazel Central Registry](https://github.com/bazelbuild/bazel-central-registry) from the
   `autoload-dev/bazel-central-registry` fork.
3. **Finalize:** the draft GitHub release is published.

Publish to BCR sets the registry entry's `version` from the tag, so `module(version = ...)`
in the module's `MODULE.bazel` needs no bump for the registry. Bump it anyway, so that
local and override builds report the released version.

## Cutting a release

```sh
git switch main && git pull
git tag autoload_rules_godot-v0.2.0
git push origin autoload_rules_godot-v0.2.0
```

Then open the registry pull request, check the presubmit and click **Ready for review**:
the registry counts the module maintainer's ready-for-review as approval, since an author
cannot approve their own pull request. A failed publish can be retried from the Actions tab
with the **Publish to BCR** workflow and the tag.

An add-on module states the ruleset release it needs in its `bazel_dep`; release the ruleset
first when an add-on needs rules that are not released yet.

## What the archive contains

Every archive holds its module's directory at its root, under `<module>-X.Y.Z/`, with the
repository's `LICENSE`. Each module's `.gitattributes` leaves every `tests/` directory out
of it (RG023); the ruleset's also leaves out its guides in `docs/` and the link to the
repository's Bazelisk wrapper. `bcr/` stays in, because the registry's presubmit builds the
module's registry test module, `bcr/<name>/`, from the archive (RG020). Each test module is
a consumer of its module with a flat project, which registers the official engine itself;
the add-on modules register none for consumers.

An add-on module's registry templates in `.bcr/addons/<module>/` are written once with the
module by `bazel run //tools/addons:new --` and checked by the conventions (RG015), so a module is ready to
publish from its first commit; it is published when its tag is pushed. `.bcr/config.yml`
lists only the ruleset: every release names its module root itself (`publish.yaml`).

The registry runs the test module on Linux and macOS with Bazel 9
([presubmit.yml](../../.bcr/rules_godot/presubmit.yml)). A first submission and any later change to
`presubmit.yml` beyond platforms and Bazel versions wait for a registry maintainer to start
the presubmit.

## One-time setup

- The repository is public: the registry downloads the release archive.
- `autoload-dev/bazel-central-registry` is a fork of `bazelbuild/bazel-central-registry`.
- The repository or organization secret `BCR_PUBLISH_TOKEN` holds a classic personal access
  token with the `repo` and `workflow` scopes, of an account that can push to the fork.
  Fine-grained tokens cannot open pull requests against the registry.

## Supporting a Godot release

A compatible release in the [version range](../../rules_godot/docs/public/versions.md) needs
no change. When a release needs
special handling, scope it to the affected feature or version range, not to one branch per
patch release. A digest update is an acquisition change. An API-baseline update is a separate
change with its own native rebuild cost.

The beta source probes in [`rules_godot/MODULE.bazel`](../../rules_godot/MODULE.bazel) enable
`freetype` explicitly: `text_server_fb` of Godot 4.8 beta 1 does not compile without it. The
rules keep optional module dependencies optional, so the probe declares the module.

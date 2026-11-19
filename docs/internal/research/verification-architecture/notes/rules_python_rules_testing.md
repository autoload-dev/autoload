# rules_python test layout, rules_testing and bazel_skylib unittest/analysistest

Sources were read from fresh shallow clones (2026-11-06): rules_python `26b0a238` (2026-11-05),
rules_testing `6239891e` (2026-09-08), bazel-skylib `a920cdfe` (2026-11-02). File paths below are
repo-relative; URLs point at `main`.

## Key question 1: rules_python layout — what is under `tests/`, `python/private/`, `examples/`; which are separate modules; how CI runs them

### Takeaway
rules_python keeps every test outside the shipped `python/` tree: `tests/` holds ~60 topic
directories of in-repo (same-module) Bazel tests, `tests/integration/` holds bazel-in-bazel
child modules driven by `rules_bazel_integration_test`, and `examples/` holds user-facing
child modules that CI builds with `working_directory` and BCR presubmit uses as the test
module. Nothing under `python/private/` is a test; implementation and tests are strictly
separated.

### Cited Findings
- `tests/` contains 60+ subject-oriented directories, e.g. `api`, `base_rules`, `bootstrap_impls`,
  `builders`, `cc`, `config_settings`, `exec_toolchain_matching`, `integration`, `modules`,
  `packaging`, `py_runtime`, `py_wheel`, `pypi`, `support`, `toolchains`, `uv`, `version`,
  `whl_filegroup`, plus a root `tests/BUILD.bazel` and `tests/default_info_subject.bzl` —
  [rules_python tests/](https://github.com/bazel-contrib/rules_python/tree/main/tests)
- 186 `BUILD*` files under `tests/` (one package per test suite) — count from the clone of
  [rules_python tests/](https://github.com/bazel-contrib/rules_python/tree/main/tests)
- `tests/BUILD.bazel` (root of tests) only declares a `build_test` named `bzl_libraries_build_test`
  over the public `bzl_library` targets (`//python:py_binary_bzl`, `//python:defs_bzl`, ...), with
  `package(default_visibility = ["//visibility:public"])` —
  [tests/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/tests/BUILD.bazel)
- Dev guide: "Tests go under `tests/`. They are loosely organized into directories for the
  particular subsystem or functionality they are testing. If an existing directory doesn't seem
  like a good match ... it's fine to create a new directory." —
  [docs/devguide.md](https://github.com/bazel-contrib/rules_python/blob/main/docs/devguide.md)
- Under `python/` there are no test files; the only `*test*` paths are the shipped rules
  themselves (`python/py_test.bzl`, `python/private/py_test_rule.bzl`, `python/private/py_test_macro.bzl`,
  `python/private/pytest_test/`, `python/zipapp/py_zipapp_test.bzl`) — find over
  [rules_python python/](https://github.com/bazel-contrib/rules_python/tree/main/python)
- `python/private/BUILD.bazel` uses `package(default_visibility = ["//:__subpackages__"])`, so
  private targets are visible to `tests/` (same module) but not to consumers; `python/BUILD.bazel`
  uses `default_visibility = ["//visibility:public"]` —
  [python/private/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/python/private/BUILD.bazel),
  [python/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/python/BUILD.bazel)
- The release tarball target `//:distribution` lists `//python:distribution`, `//tools:distribution`,
  `//crates:distribution`, `//command_line_option:distribution` and root files — not `tests/` or
  `examples/` — [BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/BUILD.bazel)
- Separate Bazel modules (own `MODULE.bazel`): `examples/bzlmod`, `examples/bzlmod/other_module`,
  `examples/multi_python_versions`, `examples/pip_parse`; `tests/integration/{bzlmod_lockfile,
  compile_pip_requirements, compile_pip_requirements_test_from_external_repo, custom_commands,
  local_toolchains, pip_parse, pip_parse_isolated, prebuilt_toolchain, py_cc_toolchain_registered,
  runtime_manifests, toolchain_target_settings, unified_pypi, uv_lock, validate_test_main,
  whl_library}`; and `tests/modules/{another_module, other}` — find in
  [rules_python](https://github.com/bazel-contrib/rules_python/tree/main)
- `examples/bzlmod/MODULE.bazel` depends on rules_python via `bazel_dep(name = "rules_python",
  version = "0.0.0")` + `local_path_override(module_name = "rules_python", path = "../..")`;
  `tests/integration/pip_parse/MODULE.bazel` does the same with `path = "../../.."` —
  [examples/bzlmod/MODULE.bazel](https://github.com/bazel-contrib/rules_python/blob/main/examples/bzlmod/MODULE.bazel),
  [tests/integration/pip_parse/MODULE.bazel](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/pip_parse/MODULE.bazel)
- `tests/modules/other` and `tests/modules/another_module` are *not* child workspaces run
  separately; they are dev-only modules pulled into the main module via `bazel_dep(name = "other",
  version = "0", dev_dependency = True)` (and a `local_path_override`) so in-repo tests can exercise
  cross-module behaviour (e.g. the `explicit_init_py` config extension "when used by a module that's
  a dependency") — [MODULE.bazel](https://github.com/bazel-contrib/rules_python/blob/main/MODULE.bazel),
  [tests/modules/other/MODULE.bazel](https://github.com/bazel-contrib/rules_python/blob/main/tests/modules/other/MODULE.bazel)
- `examples/BUILD.bazel` is a real package in the parent module (it hosts `lock(...)` targets that
  regenerate `examples/bzlmod/uv.lock`), while the child module directories are hidden from the
  parent through `.bazelrc.deleted_packages` ("Generated via './tools/update_deleted_packages.sh'",
  `common --deleted_packages=examples/bzlmod`, ...) and `.bazelignore` entries for every
  `bazel-<name>` convenience symlink ("Any directory with a WORKSPACE in it should be added here") —
  [examples/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/examples/BUILD.bazel),
  [.bazelrc.deleted_packages](https://github.com/bazel-contrib/rules_python/blob/main/.bazelrc.deleted_packages),
  [.bazelignore](https://github.com/bazel-contrib/rules_python/blob/main/.bazelignore)
- `tests/integration/README.md`: "The tests in this directory are Bazel-in-Bazel integration tests.
  These are necessary because our CI has a limit of 80 jobs, and our test matrix uses most of those
  for more important end-to-end tests of user-facing examples. The tests in here are more for
  testing internal aspects of the rules that aren't easily tested as tests run by Bazel itself
  (basically anything that happens prior to the analysis phase)." Adding a directory requires:
  add to `--deleted_packages` (pre-commit does it), add `bazel-<name>` to `.bazelignore`, add a
  `rules_python_integration_test` target —
  [tests/integration/README.md](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/README.md)
- `tests/integration/BUILD.bazel` loads `default_test_runner` from
  `@rules_bazel_integration_test//bazel_integration_test:defs.bzl`, defines a bzlmod `test_runner`
  and a `workspace_test_runner` (`--noenable_bzlmod --enable_workspace`), and declares ~20
  `rules_python_integration_test(...)` targets (bzlmod and `bzlmod = False` workspace variants,
  some with a Python `py_main` runner, `bazel_versions = ["7.7.0", "8.5.1"]` for workspace-only
  cases because "Bazel 9 ignores WORKSPACE files") plus a `test_suite(name = "subset", tags =
  ["manual"])` —
  [tests/integration/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/BUILD.bazel)
- `tests/integration/integration_test.bzl` wraps `bazel_integration_test` per Bazel version from
  `@bazel_binaries//:defs.bzl` (`bazel_binaries.versions.all`), caps
  `integration_test_utils.glob_workspace_files` at 1000 files (guard against following `bazel-*`
  symlinks), adds `//:distribution` to `workspace_files`, sets `size = "enormous"` and tags
  `exclusive`, `no-sandbox`, `no-remote-exec`, `integration-test` ("A special tag is used so CI can
  run them as a separate job"); Python runners are `py_test` targets tagged `manual` that get
  `BIT_WORKSPACE_DIR`/`BIT_BAZEL_BINARY` from the harness (`runner.py` `TestCase.setUp`) —
  [tests/integration/integration_test.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/integration_test.bzl),
  [tests/integration/runner.py](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/runner.py)
- `MODULE.bazel` dev-only section: `bazel_dep(name = "rules_bazel_integration_test", version =
  "0.27.0", dev_dependency = True)`, `bazel_dep(name = "rules_testing", version = "0.6.0",
  dev_dependency = True)`, `rules_shell`, `rules_multirun`, `bazel_ci_rules`, `rules_pkg`, plus a
  `bazel_binaries` extension with `dev_dependency = True` ("Keep in sync with //:version.bzl") —
  [MODULE.bazel](https://github.com/bazel-contrib/rules_python/blob/main/MODULE.bazel)
- CI (`.bazelci/presubmit.yml`): the default jobs build/test `...` with
  `--build_tag_filters=-integration-test` / `--test_tag_filters=-integration-test` across
  `ubuntu2204`, `debian11`, `macos_arm64`, `windows` × Bazel `7.x, 8.x, 9.x`; separate
  `integration_test_bazelinbazel_*` jobs invert the filter (`--test_tag_filters=integration-test
  --jobs=2 --local_test_jobs=2`, "only a few can be run concurrently"), with macOS/Windows limited
  to `//tests/integration:subset` "to save CI jobs slots"; each example gets its own job via
  `working_directory: examples/<name>` with `build_targets/test_targets: ["..."]`; a `bcr_test` job
  runs `working_directory: examples/bzlmod` and is marked "Keep in sync with .bcr/presubmit.yml" —
  [.bazelci/presubmit.yml](https://github.com/bazel-contrib/rules_python/blob/main/.bazelci/presubmit.yml)
- `.bcr/presubmit.yml` declares `bcr_test_module: module_path: "examples/bzlmod"` with a
  platform × Bazel matrix and `build_targets/test_targets: //...` — the example module doubles as
  the BCR smoke test — [.bcr/presubmit.yml](https://github.com/bazel-contrib/rules_python/blob/main/.bcr/presubmit.yml)
- Legacy/WORKSPACE flag: CI still runs `*_workspace` jobs with `--noenable_bzlmod --enable_workspace`
  pinned to `bazel: 7.x` and `skip_in_bazel_downstream_pipeline: "Bazel 9 doesn't support
  workspace"`; the dev guide notes `WORKSPACE.bzlmod` is kept "because it is impossible to have
  dev-only local overrides" — [.bazelci/presubmit.yml](https://github.com/bazel-contrib/rules_python/blob/main/.bazelci/presubmit.yml),
  [MODULE.bazel](https://github.com/bazel-contrib/rules_python/blob/main/MODULE.bazel)
- Dev guide on integration tests: "An integration test is one that runs a separate Bazel instance
  inside the test. These tests are discouraged unless absolutely necessary because they are slow,
  require a lot of memory and CPU, and are generally harder to debug. Integration tests are reserved
  for things that simply can't be tested otherwise, or for simple high-level verification tests.
  Integration tests live in `tests/integration`. When possible, add to an existing integration
  test." — [docs/devguide.md](https://github.com/bazel-contrib/rules_python/blob/main/docs/devguide.md)

### Inferences
- Three tiers map to three mechanisms: same-module tests (fast, `bazel test //...`), child modules
  under `tests/integration` (bazel-in-bazel, tagged out of `//...`), and child modules under
  `examples/` (run by CI `working_directory`, never by the parent Bazel). The parent build never
  sees child-module files except through `glob_workspace_files` + `deleted_packages`.
- `tests/modules/*` is a fourth, cheaper pattern for "another module consumes my rules": a
  dev-dependency module included via `local_path_override`, so cross-module tests run in the
  normal in-repo `bazel test` without a bazel subprocess.

### Gaps
- No maintainer document explains why `examples/` are separate modules beyond the CI job-limit
  rationale in `tests/integration/README.md`; the examples themselves carry no README stating it.

## Key question 2: what is in `tests/support`, its visibility, and whether rules_python exposes a public testing package

### Takeaway
`tests/support` is a private, same-module toolbox (truth subjects for rules_python providers,
fake toolchains, mocks for repository/module ctx, a config-transition test rule and an sh+py
runner); its visibility is `//:__subpackages__` and it is not in the distribution. rules_python
exposes no public `//python/testing`-style package.

### Cited Findings
- Contents of `tests/support/`: `BUILD.bazel`, `support.bzl`, `sh_py_run_test.bzl`,
  `py_reconfig.bzl`, `copy_file.bzl`, `explicit_init_py_test.bzl`, truth subjects
  `cc_info_subject.bzl`, `py_cc_toolchain_info_subject.bzl`, `py_executable_info_subject.bzl`,
  `py_info_subject.bzl`, `py_runtime_info_subject.bzl`, and subpackages `cc_toolchains/`
  (`fake_cc_toolchain_config.bzl`, fake headers), `empty_toolchain/`, `mocks/`
  (`mocks.bzl`, `mocks_tests.bzl`, `python_ext.bzl`), `platforms/`, `py_toolchains/`, `pyrefly/`,
  `whl_from_dir/` — [tests/support/](https://github.com/bazel-contrib/rules_python/tree/main/tests/support)
- `tests/support/BUILD.bazel`: `package(default_visibility = ["//:__subpackages__"])`, declares a
  `current_build_settings` target, a `string_flag` `custom_runtime` and matching `config_setting`s —
  [tests/support/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/BUILD.bazel)
- `tests/support/cc_toolchains/BUILD.bazel` also uses `package(default_visibility =
  ["//:__subpackages__"])`; `tests/support/py_toolchains/BUILD` has no `package()` statement
  (default private) and defines fake `py_runtime(interpreter_path = "/fake/python3.9",
  implementation_name = "fakepy")`, `py_runtime_pair`, `toolchain(... toolchain_type =
  "//python:toolchain_type")` and an `exec_toolchain` using `//python/private:py_exec_tools_toolchain.bzl` —
  [tests/support/py_toolchains/BUILD](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/py_toolchains/BUILD),
  [tests/support/cc_toolchains/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/cc_toolchains/BUILD.bazel)
- `support.bzl` exports label constants for the fake toolchains (`PY_TOOLCHAINS =
  str(Label("//tests/support/py_toolchains:all"))`, `CC_TOOLCHAIN`, `CROSSTOOL_TOP`,
  `CUSTOM_RUNTIME`) and compatibility selects (`SUPPORTS_BOOTSTRAP_SCRIPT`, `SUPPORTS_BZLMOD`,
  `NOT_WINDOWS`, `BAZEL_8_OR_LATER`); comment: "Explicit Label() calls are required so that it
  resolves in @rules_python context instead of e.g. the @rules_testing context" and "str() around
  Label() is necessary because rules_testing's config_settings doesn't accept yet Label objects" —
  [tests/support/support.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/support.bzl)
- `sh_py_run_test.bzl`: "Run a py_binary with altered config settings in an sh_test. This
  facilitates verify running binaries with different configuration settings without the overhead
  of a bazel-in-bazel integration test."; it composes `@rules_shell//shell:sh_test.bzl` with a
  `py_reconfig_binary` — [tests/support/sh_py_run_test.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/sh_py_run_test.bzl)
- `py_reconfig.bzl` builds `py_reconfig_test`/`py_reconfig_binary` from the private rule
  builders (`//python/private:py_binary_rule.bzl` `create_py_binary_rule_builder`, etc.) with an
  outgoing transition that sets rules_python flags from attributes; dev guide: "Add an attribute to
  the rule. It should have the same name as the flag it's for ... Modify the transition and add the
  flag to both the inputs and outputs list" — [tests/support/py_reconfig.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/py_reconfig.bzl),
  [docs/devguide.md](https://github.com/bazel-contrib/rules_python/blob/main/docs/devguide.md)
- Usage counts in `tests/` BUILD files: `py_reconfig_test` in 10, `sh_py_run_test` in 2 — grep over
  the clone of [tests/](https://github.com/bazel-contrib/rules_python/tree/main/tests)
- `tests/support/mocks/mocks.bzl`: "Mocks for repository_ctx, module_ctx, and File objects" (struct
  based `mocks.path`, `mocks.file`, ...), used by 14 test files, e.g. the pure-Starlark
  `tests/pypi/parse_requirements` unit tests that build a `_mock_ctx()` with in-memory requirement
  files — [tests/support/mocks/mocks.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/mocks/mocks.bzl),
  [tests/pypi/parse_requirements/parse_requirements_tests.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/pypi/parse_requirements/parse_requirements_tests.bzl)
- Provider subjects follow rules_testing's `subjects` style: e.g. `py_info_subject(info, *, meta)`
  returns a struct of lambdas (`direct_pyc_files`, `imports`, `transitive_sources`, ...) each
  returning `subjects.depset_file(..., meta = self.meta.derive("..."))` —
  [tests/support/py_info_subject.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/py_info_subject.bzl)
- Dev guide: "Re-usable test helpers and support code go in `tests/support`. Tests don't need to
  be perfectly factored and not every common thing a test does needs to be factored into a more
  generally reusable piece. Copying and pasting is fine." —
  [docs/devguide.md](https://github.com/bazel-contrib/rules_python/blob/main/docs/devguide.md)
- `whl_from_dir_repo` (in `tests/support/whl_from_dir`) "takes a directory tree and turns it into
  a `.whl` file" because "Checking in binary artifacts is not allowed ... This is true even in
  test contexts" — [docs/devguide.md](https://github.com/bazel-contrib/rules_python/blob/main/docs/devguide.md),
  [CONTRIBUTING.md](https://github.com/bazel-contrib/rules_python/blob/main/CONTRIBUTING.md)
- No directory named `testing` or `test_support` exists under `python/`, and `python/BUILD.bazel`
  has no "testing" target; the only test-related public items are the `py_test`/`pytest_test`
  rules themselves — find/grep over [python/](https://github.com/bazel-contrib/rules_python/tree/main/python)
- `python/private/visibility.bzl` defines `NOT_ACTUALLY_PUBLIC = ["//visibility:public"]` "Use when
  a target isn't actually public, but needs public visibility to keep Bazel happy. Such cases are
  typically for defaults of rule attributes or macro args that get used outside of rules_python
  itself." (used in `python/config_settings/BUILD.bazel`) —
  [python/private/visibility.bzl](https://github.com/bazel-contrib/rules_python/blob/main/python/private/visibility.bzl)

### Inferences
- The helper package relies on *target* visibility (`//:__subpackages__`) plus exclusion from
  `//:distribution` for privacy; nothing marks it `testonly` at package level (unlike skylib's
  `tests/BUILD` which sets `default_testonly = 1`).
- Fake toolchains are activated per test through `config_settings`/`--extra_toolchains` values
  (string labels from `support.bzl`), which is why those packages need no outward visibility.

### Gaps
- I found no statement from maintainers about whether a public testing API was considered and
  rejected; the absence is observable only from the tree.

## Key question 3: how rules_python analysis tests load private files and whether it uses load visibility

### Takeaway
Tests load `//python/private:*.bzl` directly and silence buildifier's `bzl-visibility` lint
per load line; the repo does not use Starlark `visibility()` to protect `python/private` (one
unrelated use exists), relying on the `private/` directory convention, buildifier lint, and
target visibility instead.

### Cited Findings
- 93 files under `tests/` carry `# buildifier: disable=bzl-visibility` on loads such as
  `load("//python/private:bzlmod_enabled.bzl", "BZLMOD_ENABLED")  # buildifier: disable=bzl-visibility`
  and `load("//python/private/pypi:parse_requirements.bzl", ...)  # buildifier: disable=bzl-visibility` —
  grep over [tests/](https://github.com/bazel-contrib/rules_python/tree/main/tests); examples in
  [tests/support/explicit_init_py_test.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/explicit_init_py_test.bzl),
  [tests/pypi/parse_requirements/parse_requirements_tests.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/pypi/parse_requirements/parse_requirements_tests.bzl)
- The only `visibility(...)` load-visibility declaration in `python/` is
  `python/uv/private/lock.bzl:25: visibility(["//..."])` (which *widens* it to the whole repo so
  `examples/BUILD.bazel` can load it) — grep over [python/](https://github.com/bazel-contrib/rules_python/tree/main/python);
  [python/uv/private/lock.bzl](https://github.com/bazel-contrib/rules_python/blob/main/python/uv/private/lock.bzl)
- CI runs buildifier with `warnings: "all"` (`version: 8.2.1`), so the `bzl-visibility` lint is
  active and the disable comments are necessary —
  [.bazelci/presubmit.yml](https://github.com/bazel-contrib/rules_python/blob/main/.bazelci/presubmit.yml)
- Even the examples (a separate module) reach into private code:
  `examples/BUILD.bazel` loads `@rules_python//python/uv/private:lock.bzl` with the same disable
  comment — [examples/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/examples/BUILD.bazel)
- CONTRIBUTING style rule: "Separate files should be used to expose public APIs. This ensures our
  public API is well defined and prevents accidentally exposing a package-private symbol as a
  public symbol." and "The public API file's docstring becomes part of the user-facing docs" —
  [CONTRIBUTING.md](https://github.com/bazel-contrib/rules_python/blob/main/CONTRIBUTING.md)
- Pattern of a rules_python analysis-test package: `tests/base_rules/py_library/BUILD.bazel` is
  three lines (`load(":py_library_tests.bzl", "py_library_test_suite")` +
  `py_library_test_suite(name = "py_library_tests")`); the `.bzl` collects `_tests = []`, appends
  `_test_*` arrange functions that call `rt_util.helper_target(config.rule, name = name +
  "_subject", ...)` then `analysis_test(name, target, impl)`, and reuses
  `//tests/base_rules:base_tests.bzl` `create_base_tests(config)` across `py_binary`, `py_test`
  and `py_library` — [tests/base_rules/py_library/py_library_tests.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/base_rules/py_library/py_library_tests.bzl),
  [tests/base_rules/base_tests.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/base_rules/base_tests.bzl),
  [tests/base_rules/util.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/base_rules/util.bzl)
- Framework usage in `tests/`: 44 files load `@rules_testing//lib:analysis_test.bzl`, 70 load
  `@rules_testing//lib:test_suite.bzl` or `unit_test.bzl`, only 1 loads
  `@bazel_skylib//lib:unittest.bzl` — grep over [tests/](https://github.com/bazel-contrib/rules_python/tree/main/tests)
- Tests that need a different module context skip at load time: `explicit_init_py_test` emits an
  empty `native.test_suite` when `not BZLMOD_ENABLED` —
  [tests/support/explicit_init_py_test.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/explicit_init_py_test.bzl)

### Inferences
- Because `tests/` lives in the same module, `private/` symbols are reachable without any API
  surface for consumers; the cost is lint noise (one disable comment per load). A ruleset that
  wants hard enforcement would add `visibility(["//..."])`-style declarations in `private/` files;
  rules_python chose not to.

### Gaps
- No issue/PR discussion was found explaining why `visibility()` was not adopted; this is an
  observation of absence, not a documented decision.

## Key question 4: rules_testing — what it offers, intended usage, recommended layout, and its own tests

### Takeaway
rules_testing offers `analysis_test` (+ `test_suite`), `unit_test`, the fluent `truth` library
and `util` helpers (`helper_target`, `skip_test`, ...); its guides prescribe "arrange macro +
impl function + `test_suite` per sub-package", with only `lib/*.bzl` public and `lib/private`
hidden; its own tests live in `tests/` (same module) plus an `e2e/bzlmod` child module run by CI.

### Cited Findings
- Public modules: `lib/analysis_test.bzl` ("Support for testing analysis phase logic, such as
  rules"; exports `analysis_test` and an alias `test_suite`), `lib/truth.bzl`, `lib/util.bzl`,
  `lib/unit_test.bzl`, `lib/test_suite.bzl`, and `lib/unittest.bzl` ("This version is forked from
  bazel_skylib") — all `bzl_library` targets with `visibility = ["//visibility:public"]` while the
  package default is `//visibility:private`; `lib/private/BUILD` sets
  `default_visibility = ["//:__subpackages__"]` with one `config_setting` forced public and the
  comment "Not actually public: only public because its a dependency of public targets" —
  [lib/BUILD](https://github.com/bazelbuild/rules_testing/blob/main/lib/BUILD),
  [lib/private/BUILD](https://github.com/bazelbuild/rules_testing/blob/main/lib/private/BUILD),
  [lib/analysis_test.bzl](https://github.com/bazelbuild/rules_testing/blob/main/lib/analysis_test.bzl)
- `analysis_test(*, name, target=None, targets=None, impl, expect_failure=False, attrs={},
  attr_values={}, fragments=[], config_settings={}, testing_aspect=..., extra_target_under_test_aspects=[],
  provider_subject_factories=[])`; `impl` receives `(env, target)`; `config_settings` "may be used
  to essentially change 'build flags' for the target under test ... it's suggested to always
  explicitly call `Label()` on the value before passing it in. This ensures the label is resolved
  in your repository's context, not rule_testing's."; `provider_subject_factories` lets a ruleset
  register its own truth subjects — [lib/private/analysis_test.bzl](https://github.com/bazelbuild/rules_testing/blob/main/lib/private/analysis_test.bzl)
- Installation guidance: `bazel_dep(name = "rules_testing", version = "<VERSION>",
  dev_dependency=True)`; "We recommend using bzlmod because it's simpler" —
  [docs/source/index.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/index.md)
  (rendered at https://rules-testing.readthedocs.io/en/latest/)
- Analysis-test guide: skeleton is a `BUILD` that loads one suite function
  (`my_test_suite(name="my_test_suite")`) and a `my_tests.bzl` with `_test_hello(name)` arranging a
  `util.helper_target(...)` subject and calling `analysis_test(...)`, `_test_hello_impl(env, target)`
  asserting via `env.expect.that_target(target)...`, and `test_suite(name, tests=[...])`; "All the
  targets taking part in the arrangement should be tagged with `manual`"; "Source source files
  aren't required to exist"; setup target names must include the test `name` as prefix; limitations:
  `--analysis_testing_deps_limit` and "Mocking toolchains (adding a toolchain used only in the test)
  is not possible at the moment." — [docs/source/analysis_tests.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/analysis_tests.md)
- Best practices: "Put each suite of tests in its own sub-package ... because the names of your
  test functions become target names in the BUILD file, which makes it easier to create name
  conflicts" and "Give test functions private names ... tools like buildifier can detect the unused
  private function" — [docs/source/best_practices.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/best_practices.md)
- Unit tests: "Unit tests are for Starlark code that isn't specific to analysis-phase or loading
  phase cases; usually utility code"; `test_suite(name, basic_tests=[fn(env)], tests=[fn(name)],
  test_kwargs=...)`; "Under the hood, each test is its own target with an aggregating
  `native.test_suite`" — [docs/source/unit_tests.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/unit_tests.md),
  [docs/source/test_suite.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/test_suite.md)
- `util.helper_target(rule, **kwargs)`: "Define a target only used as a Starlark test input ...
  Tags are added to hide the target from `:all`, `/...`, TAP, etc." — adds
  `PREVENT_IMPLICIT_BUILDING_TAGS = ["manual", "nobuilder"] + _SKIP_CI_TAGS`; `util.skip_test(name)`
  defines an always-skipped test but "prefer to use `target_compatible_with`"; `util.empty_file`,
  `runfiles_paths`, `get_target_actions`, `make_testing_aspect` also exist —
  [lib/util.bzl](https://github.com/bazelbuild/rules_testing/blob/main/lib/util.bzl)
- `lib/BUILD` provides `do_nothing(name = "_stub_target_for_unit_tests")` because "Unit tests need
  some target because they're based upon analysis tests" —
  [lib/BUILD](https://github.com/bazelbuild/rules_testing/blob/main/lib/BUILD)
- rules_testing's own tests: `tests/BUILD` instantiates `analysis_test_test_suite`,
  `truth_test_suite`, `unit_test_test_suite`, `unittest_passing_tests_suite()` and a
  `build_test` over the public `bzl_library`s; subdirs `default_info_subject`, `matching`,
  `struct_subject`, `testdata`, plus `tests/test_util.bzl` —
  [tests/BUILD](https://github.com/bazelbuild/rules_testing/blob/main/tests/BUILD)
- `e2e/bzlmod` is a child module (`bazel_dep(name = "rules_testing", version = "0.0.0")` +
  `local_path_override(path = "../..")`) with "Basic tests to verify things work under bzlmod";
  CI runs it as task `e2e_bzlmod` with `working_directory: e2e/bzlmod`, alongside
  `all_tests_bzlmod` and `all_tests_workspace_latest` (`--noenable_bzlmod --enable_workspace`)
  over `...` on ubuntu2004/windows/macos_arm64 —
  [e2e/bzlmod/MODULE.bazel](https://github.com/bazelbuild/rules_testing/blob/main/e2e/bzlmod/MODULE.bazel),
  [.bazelci/presubmit.yml](https://github.com/bazelbuild/rules_testing/blob/main/.bazelci/presubmit.yml)
- rules_testing's `MODULE.bazel` runtime deps are only `platforms`, `bazel_skylib`, `rules_license`;
  stardoc/rules_python/rules_shell are `dev_dependency = True` —
  [MODULE.bazel](https://github.com/bazelbuild/rules_testing/blob/main/MODULE.bazel)
- Historical origin: the rules_python commit adding base-rule analysis tests describes them as
  "regression tests for the Starlark rewrite ... approximately the same as Bazel's Java-implemented
  tests" and loads `@rules_testing//lib:analysis_test.bzl` —
  [rules_python commit cfc038d](https://github.com/bazelbuild/rules_python/commit/cfc038d36e9fded81badea2dbff77c400bcb0bbe)

### Inferences
- rules_testing's own layout (public `lib/`, `lib/private/`, same-module `tests/`, child-module
  `e2e/`) is the minimal version of the rules_python layout; rules_python adds `tests/support` and
  `tests/integration` on top.
- `provider_subject_factories` plus rules_python's `*_subject.bzl` files show the expected way for
  a ruleset to extend truth for its own providers: write subjects in the ruleset's private test
  support package rather than upstreaming them.

### Gaps
- The readthedocs landing page fetched gave only the index; the guide text above is from the
  repo's `docs/source/*.md` (the readthedocs source), not from rendered pages.

## Key question 5: bazel_skylib `unittest.bzl` / `analysistest` — usage pattern, limitations, recommended place

### Takeaway
Skylib's `unittest.bzl` exports `unittest`, `analysistest`, `loadingtest` and `asserts`; a test is
`impl(ctx)` wrapped by `unittest.make`/`analysistest.make`, instantiated via `unittest.suite` in
a `.bzl` macro called from `BUILD`; it needs the unittest toolchain (auto-registered under
bzlmod), reports failures at test-execution time via a generated script, and can only assert
analysis-phase outcomes (providers, registered actions, `expect_failure` for analysis errors);
skylib itself keeps tests in `tests/` with `default_testonly = 1`.

### Cited Findings
- Module docstring: "`unittest` contains functions to declare and define unit tests for ordinary
  Starlark functions; `analysistest` ... tests for analysis phase behavior of a rule, such as a given
  target's providers or registered actions; `loadingtest` ... tests for loading phase behavior,
  such as macros and `native.*`; `asserts` contains the assertions used within tests." —
  [lib/unittest.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/lib/unittest.bzl),
  [docs/unittest_doc.md](https://github.com/bazelbuild/bazel-skylib/blob/main/docs/unittest_doc.md)
- `analysistest.make(impl, expect_failure=False, attrs={}, fragments=[], config_settings={},
  extra_target_under_test_aspects=[], doc="")`: "An analysis test verifies the behavior of a
  'real' rule target by examining and asserting on the providers given by the real target";
  pattern `env = analysistest.begin(ctx)` ... `return analysistest.end(env)`; "Recall that names of
  test rules must end in `_test`"; `expect_failure=True` sets
  `//command_line_option:allow_analysis_failures` and lets `asserts.expect_failure(env, msg)` check
  `AnalysisFailureInfo` causes; `analysistest.target_actions(env)` "Returns a list of actions
  registered by the target under test" — [docs/unittest_doc.md](https://github.com/bazelbuild/bazel-skylib/blob/main/docs/unittest_doc.md),
  [lib/unittest.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/lib/unittest.bzl)
- `unittest.suite(name, *test_rules)`: "To reduce duplication, we recommend writing a macro in your
  `.bzl` file to instantiate all targets, and calling that macro from your BUILD file so you only
  have to load one symbol"; attributes via `partial.make()` —
  [docs/unittest_doc.md](https://github.com/bazelbuild/bazel-skylib/blob/main/docs/unittest_doc.md)
- Toolchain requirement: `unittest.end` writes a test script via the `unittest_toolchain`
  (`cmd_toolchain`/`bash_toolchain`); skylib's `MODULE.bazel` does
  `register_toolchains("//toolchains/unittest:cmd_toolchain", "//toolchains/unittest:bash_toolchain")`
  so bzlmod consumers get it automatically, while WORKSPACE users must call
  `register_unittest_toolchains()` ("should only be called from WORKSPACE files") —
  [MODULE.bazel](https://github.com/bazelbuild/bazel-skylib/blob/main/MODULE.bazel),
  [lib/unittest.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/lib/unittest.bzl)
- Skylib's separate `rules/analysis_test.bzl` (`analysis_test(name, targets)`) only checks that
  targets analyze: "Action success/failure for the targets and their transitive dependencies are
  not verified ... NOTE: If the targets fail to analyze, instead of the analysis_test failing, the
  analysis_test will fail to build. Ideally, it would instead result in a test failure. This is a
  current infrastructure limitation" — [rules/analysis_test.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/rules/analysis_test.bzl)
- Skylib's own tests: `tests/BUILD` has `package(default_testonly = 1)`, calls
  `unittest_passing_tests_suite()` etc., and uses `sh_test` end-to-end tests (`unittest_e2e_test`,
  `analysis_test_e2e_test`, tagged `local`) that spin up a scratch workspace — because "Some
  unittest.bzl tests verify a test fails when assertions are not met. Such tests must be run in an
  e2e shell test. This suite only includes tests which verify success tests." —
  [tests/BUILD](https://github.com/bazelbuild/bazel-skylib/blob/main/tests/BUILD),
  [tests/unittest_tests.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/tests/unittest_tests.bzl),
  [tests/unittest_test.sh](https://github.com/bazelbuild/bazel-skylib/blob/main/tests/unittest_test.sh)
- Skylib README contribution rule: "Add unit tests for your module in the `tests` directory." —
  [README.md](https://github.com/bazelbuild/bazel-skylib/blob/main/README.md)
- Skylib's `MODULE.bazel` itself depends on `rules_testing` 0.6.0 as a `dev_dependency` and keeps
  a `local_path_override` for its gazelle plugin under "INTERNAL ONLY - lines after this are not
  included in the release packaging" — [MODULE.bazel](https://github.com/bazelbuild/bazel-skylib/blob/main/MODULE.bazel)
- rules_testing ships a fork of this file (`lib/unittest.bzl`, "This version is forked from
  bazel_skylib") — [rules_testing lib/BUILD](https://github.com/bazelbuild/rules_testing/blob/main/lib/BUILD)

### Inferences
- Skylib's `analysistest` and rules_testing's `analysis_test` share the same mechanism
  (`analysis_test = True` rule + transition on config settings + aspect to collect actions); the
  difference is ergonomics (`ctx`-based asserts vs. `env.expect` truth subjects and
  `test_suite`). Neither can observe action execution; "cannot test build failures" follows from
  the design (assertions evaluate at analysis time, outputs are written as a test script) and from
  skylib's note that analysis failures become build breakages unless `expect_failure` is used.

### Gaps
- Skylib's docs do not state a package-placement recommendation beyond "tests directory" for its
  own repo; the sub-package advice comes from rules_testing's best practices.

## Key question 6: Bazel docs guidance on rule test categories and helper placement

### Takeaway
The Bazel "Testing" page describes three categories — analysis tests of rules (skylib
`analysistest`, incl. `expect_failure`, actions and `config_settings`), artifact validation via
`sh_test`/custom rules, and `unittest` for utilities — and the "Deploying rules" page says tests
belong in the language directory or a top-level `tests/` with an optional `examples/`; neither
page covers bazel-subprocess integration tests or helper placement.

### Cited Findings
- Bazel "Testing" page (fetched 2026-11-06): analysis tests are "currently the best option for
  testing the inner workings of rules"; it covers provider assertions, `expect_failure = True`
  with the target under test tagged `manual`, `analysistest.target_actions(env)`, and
  `config_settings` on `analysistest.make()`; it also recommends naming `_test_foo` / `foo_test` /
  `_foo_test_impl` / `foo_`-prefixed targets — [bazel.build/rules/testing](https://bazel.build/rules/testing)
- Same page, limitations: an error during the test "is seen by Bazel as a build breakage rather
  than a test failure"; test target names "must be named such that they do not collide"; analysis
  tests should be "fairly small and lightweight", some features limited to targets with at most
  500 transitive dependencies — [bazel.build/rules/testing](https://bazel.build/rules/testing)
- Same page, artifact validation: an `sh_test` with the artifact in `data` and `$(location ...)`
  in `args`, or a custom rule using `ctx.actions.expand_template` on a shell template; utilities
  tested with `unittest` and `unittest.suite()`; the page "does not mention `bazel_integration_test`
  or subprocess-based integration tests" and "does not state a formal rule" for helper placement
  (examples keep `*_test.bzl` next to the `BUILD`) — [bazel.build/rules/testing](https://bazel.build/rules/testing)
- Bazel "Deploying rules" page: "There should be tests that verify that the rules are working as
  expected"; tests can live in the language directory or a top-level `tests/` directory; "It is
  useful to users to have an `examples/` directory that shows users a couple of basic ways that the
  rules can be used"; public rules go in `<lang>/` as individual `.bzl` files; the page does not
  mention `private/` or integration tests — [bazel.build/rules/deploying](https://bazel.build/rules/deploying)
- rules_bazel_integration_test README: macros "support running integration tests with multiple
  versions of Bazel"; `bazel_binaries` extension downloads Bazel versions (e.g. from
  `//:.bazelversion`); "For `glob()` in the parent workspace to find files in the child workspaces,
  we need to use the deleted packages mechanism" (`--deleted_packages` or `.bazelignore`, helper
  `bazel run @rules_bazel_integration_test//tools:update_deleted_packages`); "By default, the
  integration test targets are tagged as `manual`"; its own example places child workspaces under
  `examples/` — [rules_bazel_integration_test README](https://github.com/bazel-contrib/rules_bazel_integration_test/blob/main/README.md)

### Inferences
- The official docs establish the categories (analysis / artifact / utility) but leave the
  "bazel subprocess" tier and helper placement to community practice, which rules_python fills with
  `tests/integration` + `tests/support` and rules_testing's "one suite per sub-package" rule.

### Gaps
- The Bazel docs give no 2026-specific guidance on bzlmod child modules; all child-module practice
  comes from the rulesets themselves.

## Key question 7: explicit maintainer statements on layout rationale

### Takeaway
The explicit rationale lives in rules_python's `docs/devguide.md`, `tests/integration/README.md`
and `CONTRIBUTING.md`, and in rules_testing's `best_practices.md`; nothing else (issues, blog
posts) adds a documented design decision.

### Cited Findings
- "Most code should have tests of some sort ... We don't require 100% test coverage; testing
  certain Bazel functionality is difficult, and some edge cases are simply too hard to test or not
  worth the extra complexity." — [docs/devguide.md](https://github.com/bazel-contrib/rules_python/blob/main/docs/devguide.md)
- `sh_py_run_test`/`py_reconfig_test` are described as the way to test flag-dependent runtime
  behaviour "without the overhead of a bazel-in-bazel integration test" —
  [tests/support/sh_py_run_test.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/sh_py_run_test.bzl),
  [tests/support/py_reconfig.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/py_reconfig.bzl)
- Bazel-in-bazel tests exist for "anything that happens prior to the analysis phase" and are
  capped by the "limit of 80 jobs" on CI — [tests/integration/README.md](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/README.md)
- The integration-test tags carry inline justification: "These tests are very heavy weight, so
  much so that only a couple can be run in parallel without harming their reliability", "The
  default_test_runner() assumes it can write to the user's home directory ... Give it access"
  (`no-sandbox`), "The CI RBE setup can't successfully run these tests remotely" (`no-remote-exec`) —
  [tests/integration/integration_test.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/integration_test.bzl)
- Phase-separation style rule (affects what tests may load): "The different build phases shouldn't
  load code that defines objects that aren't valid for their phase ... Providers should be in their
  own files ... One rule per file is preferred" — [CONTRIBUTING.md](https://github.com/bazel-contrib/rules_python/blob/main/CONTRIBUTING.md)
- Commit-type `test:` "means only tests are being added"; dev-only changes such as "cleaning up
  testing, adding test support code" go at the end of a PR body —
  [CONTRIBUTING.md](https://github.com/bazel-contrib/rules_python/blob/main/CONTRIBUTING.md)
- rules_testing: sub-package-per-suite and private test function names are given as explicit
  best practices with reasons (name collisions; buildifier unused-function detection) —
  [docs/source/best_practices.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/best_practices.md)

### Inferences
- The consistent maintainer position across the three repos: tests are same-module by default,
  bazel-subprocess tests are a last resort, examples double as end-to-end/BCR checks, and test
  helpers are private support code, not a product API.

### Gaps
- A web search for maintainer discussion of the `tests/support` layout returned only mirrors of
  the directory and the original analysis-test commit; no issue or design doc was found —
  [search result](https://github.com/bazelbuild/rules_python/commit/cfc038d36e9fded81badea2dbff77c400bcb0bbe)

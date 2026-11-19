# Cross-cutting conventions and official guidance for testing Bazel rulesets

Method note: all ruleset facts below come from shallow clones of the default branches taken on
2026-11-06 (rules_python, rules_go, rules_rust, rules_cc, rules_java, bazel-skylib,
rules_jvm_external, rules_apple, rules_oci, rules_kotlin, rules_pkg, bazel-lib, rules_testing,
rules_js, rules_bazel_integration_test, rules_proto, rules-template), plus the Bazel and BCR docs
fetched the same day. Where a repository has no such file, that absence was verified by listing the
directory, not assumed. Legacy WORKSPACE-only material is flagged inline.

## KQ1: What does the official Bazel guidance (bazel.build/rules/testing, deploying, visibility) say about test categories and placement?

### Takeaway
Bazel's official rule-testing page names four kinds of tests (analysis tests with Skylib
`analysistest`, analysis-failure tests, artifact validation via a `*_test` on built outputs, and
plain Skylib `unittest` for helpers) and places test `.bzl` files beside the rule in the same
package; it says nothing about Bazel-in-Bazel integration tests, `rules_testing`, `testonly` or
incrementality. The deploying page only says tests go in the language's standard location or a
top-level `tests/`, and recommends starting from `rules-template`.

### Cited Findings
- `bazel.build/rules/testing` names: (a) analysis tests via Skylib `unittest.bzl` `analysistest`,
  described as "the best option for testing the inner workings of rules", inspecting providers via
  `analysistest.target_under_test(env)` and actions via `analysistest.target_actions(env)`;
  (b) failure tests via `analysistest.make(..., expect_failure = True)` plus
  `asserts.expect_failure(env, "...")`; (c) "artifact validation" via a `*_test` target (e.g.
  `sh_test`) that checks generated files, or a custom test rule that instantiates a script template;
  (d) utility tests with Skylib `unittest` for helpers that are neither macros nor rules. Bazel-run
  integration tests and `rules_testing` are not mentioned — [Testing rules](https://bazel.build/rules/testing)
- The same page's caveats: analysis-test assertions run during the build (errors surface as build
  breakage, not test failure); analysis tests must stay "fairly small and lightweight" (some
  features limited to targets with ≤500 transitive deps); testing rules must be bound to global
  variables, not created inside a macro; targets under test should be tagged `manual`;
  `config_settings` use the `//command_line_option:` prefix — [Testing rules](https://bazel.build/rules/testing)
- Placement/naming in the official examples: test `.bzl` beside the rule in the same package
  (`//mypkg/myrules_test.bzl` next to `//mypkg/myrules.bzl`), suites declared in that package's
  BUILD via `native.test_suite`; naming stem `foo`: `_test_foo` macro, `foo_test` rule/target,
  `_foo_test_impl`, `foo_` prefixes for targets under test — [Testing rules](https://bazel.build/rules/testing)
- Skylib `analysistest.make(impl, expect_failure=False, attrs={}, fragments=[], config_settings={}, extra_target_under_test_aspects=[], doc="")`
  adds a mandatory `target_under_test` attribute carrying an aspect that captures `target.actions`
  into an `_ActionInfo` provider; the rule is declared with `test = True, analysis_test = True`.
  `expect_failure = True` sets `//command_line_option:allow_analysis_failures` to `"True"` through
  an `analysis_test_transition`; `asserts.expect_failure` checks for `AnalysisFailureInfo` and
  substring-matches the joined cause messages. `target_bin_dir_path(env)` returns the target's
  `ctx.bin_dir.path` — [bazel-skylib lib/unittest.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/lib/unittest.bzl)
- Skylib's separate `analysis_test` rule (`@bazel_skylib//rules:analysis_test.bzl`) only checks
  that `targets` and their transitive deps analyze ("equivalent of `bazel build [targets] --nobuild`");
  it does not execute actions, and an analysis failure makes the test target fail to build rather
  than report a test failure (documented as a current infrastructure limitation) —
  [bazel-skylib rules/analysis_test.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/rules/analysis_test.bzl)
- `bazel.build/rules/deploying`: start from the rules-template repository; public rules and macros
  in individual `.bzl` files under a per-language directory with a BUILD file; tests "either in the
  language's standard test location or a top-level `tests/` directory"; optional `examples/`;
  document with Stardoc; no guidance on test categories, no mention of `private/` directories,
  `rules_testing`, `bazel_integration_test` or BCR — [Deploying rules](https://bazel.build/rules/deploying)
- rules-template (the recommended starting point) ships `e2e/smoke/MODULE.bazel` with
  `bazel_dep(name = "com_myorg_rules_mylang", version = "0.0.0", dev_dependency = True)` +
  `local_path_override(path = "../..")`, and `.bcr/presubmit.yml` whose only job is
  `bcr_test_module: module_path: "e2e/smoke"` running `test_targets: ["//..."]` on Bazel 9.* and
  8.* across debian11/macos/ubuntu2204/windows —
  [rules-template e2e/smoke/MODULE.bazel](https://github.com/bazel-contrib/rules-template/blob/main/e2e/smoke/MODULE.bazel),
  [rules-template .bcr/presubmit.yml](https://github.com/bazel-contrib/rules-template/blob/main/.bcr/presubmit.yml)
- rules_testing's own docs define: analysis tests ("the typical way to test rule behavior",
  observing providers, actions, aspects and configuration), unit tests ("for Starlark code that
  isn't specific to analysis-phase or loading phase cases; usually utility code"), and the fluent
  "truth" asserts. Best practices: put each suite in its own sub-package because test function
  names become target names; give test functions private (underscore) names so buildifier flags
  tests forgotten from the suite list —
  [rules_testing docs/source/analysis_tests.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/analysis_tests.md),
  [unit_tests.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/unit_tests.md),
  [best_practices.md](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/best_practices.md)
- rules_testing is consumed as `bazel_dep(name = "rules_testing", version = "<VERSION>", dev_dependency=True)`; a WORKSPACE recipe exists (legacy) — [rules_testing docs index](https://github.com/bazelbuild/rules_testing/blob/main/docs/source/index.md)
- rules_go's test-suite rules (the most explicit written policy found): every test folder has a
  README.rst with a section per test rule saying what it checks and linking the issue; "Test one
  thing at a time"; tests must run on CI by default; flaky tests are deleted; all three platforms;
  "Anything that requires external dependancies beyond those of the rules belongs in the
  integration tests" — [rules_go tests/README.rst](https://github.com/bazel-contrib/rules_go/blob/master/tests/README.rst)
- rules_go `tests/integration/README.rst`: integration tests "check that rules_go works correctly in
  the real world, rather than in isolated single feature tests"; "If the unit tests were correct
  and exhaustive this directory should in theory be redundant" — [rules_go tests/integration/README.rst](https://github.com/bazel-contrib/rules_go/blob/master/tests/integration/README.rst)
- rules_python `tests/integration/README.md`: Bazel-in-Bazel tests exist "for testing internal
  aspects of the rules that aren't easily tested as tests run by Bazel itself (basically anything
  that happens prior to the analysis phase)"; adding one requires `--deleted_packages`,
  `.bazelignore` entries and a `rules_python_integration_test` target (built on
  `@rules_bazel_integration_test//bazel_integration_test:defs.bzl`) —
  [rules_python tests/integration/README.md](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/README.md),
  [integration_test.bzl](https://github.com/bazel-contrib/rules_python/blob/main/tests/integration/integration_test.bzl)

### Inferences
- The official page's "artifact validation" category is what rulesets implement as build-and-inspect
  tests (`diff_test`, `sh_test` over outputs, rules_pkg `verify_archive_test`, bazel-lib
  `assert_*`); the official page never uses the words "integration" or "e2e" — those categories are
  a community convention (rules-template `e2e/`, rules_bazel_integration_test), not Bazel guidance.
- Framework choice splits by generation: Skylib `analysistest` in older rulesets (rules_rust
  59 files, rules_apple 19, rules_jvm_external, rules_go 1), `rules_testing` in Google-maintained
  "Starlarkified" rulesets (rules_python 94 files, rules_cc 39, rules_java, rules_kotlin) — counts
  from grep over the clones.

### Gaps
- `bazel.build/rules/testing` does not state where tests should live relative to a `private/`
  directory, nor anything about `testonly`; no official page found that discusses Bazel-in-Bazel
  integration tests for rulesets.

## KQ2: Which mature rulesets ship a public test-support package for consumers, and how is it marked?

### Takeaway
Only a minority of rulesets ship consumer-facing test support, and each does it differently:
rules_go `go/tools/bazel_testing` (Go library + `go_bazel_test` macro, public, not `testonly`),
bazel-lib `lib/testing.bzl` (public assertion macros), rules_pkg `pkg/verify_archive.bzl`
(public `verify_archive_test`, explicitly "available for integration testing"), and
rules_bazel_integration_test as a standalone ruleset. rules_cc has no `cc/testing`, rules_java's
`java/testutil.bzl` is an internal shim, rules_apple's `apple_verification_test` is explicitly
"implementation details … do not depend on this rule", and rules_oci's `oci/tests` is the ruleset's
own regression package, not a consumer API.

### Cited Findings
- rules_go `go/tools/bazel_testing/BUILD.bazel`: `go_library(name = "bazel_testing", …, visibility = ["//visibility:public"])`
  with `data` on the host-compatible Go SDK; `filegroup(name = "all_files", testonly = True, srcs = glob(["**"]), visibility = public)`;
  `bzl_library(name = "def", srcs = ["def.bzl"], visibility = public)`. The library itself is not
  `testonly`; only the `all_files` filegroup is — [rules_go go/tools/bazel_testing/BUILD.bazel](https://github.com/bazel-contrib/rules_go/blob/master/go/tools/bazel_testing/BUILD.bazel)
- `def.bzl` defines `go_bazel_test(rule_files = None, **kwargs)`: a `go_test` wrapper that adds the
  `bazel_testing` dep, adds `//:all_files` as `data`, passes `-begin_files … -end_files` rlocation
  paths, sets `rundir = "."`, and forces tags `local` ("don't run in sandbox or on remote
  executor") and `exclusive` ("run one test at a time, since they share a Bazel output directory") —
  [rules_go go/tools/bazel_testing/def.bzl](https://github.com/bazel-contrib/rules_go/blob/master/go/tools/bazel_testing/def.bzl)
- `bazel_testing.go` package doc: "provides an integration testing framework for testing rules_go
  with Bazel… Tests are run in a synthetic test workspace. Tests may run bazel commands with
  RunBazel"; `RunBazel`/`BazelOutput` return a `*StderrExitError` wrapping stderr on non-zero exit —
  [rules_go bazel_testing.go](https://github.com/bazel-contrib/rules_go/blob/master/go/tools/bazel_testing/bazel_testing.go)
- rules_go documents `go_bazel_test` only inside the test tree (`tests/core/go_bazel_test/README.rst`,
  `tests/core/README.rst`); no mention in `docs/` or `go/*.rst` was found by grep — [rules_go tests/core/go_bazel_test/README.rst](https://github.com/bazel-contrib/rules_go/blob/master/tests/core/go_bazel_test/README.rst)
- 45 BUILD files under `rules_go/tests` use `go_bazel_test` (grep count) — [rules_go tests/](https://github.com/bazel-contrib/rules_go/tree/master/tests)
- bazel-lib `lib/testing.bzl` ("Helpers for making test assertions") exports `assert_contains`
  (generates an `sh_test`; "Depends on bash"), `assert_outputs`, `assert_archive_contains`,
  `assert_directory_contains`; the `bzl_library(name = "testing")` in `lib/BUILD.bazel` carries no
  `testonly` and no explicit visibility (package default) — [bazel-lib lib/testing.bzl](https://github.com/bazel-contrib/bazel-lib/blob/main/lib/testing.bzl),
  [lib/BUILD.bazel](https://github.com/bazel-contrib/bazel-lib/blob/main/lib/BUILD.bazel)
- rules_pkg `pkg/verify_archive.bzl` docstring: "Rule to test that the content of an archive has
  particular properties. This is available for integration testing, when people want to verify that
  all the files they expect are in an archive." The `verify_archive_test(name, target, must_contain,
  must_contain_regex, must_not_contain, must_not_contain_regex, min_size, max_size, verify_links, **kwargs)`
  macro expands a `.py.tpl` into a `py_test`; `pkg/BUILD` `exports_files(["verify_archive_test_main.py.tpl"])` —
  [rules_pkg pkg/verify_archive.bzl](https://github.com/bazelbuild/rules_pkg/blob/main/pkg/verify_archive.bzl)
- rules_cc: `cc/` contains no `testing` directory (listing: `action_names.bzl`, `common/`,
  `private/`, `toolchains/`, …). Test helpers live in `tests/cc/testutil/` (`cc_analysis_test.bzl`,
  `cc_binary_target_subject.bzl`, `cc_info_subject.bzl`, `link_action_subject.bzl`, `mock_rules.bzl`)
  and `tests/rule_based_toolchain/{testing_rules,subjects,generics,helpers}.bzl` — [rules_cc cc/](https://github.com/bazelbuild/rules_cc/tree/main/cc),
  [rules_cc tests/cc/testutil](https://github.com/bazelbuild/rules_cc/tree/main/tests/cc/testutil)
- rules_cc `tests/cc/testutil/testutil.bzl` declares `visibility(["//third_party/bazel_rules/rules_cc/..."])`
  (a Google-monorepo path, i.e. a copybara artifact) — [rules_cc tests/cc/testutil/testutil.bzl](https://github.com/bazelbuild/rules_cc/blob/main/tests/cc/testutil/testutil.bzl)
- rules_java `java/testutil.bzl` ("Exposes some private APIs for tests", `# copybara: rules_java visibility`,
  `# TODO: consider eventually upstreaming to rules_cc`) exposes three CcInfo accessors; it has no
  `bzl_library` in `java/BUILD` and its only loader is `test/java/testutil/cc_info_subject.bzl`.
  The real test support (`javac_action_subject.bzl`, `java_info_subject.bzl`, `mock_java_toolchain.bzl`, …)
  lives in `test/java/testutil/` — [rules_java java/testutil.bzl](https://github.com/bazelbuild/rules_java/blob/master/java/testutil.bzl),
  [rules_java test/java/testutil](https://github.com/bazelbuild/rules_java/tree/master/test/java/testutil)
- rules_apple `test/starlark_tests/rules/apple_verification_test.bzl` docstring: "This rule is meant
  to be used only for rules_apple tests and are considered implementation details that may change at
  any time. Please do not depend on this rule." It applies a transition and runs a shell verifier
  on the built bundle — [rules_apple apple_verification_test.bzl](https://github.com/bazelbuild/rules_apple/blob/master/test/starlark_tests/rules/apple_verification_test.bzl)
- rules_apple `test/test_rules.bzl` `apple_multi_shell_test` builds one `sh_test` per configuration
  that runs a script invoking `bazel build` with different flags (shell-based integration tests),
  helper assertions in `apple_shell_testutils.sh` (`assert_zip_contains`, …) — [rules_apple test/test_rules.bzl](https://github.com/bazelbuild/rules_apple/blob/master/test/test_rules.bzl)
- rules_oci `oci/tests/BUILD.bazel` contains the ruleset's own `oci_pull` regression tests
  (`run_binary` with crane + `diff_test` against `@repo` outputs, `build_test`, Starlark unit tests
  in `pull_tests.bzl`); consumer-level checks live in `e2e/assertion` (bats tests, own
  MODULE.bazel with `local_path_override`), `e2e/smoke`, `e2e/wasm` — [rules_oci oci/tests/BUILD.bazel](https://github.com/bazel-contrib/rules_oci/blob/main/oci/tests/BUILD.bazel),
  [rules_oci e2e/assertion](https://github.com/bazel-contrib/rules_oci/tree/main/e2e/assertion)
- rules_kotlin: `src/test/` holds `starlark/` (rules_testing-based, with its own `case.bzl`
  framework and `truth.bzl`), `kotlin/` (Kotlin assertion tests against built jars), `integration/`;
  `examples/` "also serve as integration tests" driven through
  `@rules_bazel_integration_test//bazel_integration_test:defs.bzl` — [rules_kotlin examples/README.md](https://github.com/bazelbuild/rules_kotlin/blob/master/examples/README.md),
  [rules_kotlin src/test/starlark/case.bzl](https://github.com/bazelbuild/rules_kotlin/blob/master/src/test/starlark/case.bzl)
- rules_jvm_external: `tests/unit/` (Skylib `analysistest`), `tests/integration/`, `tests/bazel_run_tests.sh`,
  and `examples/*` as separate workspaces; BCR presubmit runs `examples/java-export` — [rules_jvm_external tests/](https://github.com/bazelbuild/rules_jvm_external/tree/master/tests)
- rules_bazel_integration_test (bazel-contrib): "macros that execute integration tests that use
  Bazel (e.g. execute tests in a child workspace)… with multiple versions of Bazel"; consumed as
  `bazel_dep(..., dev_dependency = True)`; requires `--deleted_packages` for child workspaces; WORKSPACE
  path labelled "Legacy" — [rules_bazel_integration_test README](https://github.com/bazel-contrib/rules_bazel_integration_test/blob/main/README.md)
- rules_python keeps its shared test support in `tests/support/` (subjects such as
  `py_info_subject.bzl`, `py_executable_info_subject.bzl`, `sh_py_run_test.bzl`, mocks, toolchains)
  with `package(default_visibility = ["//:__subpackages__"])`, i.e. not consumer-facing —
  [rules_python tests/support/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/tests/support/BUILD.bazel)

### Inferences
- The consumer-facing test packages that exist are all *black-box* helpers (run Bazel on a synthetic
  workspace; assert on produced files/archives). No ruleset exposes analysis-test subjects or
  mock toolchains as public API; those stay under `tests/`/`test/` with repo-internal visibility.
- None of the public test-support `.bzl` libraries found is marked `testonly`; `testonly` appears
  only on data filegroups (rules_go `all_files`) and as a pass-through attribute.

### Gaps
- Could not confirm whether bazel-lib documents `lib/testing.bzl` in generated docs (the clone has
  no `docs/` directory; docs appear to be published elsewhere).
- rules_pkg's generated docs mention `verify_archive_test` only in CHANGELOG within the clone; the
  rendered doc site was not checked.

## KQ3: How do rulesets enforce the public API boundary (load visibility, bzl_library/package visibility, package_group, --check_bzl_visibility, testonly)?

### Takeaway
Load visibility (`visibility()` in `.bzl`, Bazel ≥ 6.0, default public, enforced by
`--check_bzl_visibility`) is used heavily only by the Google-maintained rules_cc (63 calls),
rules_apple (33) and rules_java (10); rules_python has one call, and rules_go, rules_rust,
rules_jvm_external, bazel-skylib, bazel-lib, rules_oci, rules_pkg, rules_js, rules_kotlin,
rules_testing use none. Specs are repo-relative, `@` is forbidden, so a `visibility("private")`
or `visibility("//...")` file is unloadable from any other module — including a separate test
module; rulesets that want tests to reach internals list the test package explicitly
(`"//tests/rule_based_toolchain/..."`, `"//test/..."`, `["//test"]`) or keep tests in the same
module. Target-level boundaries are set with `package(default_visibility = ["//:__subpackages__"])`
on `private/` packages (rules_python) or `exports_files(..., visibility = ["//docs:__pkg__"])`
(rules_oci). No ruleset used a `package_group` for the boundary.

### Cited Findings
- Bazel docs: load visibility is set by calling `visibility(value)` once at top level of the `.bzl`
  (recommended directly below the `load()`s); `value` is a list of package specs in `package_group`
  `packages` form without negations; `"//foo"`, `"//foo/..."`, `"public"`, `"private"`; empty list
  equals `"private"`; "The '@' syntax is not allowed; all specifications are interpreted relative to
  the current module's repository"; `"//..."` always means all packages in the current repository;
  a module can always be loaded within its own package — [Bazel .bzl globals: visibility](https://bazel.build/rules/lib/globals/bzl#visibility)
- Load visibility defaults to public (unlike target visibility); available as of Bazel 6.0;
  `--check_bzl_visibility=false` disables enforcement (docs: for prototyping, not submitted code;
  violations then emit warnings instead of failing); load visibility cannot be defined via a
  `package_group` — to share a list between target and load visibility, put it in a `.bzl` variable;
  underscore-prefixed symbols cannot be loaded; Buildifier's `bzl-visibility` lint warns when loading
  from `internal`/`private` directories from outside their parent, and the docs call that lint
  unnecessary where files declare their visibility — [Bazel visibility concepts](https://bazel.build/concepts/visibility#load-visibility)
- Target visibility and load visibility are independent and may disagree; the docs note this can
  bite "tools, such as documentation generators or test tools, that consume `.bzl` files as source" —
  [Bazel visibility concepts](https://bazel.build/concepts/visibility#load-visibility)
- Counts of top-level `visibility(` calls in `.bzl` files per clone: rules_cc 63 (32× `"private"`,
  8× `"public"`, 5× `"//tests/rule_based_toolchain/..."`, 2× `"//cc/..."`, 2× `PUBLIC_IF_NOT_GOOGLE`),
  rules_apple 33 (9× `"private"`, 7× `"//test/starlark_tests/..."`, 5× `"public"`, 2× `"//apple/..."`,
  lists including `"//test/..."`), rules_java 10 (6× `"private"`, `["//test"]`, `["//java/common/rules/..."]`,
  `["//java"]`, `["//java/..."]`), rules_python 1 (`python/uv/private/lock.bzl`: `visibility(["//..."])`),
  0 in rules_go, rules_rust, rules_jvm_external, bazel-skylib, bazel-lib, rules_oci, rules_pkg,
  rules_js, rules_kotlin, rules_testing, rules_proto, rules_bazel_integration_test, rules-template —
  grep over clones; representative files: [rules_cc cc/toolchains/impl/toolchain_config.bzl](https://github.com/bazelbuild/rules_cc/blob/main/cc/toolchains/impl/toolchain_config.bzl),
  [rules_apple apple/internal/platform_support.bzl](https://github.com/bazelbuild/rules_apple/blob/master/apple/internal/platform_support.bzl),
  [rules_java java/bazel/repositories_util.bzl](https://github.com/bazelbuild/rules_java/blob/master/java/bazel/repositories_util.bzl),
  [rules_python python/uv/private/lock.bzl](https://github.com/bazel-contrib/rules_python/blob/main/python/uv/private/lock.bzl)
- rules_cc centralises its allowlists in `cc/private/visibility.bzl` (`visibility("//cc/...")`,
  `PUBLIC_IF_NOT_GOOGLE = ["public"]`, "publicly visible in the open-source Bazel world, but have
  restricted visibility within Google's monorepo", plus a runtime `check_private_api` allowlist of
  (repo, package) pairs such as `("rules_rust", "rust/private")`, `("rules_java", "")`) —
  [rules_cc cc/private/visibility.bzl](https://github.com/bazelbuild/rules_cc/blob/main/cc/private/visibility.bzl)
- Pattern "private file admits the in-repo test package": rules_cc `cc/toolchains/impl/*.bzl`
  (`args_utils`, `nested_args`, `variables`, `external_feature`, `toolchain_config`, …) each list
  `"//tests/rule_based_toolchain/..."`; `libc_version.bzl` lists `"//tests/libc_settings"`;
  rules_apple internals list `"//test/..."` or `"//test/starlark_tests/..."`; rules_java
  `repositories_util.bzl` is `visibility(["//test"])` — same files as above
- rules_cc tests that still need an un-listed private file use `# buildifier: disable=bzl-visibility`
  (`tests/default_unix_toolchain/BUILD.bazel`, `tests/cc/common/cc_common_test.bzl`); rules_apple's
  `apple_verification_test.bzl` and rules_rust's `crate_universe` do the same — [rules_cc tests/cc/common/cc_common_test.bzl](https://github.com/bazelbuild/rules_cc/blob/main/tests/cc/common/cc_common_test.bzl)
- No `.bazelrc` in any clone sets `--check_bzl_visibility`, i.e. all rely on the default (enforced) — grep over clones
- Target-visibility boundaries: rules_python `python/private/BUILD.bazel`
  `package(default_visibility = ["//:__subpackages__"])` while `python/BUILD.bazel` is
  `package(default_visibility = ["//visibility:public"])`; rules_oci `oci/private/BUILD.bazel`
  `exports_files(glob(["*.bzl"]), visibility = ["//docs:__pkg__"])` and `bzl_library` targets
  visible to `//docs:__pkg__` + `//oci:__subpackages__`; rules_testing `lib/BUILD`
  `default_visibility = private` with explicit public targets and `lib/private/BUILD`
  `default_visibility = ["//:__subpackages__"]`; counter-examples rules_cc `cc/private/BUILD` and
  rules_js `js/private/BUILD.bazel` use `default_visibility = ["//visibility:public"]` —
  [rules_python python/private/BUILD.bazel](https://github.com/bazel-contrib/rules_python/blob/main/python/private/BUILD.bazel),
  [rules_oci oci/private/BUILD.bazel](https://github.com/bazel-contrib/rules_oci/blob/main/oci/private/BUILD.bazel),
  [rules_testing lib/private/BUILD](https://github.com/bazelbuild/rules_testing/blob/main/lib/private/BUILD)
- No `package_group(` definition exists in the top-level BUILD files of rules_python, rules_go,
  rules_rust, rules_cc, rules_java, rules_kotlin, rules_jvm_external, rules_apple, rules_oci,
  bazel-lib, rules_js, rules_testing, rules_pkg (grep) — clones
- `package_group` facts from the docs: `includes` composes groups, a `package_group` is always
  publicly visible, groups used in `transitive_visibility` may not use `includes` — [Bazel visibility concepts](https://bazel.build/concepts/visibility)
- Cross-module enforcement is real: Bazel issue #18346 (May 2023) shows rules_go/rules_python
  downstream failing with "Bzlmod system contains .bzl load visibility violations …" when a `.bzl`
  in one repo was loaded from a repo-rule context in another; fixed by "Stop checking .bzl files
  visibility in RepoRuleFunction" (cherry-picked for 6.3.0) — [bazelbuild/bazel#18346](https://github.com/bazelbuild/bazel/issues/18346)
- Consumer-side test modules (rules_python `examples/bzlmod`, rules_go `tests/bcr`, bazel-lib
  `e2e/smoke`, rules_oci `e2e/*`, rules-template `e2e/smoke`) depend on the ruleset via
  `bazel_dep(name = …, version = "0.0.0")` + `local_path_override(path = "../..")`, so they can only
  load `.bzl` files whose load visibility is `"public"` and only depend on targets visible to
  external repos — [rules_go tests/bcr/MODULE.bazel](https://github.com/bazel-contrib/rules_go/blob/master/tests/bcr/MODULE.bazel),
  [rules_python examples/bzlmod/MODULE.bazel](https://github.com/bazel-contrib/rules_python/blob/main/examples/bzlmod/MODULE.bazel)

### Inferences
- Because `visibility()` cannot name another repository, there is no way to grant a sibling test
  *module* access to private `.bzl` files; the only patterns observed are (a) white-box tests in the
  same module with the test package allow-listed in `visibility([...])`, and (b) a separate e2e
  module that is deliberately restricted to the public API. The absence of any `package_group`
  allowing a sibling module is consistent with that restriction.
- A separate test module therefore doubles as an API-boundary check: a successful `bazel test //...`
  in `e2e/` proves the public surface suffices for the example workload.

### Gaps
- The exact Bazel error text for an ordinary (non-repo-rule) load-visibility violation was not
  captured from a primary source (docs omit it; the issue above quotes only the bzlmod variant).
- No ruleset was found that documents `bzl_library` visibility as an API-boundary mechanism;
  `bzl_library` visibility in the clones serves Stardoc (`//docs:__pkg__`) rather than enforcement.

## KQ4: How do rulesets verify caching/incrementality or action-level behaviour, and where do such tests live?

### Takeaway
Action-level assertions (mnemonic, argv, inputs, outputs, env) are made in analysis tests —
Skylib `analysistest.target_actions` or rules_testing `TargetSubject.action_named(mnemonic)` /
`action_generating(short_path)` with `ActionSubject` — and live in the ruleset's own `tests/` tree
as white-box tests. Genuine cache-boundary tests are rare: the only execution-log-based test found
is rules_js `e2e/path_mapping/test.sh` (two builds with a shared `--disk_cache`, `--execution_log_json_file`,
assert `cacheHit == true` for the mnemonic); rules_go has a reproducibility integration test;
rules_rust a determinism tester binary; none of the surveyed rulesets uses
`--execution_log_compact_file` in a test (rules_python only in a BuildBuddy bazelrc).

### Cited Findings
- rules_testing `ActionSubject` methods: `argv()`, `contains_at_least_args()`,
  `contains_at_least_inputs()`, `contains_flag_values()`, `contains_none_of_flag_values()`,
  `content()`, `env()`, `execution_info()`, `has_flags_specified()`, `inputs()`, `mnemonic()`,
  `not_contains_arg()`, `outputs()`, `substitutions()`; obtained via `TargetSubject.action_generating(short_path)`
  or `action_named(mnemonic)` — [rules_testing lib/private/action_subject.bzl](https://github.com/bazelbuild/rules_testing/blob/main/lib/private/action_subject.bzl),
  [target_subject.bzl](https://github.com/bazelbuild/rules_testing/blob/main/lib/private/target_subject.bzl)
- rules_testing's `TargetSubject.failures()` reads `AnalysisFailureInfo` only, i.e. analysis-phase
  failures; no API for execution-phase (build) failures exists in `lib/` — [target_subject.bzl](https://github.com/bazelbuild/rules_testing/blob/main/lib/private/target_subject.bzl)
- Files using action assertions (`target_actions|action_named|action_generating|actions_named|.mnemonic()`),
  per clone: rules_apple 24, rules_kotlin 23, rules_java 18, rules_cc 17, rules_testing 6,
  rules_python 5, rules_rust 4 (`test/unit/dlltool/dlltool_test.bzl`, `test/unit/toolchain/toolchain_test.bzl`),
  rules_js 2, bazel-skylib 2, rules_go 1, rules_jvm_external 1 (`tests/unit/jvm_import/jvm_import_test.bzl`),
  rules_oci/rules_pkg/bazel-lib 0 — grep over clones; e.g. [rules_cc tests/cc/common/cc_link_action_test.bzl](https://github.com/bazelbuild/rules_cc/blob/main/tests/cc/common/cc_link_action_test.bzl),
  [rules_java test/java/common/rules/java_binary_tests.bzl](https://github.com/bazelbuild/rules_java/blob/master/test/java/common/rules/java_binary_tests.bzl)
- Rulesets wrap action subjects in domain-specific subjects kept under their test tree:
  rules_java `test/java/testutil/javac_action_subject.bzl` ("Bespoke rules_testing subject for the
  Java compilation action", built on `action_named("Javac")`, exposing `direct_dependencies()`,
  `javacopts()`, …); rules_cc `tests/cc/testutil/link_action_subject.bzl` (built on
  `action_generating("{package}/{name}{binary_extension}")`); rules_kotlin
  `src/test/starlark/core/plugin/kapt/kapt_test.bzl` uses `got_target.action_named(env.ctx.attr.mnemonic)` —
  [rules_java javac_action_subject.bzl](https://github.com/bazelbuild/rules_java/blob/master/test/java/testutil/javac_action_subject.bzl),
  [rules_cc link_action_subject.bzl](https://github.com/bazelbuild/rules_cc/blob/main/tests/cc/testutil/link_action_subject.bzl),
  [rules_kotlin kapt_test.bzl](https://github.com/bazelbuild/rules_kotlin/blob/master/src/test/starlark/core/plugin/kapt/kapt_test.bzl)
- rules_js `e2e/path_mapping/test.sh` (header): "Proves that the --bazel-bindir launcher flag …
  lets Bazel's path mapping share a single cached action between two builds that differ only in
  compilation mode. A shared --disk_cache is required: -c opt and -c fastbuild are different
  configurations… Only an explicit disk (or remote) cache lookup, keyed by the path-mapped action
  digest, can serve the second build's action from the first build's result." It runs
  `bazel build -c fastbuild … --disk_cache=$d --action_env=…INVALIDATE=$(date +%s)`, then
  `bazel build -c opt … --execution_log_json_file=$exec_log`, and `jq`-selects
  `.mnemonic == "BindirPathMappingCheck"` asserting `.cacheHit == "true"`; repeated for
  `JsRunBinaryPathMappingCheck` and a flag-controlled variant — [rules_js e2e/path_mapping/test.sh](https://github.com/aspect-build/rules_js/blob/main/e2e/path_mapping/test.sh)
- `--execution_log_compact_file` appears in rules_python only as a BuildBuddy CI flag
  (`buildbuddy.bazelrc` and a test that asserts the bazelrc contains it), not as a test oracle —
  [rules_python tests/workflows/setup_bazel_test.py](https://github.com/bazel-contrib/rules_python/blob/main/tests/workflows/setup_bazel_test.py)
- No other use of `execution_log` in rules_go, rules_rust, rules_apple, rules_oci, rules_cc,
  rules_java, rules_kotlin, rules_jvm_external, bazel-lib, rules_pkg, bazel-skylib, rules_testing — grep over clones
- rules_go `tests/integration/reproducibility`: "Verifies that the files generated when building a
  set of targets are identical, even when built from multiple copies of the same workspace"
  (pure `go_binary`, cgo c-archive, coverage `go_library`; notes a cgo executable is not
  reproducible on macOS) — [rules_go tests/integration/reproducibility/README.rst](https://github.com/bazel-contrib/rules_go/blob/master/tests/integration/reproducibility/README.rst)
- rules_rust `test/determinism/` is a `rust_binary` `determinism_tester` (blake3/walkdir based),
  exposed as `:tester`; no shell/test wrapper in the directory — [rules_rust test/determinism/BUILD.bazel](https://github.com/bazelbuild/rules_rust/blob/main/test/determinism/BUILD.bazel)
- Test names containing "cache" in rules_js (`js/private/test/js_binary_sh/`: `compile_cache_*_test`)
  and rules_python (`tests/bootstrap_impls:cached_venv_replaces_dangling_package_symlink_test`,
  `tests/uv/lock:cache_tests`, `tests/pypi/pypi_cache`) concern runtime/compile caches of the tools,
  not Bazel action caching — grep over clones
- Build-failure (execution-phase) tests are done by driving Bazel from a script or Go test:
  rules_rust `test/clippy/clippy_failure_tester.sh` ("Runs Bazel build commands over clippy rules,
  where some are expected to fail"; `check_build_result <expected rc> <target>` compares the exit
  code, run under `bazel run` using `BUILD_WORKSPACE_DIRECTORY`), similar `rustfmt_failure_tester.sh`;
  rules_go `go_bazel_test` tests inspect `*StderrExitError` (e.g. `tests/core/go_binary/configurable_attribute_bad_test.go`,
  `tests/core/go_test/test_fail_fast_test.go`); rules_apple shell tests via `apple_multi_shell_test`
  — [rules_rust clippy_failure_tester.sh](https://github.com/bazelbuild/rules_rust/blob/main/test/clippy/clippy_failure_tester.sh),
  [rules_go configurable_attribute_bad_test.go](https://github.com/bazel-contrib/rules_go/blob/master/tests/core/go_binary/configurable_attribute_bad_test.go)
- Analysis-failure tests: rules_cc `tests/rule_based_toolchain/testing_rules.bzl` defines
  `expect_failure_test(name, target, failure_message)`; rules_kotlin `src/test/starlark/core/plugin/test.bzl`
  has `_expect_failure`/`_expect_failure_contains`; both on rules_testing — [rules_cc testing_rules.bzl](https://github.com/bazelbuild/rules_cc/blob/main/tests/rule_based_toolchain/testing_rules.bzl)
- Skylib `analysistest.target_actions` returns `target.actions` captured by an aspect with a
  `# Validate?` comment and no documented restriction; the official page shows it inspecting
  `outputs` — [bazel-skylib lib/unittest.bzl](https://github.com/bazelbuild/bazel-skylib/blob/main/lib/unittest.bzl)

### Inferences
- Action-level analysis tests are universally treated as white-box: they live beside the ruleset's
  other internal tests (`tests/`, `test/`, `src/test/starlark`), use repo-internal subjects and
  mocks, and rely on in-repo visibility; none appear in the separate `e2e/`/`examples` modules.
- Cache-boundary behaviour is tested, when at all, at the Bazel-invocation level (shell driving two
  builds and reading the execution log), and such tests sit in the e2e/integration tier because
  they need a real Bazel server, disk cache and `jq`; the JSON execution log (`--execution_log_json_file`)
  was chosen over the compact binary log because it is `jq`-readable.

### Gaps
- No ruleset was found that asserts on action *keys* or uses `--execution_log_compact_file` as a
  test oracle; no test named "incremental" exercising edit-rebuild cycles was found in rules_go,
  rules_rust, rules_apple, rules_js or rules_oci (grep for `incremental|cache.?hit|action.?key|rebuild`
  in test trees).
- Whether rules_rust's `determinism_tester` is wired into CI could not be determined from the clone.

## KQ5: What does BCR `presubmit.yml` typically build/test for a ruleset?

### Takeaway
BCR presubmit has two layers: the anonymous-module `tasks` (build a few public targets of
`@<module>//...` from a generated `MODULE.bazel`) and the "highly recommended" `bcr_test_module`,
a sub-directory of the source archive with its own `MODULE.bazel` + `local_path_override` whose
`test_targets: ["//..."]` are run across a Bazel×platform matrix. rules-template, bazel-lib,
rules_oci use `e2e/smoke`; rules_js/rules_testing `e2e/bzlmod`; rules_python `examples/bzlmod`;
rules_jvm_external `examples/java-export`; rules_go `tests/bcr`; rules_rust `examples/hello_world`
via `working_directory`; rules_cc, rules_java, bazel-skylib, rules_kotlin, rules_proto, rules_pkg
only build `@module//<lang>/...` (no test module).

### Cited Findings
- BCR docs: "Every module version must pass the BCR presubmit… runs build and test targets specified
  in the `presubmit.yml`"; "Anonymous module test": targets in `tasks:` are built "when used as
  dependencies of a simple anonymous module" whose MODULE.bazel is `bazel_dep(name=…, version=…)`;
  "It's **highly recommended** to specify a test module that includes example usages of your
  module… A test module is located in a subdirectory of the extracted and patched source tree… A
  `MODULE.bazel` file should be in the test module directory, and it can depend on the target
  module with `local_path_override`. With the test module, you can introduce additional
  dependencies for testing without affecting the target module." Task syntax follows Bazel CI's
  pipeline config, one level deeper under `bcr_test_module`, with `module_path` and a mandatory
  `bazel` version per task; reproduce locally with `bazel run` of the registry's `//tools:setup_presubmit_repos -- --module <name>@<version>`;
  presubmit also runs Bazelisk `--migrate` against `incompatible_flags` — [BCR docs/README.md](https://github.com/bazelbuild/bazel-central-registry/blob/main/docs/README.md)
- Bazel CI task keys reused by presubmit.yml: `platform`, `bazel`, `build_targets`, `test_targets`,
  `run_targets`, `build_flags`, `test_flags`, `shell_commands`/`batch_commands`, `working_directory`
  ("Subdirectory containing a WORKSPACE file to test"), `environment`, `matrix` (with `exclude`) —
  [bazelbuild/continuous-integration buildkite/README.md](https://github.com/bazelbuild/continuous-integration/blob/master/buildkite/README.md)
- rules-template: `bcr_test_module: module_path: "e2e/smoke"`, `test_targets: ["//..."]`,
  Bazel `9.*`/`8.*`, four platforms — [rules-template .bcr/presubmit.yml](https://github.com/bazel-contrib/rules-template/blob/main/.bcr/presubmit.yml)
- bazel-lib: `e2e/smoke`, `test_targets: ["//..."]`, Bazel 7.x/8.x/9.x/rolling; `e2e/smoke/MODULE.bazel`
  uses `bazel_dep(name = "bazel_lib", version = "0.0.0", dev_dependency = True)` + `local_path_override` —
  [bazel-lib .bcr/presubmit.yml](https://github.com/bazel-contrib/bazel-lib/blob/main/.bcr/presubmit.yml)
- rules_oci: `e2e/smoke`, Bazel 6.x/7.x/8.x; a macOS task excludes `-//:test`, `-//:docker_created`,
  `-//:test_created` ("requires a docker daemon, not available on BCR CI") — [rules_oci .bcr/presubmit.yml](https://github.com/bazel-contrib/rules_oci/blob/main/.bcr/presubmit.yml)
- rules_js: `e2e/bzlmod`, `test_targets: ["//..."]`, Bazel 7.x/8.x/9.x — [rules_js .bcr/presubmit.yml](https://github.com/aspect-build/rules_js/blob/main/.bcr/presubmit.yml)
- rules_testing: `e2e/bzlmod`, Bazel 6.x/7.x — [rules_testing .bcr/presubmit.yml](https://github.com/bazelbuild/rules_testing/blob/main/.bcr/presubmit.yml)
- rules_python: `examples/bzlmod`, `build_targets` and `test_targets: ["//..."]`, Bazel 7.x/8.x/9.x,
  `test_flags` with `--keep_going` and C++17 opts — [rules_python .bcr/presubmit.yml](https://github.com/bazel-contrib/rules_python/blob/main/.bcr/presubmit.yml)
- rules_go: anonymous-module task builds `@rules_go//go/tools/bzltestutil/...`; `bcr_test_module:
  module_path: tests/bcr` builds `//...` + `@go_default_sdk//...` and tests `//...` on Bazel 7.*/8.*/9.*;
  `tests/bcr/MODULE.bazel` is `module(name = "rules_go_bcr_tests")` with
  `bazel_dep(name = "rules_go", version = "", repo_name = "my_rules_go")` + `local_path_override(path = "../..")`
  and a nested `other_module` — [rules_go .bcr/presubmit.yml](https://github.com/bazel-contrib/rules_go/blob/master/.bcr/presubmit.yml),
  [rules_go tests/bcr/MODULE.bazel](https://github.com/bazel-contrib/rules_go/blob/master/tests/bcr/MODULE.bazel)
- rules_rust: `module_path: ""` with `working_directory: examples/hello_world`, `run_targets`
  (`//third-party-in-workspace:vendor`, `@rules_rust//tools/rust_analyzer:gen_rust_project`),
  `test_targets: ["//..."]`, a `shell_commands` step removing `MODULE.bazel.lock`, and a second
  `bcr_test_module_windows` block — [rules_rust .bcr/presubmit.yml](https://github.com/bazelbuild/rules_rust/blob/main/.bcr/presubmit.yml)
- rules_jvm_external: anonymous task builds `@rules_jvm_external//:implementation` and
  `//private/tools/java/...`; `bcr_test_module: module_path: examples/java-export`; declares
  `incompatible_flags` — [rules_jvm_external .bcr/presubmit.yml](https://github.com/bazelbuild/rules_jvm_external/blob/master/.bcr/presubmit.yml)
- Build-only presubmits: rules_cc `@rules_cc//cc/...`; rules_java `@rules_java//java/...`;
  bazel-skylib `@bazel_skylib//...`; rules_kotlin `@rules_kotlin//kotlin/...` + `//src/...`;
  rules_proto `@rules_proto//proto/...`; rules_pkg `@rules_pkg//...` minus toolchains and
  `make_rpm`; rules_apple tests one target `@rules_apple//examples/macos/CommandLine:ExamplesBuildTest`
  on macos_arm64 — [rules_cc](https://github.com/bazelbuild/rules_cc/blob/main/.bcr/presubmit.yml),
  [rules_java](https://github.com/bazelbuild/rules_java/blob/master/.bcr/presubmit.yml),
  [bazel-skylib](https://github.com/bazelbuild/bazel-skylib/blob/main/.bcr/presubmit.yml),
  [rules_kotlin](https://github.com/bazelbuild/rules_kotlin/blob/master/.bcr/presubmit.yml),
  [rules_pkg](https://github.com/bazelbuild/rules_pkg/blob/main/.bcr/presubmit.yml),
  [rules_apple](https://github.com/bazelbuild/rules_apple/blob/master/.bcr/presubmit.yml)
- rules_bazel_integration_test: `module_path: ""`, tests `//bazel_integration_test/bzlmod/...` on
  Bazel 8.2.1 — [rules_bazel_integration_test .bcr/presubmit.yml](https://github.com/bazel-contrib/rules_bazel_integration_test/blob/main/.bcr/presubmit.yml)

### Inferences
- The `bcr_test_module` directory is the ruleset's declared consumer-facing test: it is the only
  place where the ruleset is exercised as an external `bazel_dep` and therefore the only place
  where load visibility, target visibility and the public `bzl_library` surface are verified
  end-to-end. Rulesets that only list `build_targets` for `@module//lang/...` get no such check from
  BCR.
- Aspect/bazel-contrib rulesets converge on `e2e/<name>` directories (several modules per repo:
  rules_oci `e2e/{assertion,smoke,wasm}`, bazel-lib `e2e/{smoke,copy_action,...}`), while
  bazelbuild rulesets reuse `examples/` or `tests/bcr`.

### Gaps
- The BCR `docs/` tree has no dedicated `bcr_test_module.md`; all guidance is in `docs/README.md`.
  Whether BCR maintainers require a test module for new modules (vs. recommend) is not stated beyond
  "highly recommended".

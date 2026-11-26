# Verification architecture

This page owns where a ruleset test lives, which form it takes, what it may depend on, what
it may claim and how it is named. It also owns the boundary rules between the ruleset and its consumer
modules, the coverage and altitude expectations, and the decisions on verifications that the
surveyed Bazel rulesets do not have. Read it when you add a test or review the tests of a
change. The [verification policy](verification.md) owns when to verify, the test-driven
cycle and evidence reuse. [Selection and lanes](verification-platforms.md) owns which lane
runs what. Tests inside a user's own project follow
[test ownership](../../rules_godot/docs/public/project-layout.md#test-ownership).

## Choosing a test kind

Answer these questions in order for the behavior a change adds or fixes. The first yes
selects the kind. The lowest number wins.

1. Does the behavior belong to an example's own feature? Write an
   [example test](#example-test).
2. Is it a tool that serves the repository rather than a build, such as a check, a CI script
   or a setup tool? Write a [repository-tooling test](#repository-tooling-test).
3. Is it pure Starlark logic without rule context, including what a module extension or a
   repository rule does with its tags, attributes and context? Write a
   [Starlark unit test](#starlark-unit-test).
4. Is it visible in providers, actions or analysis errors? Write an
   [analysis test](#analysis-test). This includes which inputs an action reads, the evidence
   for cache reuse and invalidation.
5. Is it a build tool's own logic on given inputs? Write a
   [build-tool unit test](#build-tool-unit-test).
6. Is it visible in a built output? Write a [build-output test](#build-output-test).
7. Is it visible only when Godot or the exported application runs? Write a
   [run test](#run-test).
8. Is it the claim that a user can do it with the public API on a platform? Write a
   [consumer scenario](#consumer-scenario).

Questions 3 to 7 follow altitude order, so the first match is the lowest altitude that
observes the failure. Add a consumer scenario only for a claim that questions 3 to 7 cannot
make. A behavior that no question reaches has no test kind; see
[verifications without precedent](#verifications-without-precedent).

## Test kinds

| Kind | Module and package | Form | Allowed dependencies |
|---|---|---|---|
| Starlark unit test | Ruleset, `<impl>/tests/` | rules_testing `unit_test` | Private `.bzl` files of the package under test, and mocked contexts in `tests` packages |
| Analysis test | Ruleset, `<impl>/tests/` | rules_testing `analysis_test` | Private files, fixture targets, test transitions and toolchains in `tests` packages |
| Build-tool unit test | Ruleset, `tools/<area>/tests/` | `py_test` | The tool's library and test data |
| Build-output test | Ruleset, `<impl>/tests/` | Inspection `py_test` or a test rule over built fixture outputs | Private files, fixtures, transitions, tool libraries, an engine |
| Run test | Ruleset, `<impl>/tests/` | `godot_test`, GdUnit or a launcher over an exported application | As for build-output tests |
| Consumer scenario | `e2e/rules_godot/` in the root module, one package per scenario | Public test rules, `build_test`, the artifact test rules | Public API and the artifact test rules |
| Example test | `examples/`, owned by the example | The example's own tests | Public API only |
| Repository-tooling test | Root module `autoload_dev`, beside the tool in `tools/<tool>/` | `py_test` or `unittest` | The tool's library |

`<impl>` is the implementation package under test, such as `godot/private` or
`godot/platforms/private`. Starlark unit tests through run tests are white-box tests.
rules_testing is a `dev_dependency`; bazel_skylib remains a regular dependency for non-test
code.

### Starlark unit test

- **Location**: The ruleset module, in the `tests` subpackage of the package whose `.bzl`
  logic it tests.
- **Form**: rules_testing `unit_test`.
- **Allowed dependencies**: The private `.bzl` files of the package under test, and mocked
  `module_ctx`, `repository_ctx` and `File` structs in the ruleset's `tests` packages.
- **May prove**: Pure Starlark logic: parsing, tables, label arithmetic, version comparison.
  For a module extension or a repository rule: which repositories its tags declare with which
  attributes, how it settles requests from several modules, each documented error, and the
  command lines it passes to `execute`. The logic under test takes its context and a `_fail`
  parameter, so the test calls it with a mock and collects errors instead of stopping.
- **May not claim**: How a rule uses that logic. An analysis test makes that claim. How Bazel
  resolves, maps and fetches the declared repositories, and what an external command does
  with the arguments it receives.
- **Evidence**: rules_cc, rules_java and rules_python declare rules_testing as a dev
  dependency. Bazel's [rule testing guide](https://bazel.build/rules/testing) names it
  beside skylib. rules_python tests its module extensions this way: `tests/support/mocks`
  holds mocks for `repository_ctx`, `module_ctx` and `File`, and `tests/python/python_tests.bzl`
  calls `parse_modules(module_ctx = ..., _fail = errors.append)`. Bazel-in-Bazel harnesses
  such as rules_go's `go_bazel_test` and rules_python's `tests/integration` see the real
  repository phase, but they run `local` and `exclusive`, outside remote execution, and
  rules_python moved such tests back into the build
  ([rules_python #2095](https://github.com/bazel-contrib/rules_python/pull/2095)).

### Analysis test

- **Location**: The ruleset module, in the `tests` subpackage of the implementation package.
- **Form**: rules_testing `analysis_test`, including expected failures.
- **Allowed dependencies**: Private files, fixture targets, test transitions and test
  toolchains defined in `tests` packages of the ruleset.
- **May prove**: Providers and their fields, actions with mnemonic, arguments, inputs and
  outputs, and analysis errors. An action's declared inputs are the evidence that a relevant
  change reruns it and an unrelated change does not.
- **May not claim**: What an action produces or whether it succeeds. A build-output test
  makes that claim.
- **Evidence**: rules_apple, rules_kotlin, rules_java, rules_cc, rules_python, rules_rust and
  rules_go assert actions in analysis tests and keep them in the ruleset. The analysis phase
  cannot observe execution ([rule testing guide](https://bazel.build/rules/testing)).

### Build-tool unit test

- **Location**: The ruleset module, in `tools/<area>/tests/` of the tool's package.
- **Form**: `py_test`.
- **Allowed dependencies**: The tool's library and test data. No Godot binary.
- **May prove**: The tool's logic and its error messages on given inputs.
- **May not claim**: That Bazel calls the tool with those inputs. An analysis test makes
  that claim.
- **Evidence**: The surveyed rulesets test their build tools as ordinary language tests inside
  the ruleset module, as rules_python does with `py_test`.

### Build-output test

- **Location**: The ruleset module, in the `tests` subpackage of the implementation package
  whose outputs it inspects.
- **Form**: An inspection `py_test` or a test rule that consumes the built outputs of fixture
  targets.
- **Allowed dependencies**: Private files, fixtures, transitions, tool libraries and an
  engine.
- **May prove**: The contents of real outputs in one configuration: pack members, library
  selection, symbols, metadata and determinism across two runs of a tool.
- **May not claim**: How the output behaves when it runs. A run test makes that claim.
- **Evidence**: rules_apple `apple_verification_test` and rules_pkg `verify_archive_test`
  inspect real outputs inside `bazel test`. rules_go and rules_rust compare repeated outputs
  for determinism. rules_godot inspects four target platforms, which the surveyed rulesets do
  only partially. This kind covers that inspection on rules_godot's own terms.

### Run test

- **Location**: The ruleset module, in the `tests` subpackage of the implementation package
  whose result it runs.
- **Form**: `godot_test`, a GdUnit suite or a launcher over an exported desktop application.
- **Allowed dependencies**: As for build-output tests.
- **May prove**: What Godot or an exported desktop application does with the outputs.
- **May not claim**: Behavior on a mobile device. That is mobile runtime acceptance in the
  [verification policy](verification.md#verification-kinds) and has no automated kind.
- **Evidence**: Bazel runs every test target as an execution with declared inputs. Exports
  through Godot's editor have no relative among the surveyed rulesets, so the kind is defined
  on rules_godot's terms.

### Consumer scenario

- **Location**: `e2e/rules_godot/` in the repository's root module, one package per scenario.
- **Form**: Public test rules, `build_test` and the [artifact test rules](#artifact-test-rules).
- **Allowed dependencies**: The public API and the artifact test rules.
- **May prove**: That a user can build, inspect and run what the scenario declares through
  the public API.
- **May not claim**: Coverage of variants or error paths. Analysis and build-output tests in
  the ruleset make those claims.
- **Evidence**: The surveyed rulesets keep such tests in consumer modules: `e2e/<name>` in
  the Aspect family, `tests/bcr` in rules_go, `examples/bzlmod` in rules_python.

### Example test

- **Location**: `examples/`, in the example that owns the behavior.
- **Form**: The example's own tests, placed by
  [test ownership](../../rules_godot/docs/public/project-layout.md#test-ownership).
- **Allowed dependencies**: The public API only.
- **May prove**: The example's own behavior.
- **May not claim**: Ruleset coverage. Examples demonstrate the ruleset and are not a
  coverage matrix ([example scope](../../examples/AGENTS.md#scope-and-design)).
- **Evidence**: rules_python, rules_rust and rules_jvm_external keep their examples as
  consumer modules with their own tests.
- **Altitude**: Outside the altitude order.

### Repository-tooling test

- **Location**: The root module `autoload_dev`, beside the tool in its package
  `tools/<tool>/`, as `tools/conventions` does.
- **Form**: `py_test` or `unittest`.
- **Allowed dependencies**: The tool's library.
- **May prove**: That a check, CI script or setup tool behaves as specified.
- **May not claim**: Anything about the ruleset's builds. The kinds above make those claims.
- **Evidence**: The survey does not compare repository tooling. The kind exists so that every
  test in the repository has one place.
- **Altitude**: Outside the altitude order.

## Test size

A test's `size` follows [Bazel's meaning](https://bazel.build/reference/test-encyclopedia):
the resources and default timeout of running it, with unit tests `small`, integration tests
`medium` and end-to-end tests `large` or `enormous`. It does not count the cost of building
the test's dependencies. For the kinds above:

| Kind | Size |
|---|---|
| Starlark unit test, analysis test | No effect: they run no action. They start no Godot process, so they are fast tests |
| Build-tool unit test, repository-tooling test | `small` |
| Build-output test, run test | `medium`: it builds or runs Godot |
| Consumer scenario, example test | `medium` or `large`, as their run time needs |

To check sizes against run times, run the tests in question with
`--test_verbose_timeout_warnings`; it is not on by default, because it would flag every
analysis test.

Size says nothing about the cost of a test's build, so it does not select the fast tests.
A test whose build or run starts a Godot process carries the `godot_process` tag
([RG026](conventions.md#rg026)); the ruleset's fast tests, `bazel test --config=fast //...`,
which the pre-push hook runs, are every other test. The `smoke` tag marks the few
integration tests that run with them anyway, as Bazel's encyclopedia defines it: run before
committing code changes. A smoke test carries no `godot_process` tag. Keep it to an
end-to-end path whose failure the other fast tests would miss.

## Ruleset and consumer modules

A test belongs to a consumer module only if a user could write it with the public API. Every
other test belongs to the ruleset module, in the `tests` subpackage of the implementation
package it tests. Fixtures that serve several packages go to the package whose behavior they
reproduce. The ruleset module has no second test tree at its root.

The reason is Bazel's visibility model. [Load visibility](https://bazel.build/concepts/visibility#load-visibility)
names packages of the same repository only, so another module can reach a private file
only through a public re-export. Every surveyed ruleset with white-box infrastructure keeps
those tests in its own module. The consumers need only another repository than the
ruleset's, so they live in the repository's root module, which sees the ruleset as
`@autoload_rules_godot` and runs them in one Bazel server with the tooling.

| Location | Purpose | Contents |
|---|---|---|
| `autoload_rules_godot` at `rules_godot/` | The ruleset and its white-box tests | `godot/**/tests/`, `tools/**/tests/` |
| `autoload_dev`, the repository root, `tools/` | The repository's tooling and its tests | Tooling tests beside their tools in `tools/` |
| `autoload_dev`, `examples/` | Demonstrations of the ruleset, each with tests for its own behavior | Example tests |
| `autoload_dev`, `e2e/rules_godot/` | What a user can do with the public API | One smoke scenario per platform and focused consumer scenarios |
| `autoload_<module>` at `addons/<module>/` | An add-on module and the unit tests of its code | Add-on unit tests beside their unit, `bcr/smoke/` |
| `autoload_dev`, `e2e/addons/<module>/` | What an application can do with an add-on module | Add-on end-to-end tests: one test project per module, suites in topic packages |

### Add-on module tests

The add-on modules follow the same split by how a test runs, with four kinds that
[add-on guidance](../../addons/AGENTS.md#lanes) places:

| Kind | Location | Form |
|---|---|---|
| Add-on unit test | The add-on module, beside the unit or in its `tests/<unit>/` | The language's test tool, such as `cc_test` or `py_test`, without a Godot project, on regular dependencies only: the lanes build the module from the root module, where its development dependencies are not active |
| Add-on end-to-end test | `e2e/addons/<module>/` in the root module | Godot runs or project builds through the module's public targets, such as GdUnit suites |
| Demo test | `examples/addons/<module>/tests/` | Checks of the example application itself, such as its exported pack running headless |
| Registry test module | `bcr/<name>/` of every released module ([RG020](conventions.md#rg020)) | A consumer module that the registry builds from the release archive |

The public rules of `@autoload_<module>`, such as `gdunit_test`, are tested from
`e2e/addons/<module>/` like any other end-to-end claim: an add-on module runs no Godot
([RG021](conventions.md#rg021)).

This keeps [design principle V](../../rules_godot/docs/internal/principles.md#v-examples-demonstrate-test-projects-isolate): examples stay focused demonstrations, and ruleset tests
stay out of them with a small scope.

## Boundary rules

| Rule | Statement | Enforcement | Exceptions |
|---|---|---|---|
| B1 | A consumer module loads and depends on public API labels only. Public API is what the [API reference](../../rules_godot/docs/internal/api-reference.md) documents and its inventory lists. | Bazel load visibility on private `.bzl` files and package visibility on private targets | None |
| B2 | A `tests` package of the ruleset is visible only inside the ruleset module. | Bazel visibility: `//godot:__subpackages__`, `//tools:__subpackages__` or load visibility | None |
| B3 | Consumer scenarios load no private module but the artifact test rules, which are classified as cross-repository modules. | The API inventory check | None |
| C1 | No two consumer scenarios make the same claim. A smoke path exists once per platform. | Review. The claim is semantic, so no checker can compare it. | None |
| L1 | Each test has exactly one owning lane, derived from its module, its kind and the Bazel configuration it needs. Ruleset tests belong to the lane that runs the ruleset's desktop set, and repository-tooling tests to the `quality` lane. A consumer scenario belongs to the lane of its platform configuration. A lane does not rerun another lane's tests. | Review. [Selection and lanes](verification-platforms.md) names the concrete task of each lane class. | None |

B1 and B2 need no convention rule. Bazel rejects a load or a dependency outside the declared
visibility, as rules_cc, rules_apple and rules_java use it. Lanes select tests; packages own
them. A configuration suite is a lane's entry point and lists consumer scenarios only. Where
suites are declared is a lane decision.

## Artifact test rules

`godot/private/testing` holds `android_bundle_test` and `ios_app_test`, which inspect a
built App Bundle or iOS application. They are not supported API: as in rules_apple and
rules_android, inspection rules serve the ruleset's own tests. White-box tests and the
smoke scenarios `e2e/rules_godot/smoke/android` and `e2e/rules_godot/smoke/ios` load them; the root
module loads them across repositories, so they keep public load visibility and are classified as
cross-repository modules. They carry their own inspectors instead of loading
`tools/platforms`.

White-box tests depend on tool libraries such as `//tools:pck_lib` directly; those stay
private to the ruleset under B2.

## Coverage

Coverage is a list of required test kinds per kind of public surface, with what each must
show. It names observable properties, not line counts. No surveyed ruleset measures Starlark
coverage.

| Surface | Required kinds | Must show |
|---|---|---|
| Public rule | Analysis test | Each attribute's effect on providers or actions, each documented error as an expected failure |
| Public rule with outputs a user consumes | Build-output test | Each output's contents in each configuration that changes them, such as debug, release and stripped |
| Public macro | Analysis test of the targets it creates | The generated targets and their wiring, each documented error |
| Provider | Analysis test of each producing rule | Each documented field |
| Module extension or repository rule | Starlark unit test with a mocked context | Each tag's or attribute's effect on the declared repositories, each documented error. The success path through Bazel's repository phase is shown by a consumer scenario that uses it. |
| Build tool | Build-tool unit test | Each behavior and error the tool documents. A tool that drives Godot also needs one build-output or run test through its rule. |
| Platform | Consumer scenario | One smoke path: build, inspect with public helpers, run where the host allows |
| Public test helper | Consumer scenario | That a user can load and use it |
| Repository tool | Repository-tooling test | Each check or rule, with adjacent regression cases as the [rule framework](conventions.md#rule-framework) requires |

The API contract cases in `godot/tests/api_contracts` give each public API a representative
configuration that the contract check runs against its documentation. They are the
mechanical floor of public-rule coverage, not a substitute for the analysis tests above.

## Altitude

Most tests are Starlark unit tests, analysis tests and build-tool unit tests. Build-output
and run tests exist where an output or a run is the behavior at risk. Variants such as debug,
release and stripped are verified there, at the lowest altitude that observes them. The
scenarios hold one smoke path per platform plus focused scenarios. The rule is
qualitative and sets no ratio.

rules_python and rules_apple keep hundreds of test files in the ruleset and one to three
consumer modules. GitHub bills macOS runners at ten times Linux, which is why the Aspect
family runs them only on `main`. A small consumer layer is also the cheap one.

## Methodology

1. Choose the kind with [the question list](#choosing-a-test-kind).
2. Start the [test-driven cycle](verification.md#selecting-tests-and-reviewing-changes)
   with a failing test of that kind. If the kind cannot run locally, the policy's gap rule
   applies.
3. Name the test, its files and its fixtures by [naming](#naming).

A test package that holds more than one fixture project has a README with one section per
fixture, saying what it reproduces. rules_go keeps such a README per test folder.

## Naming

A name states what its test proves or what its fixture reproduces, in the
[glossary's](glossary.md) terms and by its [naming rules](glossary.md#naming-rules).

| Name | Rule | Example |
|---|---|---|
| Test target | The claim it proves: the subject, then the expected behavior, ending in `_test`. A variant of the same claim adds its configuration as a qualifier. The tests of a rules_testing suite take their function's name instead, `test_<claim>`. | `release_pack_excludes_gdunit_test`, `ios_app_links_extension_test` |
| rules_testing test | A private function `_test_<claim>`. The targets it arranges take the test's name as a prefix and the tag `manual`. | `_test_pack_reads_declared_imports` |
| Starlark test file and suite | `<subject>_tests.bzl`, which exports `<subject>_test_suite`. The package's BUILD file instantiates the suite under that name. | `pack_tests.bzl`, `pack_test_suite` |
| Python test | `<module>_test.py` for the module it tests, with methods `test_<claim>` | `godot_actions_test.py`, `test_rejects_missing_preset` |
| `tests` subpackage | `<impl>/tests/`. The tests of one rule may get their own subpackage, named after the rule's glossary term. | `godot/private/tests/pack/` |
| Fixture | What it reproduces, not the test that uses it | `project_with_disabled_extension` |
| Consumer scenario | The package names what the user does. The smoke paths are `e2e/rules_godot/smoke/<operating_system>`. | `e2e/rules_godot/smoke/android`, `e2e/rules_godot/script_run` |

A word that states no claim on its own, such as `contract`, `regression`, `misc` or `basic`,
is not a name or a name's only qualifier, and neither is a number.

Bazel's [BUILD style guide](https://bazel.build/build/style-guide) asks for descriptive
snake_case names, the `_test` suffix, a suffix per variant and no meaningless suffixes.
[rules_testing](https://rules-testing.readthedocs.io/en/latest/analysis_tests.html) names
test functions after the behavior they test, prefixes arranged targets with the test's name
and puts each rule's tests in their own directory. rules_go keeps `<subject>_tests.bzl` files
that export `*_test_suite` functions, and rules_oci names its consumer smoke module
`e2e/smoke`. Ours live in `bcr/<name>/` of each released module, so that a registry test
module is recognizable by its place (RG020). The `test_` prefix is what Python's `unittest` discovers.

## Verifications without precedent

**Rule P1**: A verification that no surveyed ruleset has is removed. It stays only if a MUST
of the [design principles](../../rules_godot/docs/internal/principles.md) requires it and no kind on this page can satisfy that MUST. A removal
names the kind that carries its claim, or says that none does.

| Verification | Decision | Replacement | Reason |
|---|---|---|---|
| Incrementality and bundle-reuse experiments | Removed | Analysis tests of action inputs, and build-output tests of determinism for actions whose outputs feed others | Bazel reruns an action only when its declared inputs or command change, and a downstream action stays cached when an upstream output is byte-identical. Inputs and determinism together prove both sides. Every surveyed ruleset asserts action inputs. The one execution-log test, rules_js `e2e/path_mapping/test.sh`, is a single script. |
| Capability experiments | Removed | Analysis tests of membership and import action inputs | Same claim and replacement as incrementality |
| Desktop-set guard against Android repository fetches | Removed | None. The scenarios' desktop set runs without an Android SDK, so a desktop scenario that needs Android fails there. | What remains is a cost claim about unneeded fetches. No surveyed ruleset guards fetches. |
| Isolation test in a temporary consumer without mobile toolchains | Removed | Consumer scenarios for visibility. Analysis tests for toolchain resolution without mobile toolchains, using test toolchains in the ruleset's `tests` packages. | Its claims split into two existing kinds. A whole module that registers no mobile toolchain has a precedent only as a BCR smoke module; rules_godot's `bcr/smoke` is that module and registers only the prebuilt desktop engine. |
| Reproducibility experiment | Rewritten | A build-output test that imports and exports a fixture twice in its sandbox and compares the digests | rules_go's reproducibility test and rules_rust's `determinism_tester` are relatives. If one test cannot run the import twice, a test-only rule runs the tool in two actions that differ only in an unused salt input. |
| Fetch and re-evaluation checks of the engine module extension in a fresh consumer module | Removed | None. Its tag evaluation, conflicts and errors become Starlark unit tests with a mocked `module_ctx`. | What remains is that no recipe repository is fetched and that a second evaluation after `clean --expunge` gives the same toolchains. No surveyed ruleset guards fetches or re-evaluates an extension. |
| Automated public-API check (RG005) | Removed | Load visibility and target visibility (B1, B2) | No surveyed ruleset automates this check, while rules_cc, rules_apple and rules_java enforce the same boundary through Bazel |

The design principles require that changes to dependency modeling or invalidation validate both
sides. Action-input analysis tests show both sides, and determinism tests show that unchanged
inputs give unchanged outputs. A performance claim in a change still needs observations such
as executed actions. Collect them for that change with Bazel's
[execution-log comparison](https://bazel.build/remote/cache-remote) and report them as review
evidence under the [verification policy](verification.md#selecting-tests-and-reviewing-changes).

Risks remain. An undeclared input that an action reads is invisible to analysis tests.
Sandboxed and remote execution turn it into a build failure, and every rules_godot action runs
sandboxed except macOS keychain signing, which is also uncached. A consumer that registers no
mobile toolchain at all is not tested by any kind. The failure paths of the repository phase
are tested against mocked contexts only, so a mock that differs from Bazel's real context
hides a fault until a consumer scenario reaches that path.

## Execution-time failures

No kind checks that a build fails during execution, and no harness runs such builds. A failure
found at execution is tested where its cause lives. A tool's rejection of an input is a
build-tool unit test of that error. A rule that can detect the case during analysis gets an
analysis test with an expected failure. Rulesets that test failing builds from outside, such
as rules_rust and rules_oci, use scripts. rules_python moved such sub-Bazel tests back into
the build because they were expensive and hard to debug
([rules_python #2095](https://github.com/bazel-contrib/rules_python/pull/2095)).

## Evidence

The comparisons on this page come from a survey of 17 Bazel rulesets, snapshot 2026-11-06.
Bazel sources are the [rule testing guide](https://bazel.build/rules/testing),
[visibility](https://bazel.build/concepts/visibility) and
[remote cache debugging](https://bazel.build/remote/cache-remote). The rules_testing users
were read from the `MODULE.bazel` files of rules_cc, rules_java and rules_python on
2026-11-06.

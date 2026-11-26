# Repository Verification

This page owns the repository's general review, testing and verification policy. Read it
when making or reviewing a change; the hosts and recipes are linked below.
Agent instructions link here; public guides explain supported consumer workflows. The
[design principles](../../rules_godot/docs/internal/principles.md) govern what a change must validate. A concrete acceptance requirement can
add a check; the existence of a capability, task or operating system does not require every combination.

The objective is enough evidence to accept the change with the least repeated work. Select
checks for the behavior and failure modes affected, reuse valid results, and stop when the
required evidence is available. Missing prerequisites are a reported gap, not a reason to
silently claim success or build a new test framework.

## When to verify

| Boundary | Required work | Work not required merely by reaching this boundary |
|---|---|---|
| Before editing | Read the applicable instructions and identify the affected behavior | Baseline builds or tests, unless needed to reproduce a defect or distinguish an existing failure |
| During editing | Follow the test-first cycle below for behavior changes; use focused checks when their feedback helps the next decision | A suite after every file edit; rerunning successful checks with unchanged relevant inputs |
| Before claiming a local change complete | Review the diff; run the smallest existing behavior check that addresses the change | Every host's tests, a clean rebuild, or a new test for every edit |
| Before committing | Keep the pre-commit hook (`aspect bootstrap` installs it) enabled; it formats and restages the staged files, regenerates the lock files they shape and reviews the staged change's Code Health; retain relevant evidence | A second suite just because a commit is about to happen |
| Before pushing | Keep the pre-push hook (`aspect bootstrap` installs it) enabled; it runs `aspect check` ([`.aspect/develop.axl`](../../.aspect/develop.axl)) on the pushed checkout: the formatter, then `bazel test --config=check --config=fast //...` in the root module and the ruleset, which lints and runs the fast tests and every check that is a Bazel target, then the checks that are no Bazel tests, since they read the whole checkout, at once: Gazelle's and the conventions tool's, and the branch's Code Health. Bazel's caches skip what the change does not reach; the formatter covers the files changed since the merge base with `origin/main` | App builds, tests tagged `godot_process`, `android` or `ios` and cache experiments in the hook |
| PR/review readiness | Require CI's results, the [macOS job](verification-platforms.md#apple-hosts) included | Duplicating CI suites locally once CI is the execution environment |
| Merging | The merge queue runs both host jobs, the macOS job included, on the result of the merge, and saves the caches later runs read; main receives that commit unchanged, with the queue's checks | A second run on main |
| Status update, question or partial handoff | State relevant pending/failed checks if they affect the handoff | Running checks just to send a message or finish a turn |

A local completion report can say CI verification is pending. It is not a merge-ready
claim. Do not wait for unrelated checks before asking a question. If no code or configuration
changed, a read-only review does not require test execution.

The fast tests are the tests of the root module and the ruleset that start no Godot process,
their `smoke` tests included: `bazel test --config=fast //...` in each, or `aspect tests`
([test size](verification-architecture.md#test-size)). CI runs every host's job on every run; to
verify one locally, run `aspect ci linux` or `aspect ci macos`, or single `aspect work`
pieces. Do not
repeat a successful check merely because its changes were committed.

A result remains usable when its relevant source, dependencies, configuration and execution
environment are unchanged. Bazel's normal cache is valid evidence; a cached test is not a
reason to force execution. New edits, a failed check, a toolchain/environment change or a
specific unresolved concern justify rerunning affected work. Clean builds and cache bypasses
are reserved for cache/reproducibility work or a concrete stale-result investigation.

## Verification kinds

These kinds answer different questions. A command may perform several of them; `bazel test`
alone does not identify the kind because tests can inspect artifacts without launching apps.

| Kind | Evidence | Existing entry points |
|---|---|---|
| Source quality | Formatting, language/type diagnostics and repository conventions | `bazel build --config=lint` in each module, `--config=check` on any build or test, `bazel run //tools/conventions` |
| Setup validation | SDK requirements agree with consumers; the modules' shared pins agree; CI cleanup works | `bazel test //tools/android:requirements_test //tools/setup:pins_test //tools/ci:setup_action_test`, all in `aspect tests` |
| API/documentation contracts | Inventories, metadata, visibility and docstrings | `bazel test //godot/tests/api/... //godot/tests/api_contracts/...` in `rules_godot/` |
| Analysis and focused behavior tests | Declared dependencies, error paths, build-tool behavior | `bazel test //...` in `rules_godot/` (the white-box tests), `bazel test //e2e/rules_godot/...` (the regression scenarios); individual owning Bazel test targets |
| Source runs | GdUnit suites, native unit tests and example behavior, with the content validation of what they build | The examples' and add-on modules' test targets |
| Artifact build | A pack, desktop app, APK/AAB or IPA can be produced for the selected target platform | The tests tagged `android` or `ios`, and desktop targets |
| Artifact inspection | Pack members, ABI/library delivery, metadata, symbols and identifier matching | The ruleset's build-output tests; the consumer scenarios' tests tagged `android` or `ios` |
| Exported application execution | The actual desktop application starts and produces meaningful assertions | The ruleset's run tests; the desktop smoke scenarios in `//e2e/rules_godot/smoke/...`; `aspect work source-engine` |
| Action inputs and determinism | Required invalidation, unaffected reuse, deterministic imports/PCKs | The ruleset's action-input and reproducibility tests; execution-log comparison as per-change review evidence |
| Mobile runtime acceptance | Target operating-system behavior on a matching device/emulator/simulator | Focused manual acceptance when changed behavior needs it |
| Distribution acceptance | Signing/provisioning, installation policy or Store acceptance | Explicit feature/release scope; no default Store verification |
| Review | Correct behavior, sound design, requirements, useful documentation and scope | Diff and relevant owning implementation; automated passes do not establish semantics |

The [test kinds](verification-architecture.md#test-kinds) supply these verification kinds.
Starlark unit, analysis, build-tool unit and repository-tooling tests supply analysis and
focused behavior evidence. Build-output tests and consumer scenarios supply artifact
inspection. Run tests, example tests and consumer scenarios supply source runs and exported
application execution. Reproducibility is a build-output test, and action-input analysis
tests carry cache reuse and invalidation.

Environment preparation (`bootstrap` or `android:setup`) installs prerequisites; it is not
verification evidence. The setup tests use isolated SDK fixtures and do not provision an SDK
or build an app. Beta artifact inspections are ordinary Bazel tests with declared app, engine
and tool inputs; normal cached results are valid for those inputs.

Building an IPA does not establish that it launches. Inspecting a library does not establish
that its runtime integration works. A source run of a project is not a run of its packaged app.
Optimized code, a release engine, stripped output and retained debug symbols are independent
properties; use the named configurations in the [verification matrix](verification-platforms.md#supported-verification-matrix)
instead of assuming one `release` switch covers them all.

## Selecting tests and reviewing changes

Choose the test kind and its place with the
[verification architecture](verification-architecture.md#choosing-a-test-kind), which selects
the lowest altitude that reliably detects the relevant failure. Reuse an existing test or
fixture that follows it before adding another one. Test observable behavior and the failure it
prevents, not implementation structure or coverage counts.

Agents must use test-driven development (TDD) for behavior changes that need automated
coverage. Before changing production code, write or extend the smallest test expressing the
required behavior and run it. Confirm that it fails because the behavior is missing or wrong,
not because of broken setup. Then make the smallest implementation change that passes the
test. Refactor as needed while keeping the affected tests green. Derive expectations from the
requirement; do not implement first and then write tests to match the resulting code.

An existing test that already exposes the defect supplies the failing step; do not add a
duplicate. Preserve that regression coverage. Before replacing a test, check that the
replacement retains the relevant behavior and failure coverage. If prerequisites prevent
observing the failing step, report the gap rather than claiming the TDD cycle was verified.
TDD does not require repeating the verification matrix.

New behavior needs focused coverage where existing checks do not establish it. TDD does not
expand which changes need new tests: pure documentation edits, mechanical renames and
behavior-preserving moves do not by themselves require them; run the checks affected by
changed references.

Examples retain their own meaningful behavior tests under [design principle V](../../rules_godot/docs/internal/principles.md#v-examples-demonstrate-test-projects-isolate). Follow
[example scope](../../examples/AGENTS.md#scope-and-design) when changing them. Do not add a
mobile automation framework merely to complete verification.
For tests inside an example's or user's project, read [test ownership](../../rules_godot/docs/public/project-layout.md#test-ownership).
For the existing regression module's layout, use its [module guide](../../e2e/rules_godot/AGENTS.md).

Review the diff against the user's scope and applicable AGENTS.md files; for package or target
changes, also use the relevant [layout sections](../../rules_godot/docs/public/project-layout.md). Update rules or temporary exceptions made
obsolete by the change. Check English language, example focus/public API use and documentation
claims against the owning code. Report conflicts before implementing a conflicting decision.
Fix findings in their source; suppression comments are for intentional exceptions with a reason.

Public documentation describes supported behavior, requirements and established limitations.
Keep routine CI receipts, timings and device/signing evidence in the review or completion
report. A useful report names the checks/environment, outcome and remaining relevant gaps;
it does not need a new checked-in report or a checklist of every matrix cell.

## Choosing additional evidence

Default local checks are lightweight. Host-specific tests normally run in CI. When preparing a change for review or changing
build/runtime/toolchain behavior, read only the relevant rows and fallback conditions in
[verification hosts](verification-platforms.md). Do not expand a test across a Cartesian
product of hosts, targets, CPUs, engines or build modes.

For setup, API regeneration or a particular regression fixture, use the corresponding
[recipe](verification-recipes.md). These are on-demand instructions, not additional gates.
Verification scripts may save a report when useful; do not add routine receipts to reference
pages or create a separate verification cache, evidence database or per-commit receipt system.

# Repository Verification

This page owns the repository's general review, testing and verification policy. Read it
when making or reviewing a change; the lanes and recipes are linked below.
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
| Before claiming a local change complete | Review the diff; run the smallest existing behavior check that addresses the change | Every lane, a clean rebuild, or a new test for every edit |
| Before committing | Keep the pre-commit hook (`aspect bootstrap` installs it) enabled; it formats and restages the staged files, regenerates the lock files they shape and reviews the staged change's Code Health; retain relevant evidence | A second suite just because a commit is about to happen |
| Before pushing | Keep the pre-push hook (`aspect bootstrap` installs it) enabled; it checks the pushed checkout with what CI's quality and docs lanes check, plus the desktop lane's API contract cases, the fast tests and the branch's Code Health; [`.aspect/hooks.axl`](../../.aspect/hooks.axl) lists the steps. Lint, the generated files, the API documentation and its contract cases run only where their inputs changed, as [`tools/ci/work.py`](../../tools/ci/work.py) declares them: since the pushed branch's commit on the remote, as long as `HEAD` descends from it and the worktree's hook last passed on it; for a branch's first push, one that rewrites history the remote has not seen, or one over commits that reached the remote another way, such as a suggestion committed on GitHub, since the merge base with `origin/main` | App builds, non-desktop lane suites and cache experiments in the hook |
| PR/review readiness | Require CI's results, the [Apple lanes](verification-platforms.md#apple-lanes) included | Duplicating CI suites locally once CI is the execution environment |
| Merging | The merge queue runs every lane, including the Apple lanes, on the result of the merge, and saves the caches later runs read; main receives that commit unchanged, with the queue's checks | A second run on main |
| Status update, question or partial handoff | State relevant pending/failed checks if they affect the handoff | Running checks just to send a message or finish a turn |

A local completion report can say CI/lane verification is pending. It is not a merge-ready
claim. Do not wait for unrelated checks before asking a question. If no code or configuration
changed, a read-only review does not require test execution.

The fast tests are the `small`, analysis and `smoke` tests of the ruleset
([test size](verification-architecture.md#test-size)); the root module's tests run whole, as
in the quality lane. CI runs every lane on every run; to
verify a lane's work locally, run `aspect lane <lane>` or its `aspect work` pieces. Do not
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
| Source quality | Formatting, language/type diagnostics and repository conventions | `aspect work lint lint:gdscript lint:markdown`, `bazel run //tools/conventions` |
| Setup validation | SDK requirements agree with consumers; the modules' shared pins agree; CI cleanup works | `aspect work test:setup`, `bazel test //tools/ci:setup_action_test` |
| API/documentation contracts | Inventories, metadata, visibility and docstrings | `aspect work docs` |
| Analysis and focused behavior tests | Declared dependencies, error paths, build-tool behavior | `aspect work test:bazel` (the ruleset's white-box tests), `bazel test //...` in `e2e/rules_godot/` (the regression module's desktop set); individual owning Bazel test targets |
| Source runs | GdUnit suites, native unit tests and example behavior, with the content validation of what they build | Selected `test:example:*` tasks; public test targets |
| Artifact build | A pack, desktop app, APK/AAB or IPA can be produced for the selected target platform | The `android` and `ios` work and desktop targets |
| Artifact inspection | Pack members, ABI/library delivery, metadata, symbols and identifier matching | The build-output tests in the work `test:bazel`; the consumer module's configuration suites in the `android`/`ios` work |
| Exported application execution | The actual desktop application starts and produces meaningful assertions | The run tests in the work `test:bazel`; the desktop smoke scenarios in `test:gdextension`; `aspect work source-engine` |
| Action inputs and determinism | Required invalidation, unaffected reuse, deterministic imports/PCKs | The action-input and reproducibility tests in the work `test:bazel`; execution-log comparison as per-change review evidence |
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

Default local checks are lightweight. Lane suites normally run in CI. When preparing a change for review or changing
build/runtime/toolchain behavior, read only the relevant rows and fallback conditions in
[verification lanes](verification-platforms.md). Do not expand a test across a Cartesian
product of hosts, targets, CPUs, engines or build modes.

For setup, API regeneration or a particular regression fixture, use the corresponding
[recipe](verification-recipes.md). These are on-demand instructions, not additional gates.
Verification scripts may save a report when useful; do not add routine receipts to reference
pages or create a separate verification cache, evidence database or per-commit receipt system.

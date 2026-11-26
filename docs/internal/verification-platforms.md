# Verification lanes

Read this page when deciding which lanes a change needs locally, preparing a change for review, or changing
verification tooling. The [verification policy](verification.md) owns timing, TDD and reuse;
[recipes](verification-recipes.md) describe setup and individual fixtures.

## Supported verification matrix

This is the maintained representative verification set, not a Cartesian product. Product
support and acquisition availability remain in [platform setup](../../rules_godot/docs/public/platforms.md),
[versions](../../rules_godot/docs/public/versions.md) and [engines](../../rules_godot/docs/public/engine.md). A missing matrix cell
creates no automatic obligation to add it. Do not infer that all CPUs or upstream
Godot features are covered from one passing cell.

| Target / workflow | Where it runs | Representative engine/configuration | Required evidence when affected |
|---|---|---|---|
| Linux desktop: ruleset behavior and desktop app | Linux CI; local Linux for focused feedback | CI runner CPU, pinned prebuilt engine; default build configuration | Selected desktop tests, example checks/suites and exported-app assertions |
| macOS desktop: ruleset behavior and desktop app | macOS CI; local macOS for focused feedback | Host CPU, pinned prebuilt engine; default build configuration | Selected desktop tests, example checks/suites and exported-app assertions |
| Source-built engines | Source-engine lane: macOS ARM64 CI with Xcode and the Android SDK/NDK; local Mac for focused feedback | The stable and next-minor preview engines `patched` and `patched_beta`, with the patch/module fixture; the ruleset's tests tagged `source_engine` | Build and headless execution of the consumer's patched-engine apps; build-output tests of apps with source-built Android and iOS engines |
| Android packaging | The ruleset's tests in the Linux and macOS desktop sets, with SDK/NDK and Java 21; the Android lane on Linux CI for the consumer | Stable and preview prebuilt engines; ARM64 baseline; dedicated ARM64+x86_64 bundle case, each selected by its test's transition | APK/AAB build-output tests and platform library contracts in the ruleset; the consumer's Android smoke bundle and the Android API contract cases |
| Android release symbols | The desktop sets, with Android packaging | Optimized native compilation, debug information and stripping, selected by the test's transition | Match retained symbols/Build IDs/DWARF to delivered libraries |
| iOS packaging | macOS CI with Xcode, local Mac for focused feedback: the ruleset's tests in the macOS desktop set; the iOS lane for the consumer | Stable prebuilt x86_64 Simulator and prebuilt unsigned ARM64 device link in the ruleset; source-built ARM64 Simulator in the source-engine lane | Build-output tests of configured products; the consumer's iOS smoke app and the iOS API contract cases; a device link is not a provisioned device IPA |
| iOS release symbols | The macOS desktop set, with iOS packaging | Optimized build, stripping and dSYM, selected by the test's transition | Match executable/dSYM UUIDs and expected native libraries |
| Mobile operating-system behavior | Matching Android device/emulator or iOS device/simulator | One representative environment for the changed operating-system behavior | Focused runtime acceptance only if that behavior or explicit feature acceptance requires it |
| Signing/distribution | Appropriate identity, provisioning and environment | Configuration explicitly selected for the task | Only the signing/distribution operation in scope; never infer Store acceptance |

Each test runs in one lane. The ruleset's tests, its Android and iOS build-output tests
included, run in the desktop sets (the work `test:bazel` provisions the Android SDK); the
source-engine lane runs those tagged `source_engine`, which build an engine from source. The
ruleset's `.bazelrc` leaves them out of every build and test unless `--config=source-engine`
selects them, so the desktop sets do not analyze their source recipes; one named by its label
runs only with that config too. CI runs the lane only
in the [Source engine](#source-engine-workflow) workflow; locally, `aspect work source-engine`
runs `--config=source-engine-main`, which leaves out the tests also tagged
`source_engine_extended`.
The Android and iOS lanes run the scenarios' mobile smoke tests and the API
contract cases of their lane.

The matrix separates **host**, **operating system of the application**, **CPU/ABI**,
**engine origin and version**, **build mode/optimization/symbols**, **execution venue** and
**device class**.
They are not independent in every combination: Apple tooling requires macOS; an engine archive
supplies runtimes for specific platform slices; a device link does not require running that device. Add a combination
only when it covers a distinct supported failure mode or explicit acceptance requirement.
Do not multiply every test across all dimensions.

Linux ARM64 and macOS Intel acquisition support does not imply dedicated CI execution for
every editor platform. Windows hosts, Windows and Web applications and .NET/C# have no routine
verification commitment here. There is no default mobile GdUnit/device automation or
visual/manual desktop gameplay gate.

Engine compatibility uses the pinned stable release and pinned next-minor preview, not every
accepted patch/minor version. Engine acquisition/configuration changes require the relevant
archive, generator and build contracts; changing an extension API baseline requires its extension
compatibility checks. Package/symbol cases cover their specific contracts without replaying
all source suites in every release configuration.

## Lanes and execution

CI runs every lane on every run: pull requests, the merge queue and a manual dispatch.
Bazel's caches keep unchanged work cheap. The lanes' work lives in
[`tools/ci/work.py`](../../tools/ci/work.py): the repository's own, each add-on module's
lanes as its `addon.pkl` names them and the add-on generator's self-test in each add-on lane.
Each job of [CI](../../.github/workflows/ci.yml)'s lane matrix runs one lane on its host with
`aspect lane <lane>`, which leaves out add-on work whose `addon.pkl` excludes the host, and
`Finalize` fails when any job failed or was cancelled.
The matrix fails fast: the first job to fail cancels the others, so they free their runners
and `Finalize` fails at once, which in the merge queue removes the entry without waiting for
the slowest lane; the work they finished stays in Bazel's caches.

Locally, `aspect lane <lane>` runs a whole lane on this host, `aspect work <name>...` single
pieces, and `aspect work` lists them. Where a piece is one Bazel command, the documentation
shows that command instead. The pre-push hook runs the checks that need no lane machine, as
the [verification policy](verification.md#when-to-verify) describes.

A lane needs its prerequisites and must not silently succeed because it was invoked on an
unsuitable host; Android work provisions the pinned SDK first. Each example's suite, such
as `test:example:lichtpost`, uses `--build_tests_only` over its example subtree, so new test
targets are discovered automatically without building unrelated app targets. Bazel still
respects manual tags and platform compatibility.

Each application of `examples/` runs in the lanes its `app.pkl` names, as
[tools/apps/App.pkl](../../tools/apps/App.pkl) defines them.

Each add-on module runs the same generic work in the lanes its `addon.pkl` names. A lane
runs all of them with one Bazel command as the work `<lane>:addons`, and the work
`<lane>:addon:<module>` runs one module alone; [add-on guidance](../../addons/AGENTS.md#lanes)
has the commands. Their iOS work follows the Apple-lane policy below.

### Source engine workflow

The source-engine lane is the most expensive one and the least likely to change with a
commit, so CI has no job for it. The
[Source engine](../../.github/workflows/source-engine.yml) workflow runs the whole lane,
its contract cases and `source-engine:full`, on main on its schedule, and on manual dispatch for any
branch: a pull request that changes source-built engines dispatches it on its own branch
before it merges. Stale recipe pins need no dispatch to show: the quality lane's
`generated` work, which the pre-push hook runs too when a change can shape a pin, analyses each pinned engine's
toolchains, which fails on a pin whose inputs changed, such as rules_godot's graph capture.
`aspect work source-engine` runs
locally the cases users depend on most: the runtimes the official artifacts lack, built
from the release's sources for the iOS arm64 Simulator and for Android, and the
consumer's patched engine with its custom module, editor included; the tests tagged
`source_engine_extended`, the stable and beta patched engines and the suites of the
applications whose `app.pkl` names the lane join them in `source-engine:full`.

### Apple lanes

The lanes that need a macOS runner are the Apple lanes: the desktop tests on macOS, the apps
with source-built engines and the iOS apps. Their [CI](../../.github/workflows/ci.yml) jobs
run on the self-hosted runners labeled `macos-ci`: four runners in one macOS VM, which keep
their tools and Bazel caches on their own disk between jobs. The VM, its runners and its
BuildBuddy executor are set up in the private repository `autoload-dev/macos-ci`; a change
there takes effect through a new image and a replaced VM, done only while no job runs on
it. CI runs the Apple lanes like the other lanes, on pull requests and in the merge queue.
A pull request from a fork runs no Apple lane: the VM also holds caches and the BuildBuddy
executor's key, so a fork's code reaches it only in the merge queue. CI's `Finalize` is the
merge queue's required check: a pull request whose lanes fail there leaves the queue and
does not reach main. The ruleset of main, which requires the merge queue and that check, is
managed in the repository settings. Main receives the merge group's commit unchanged, so its
checks show on the commit and a push to main runs no CI. The merge queue also saves the
caches that later runs read, such as the Linux jobs' Bazel downloads: Blacksmith's branch
protection for the Actions cache and sticky disks is off, so every branch reads a merge
group's entries.

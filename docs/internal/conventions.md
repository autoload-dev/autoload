# Repository conventions

The conventions check (`bazel run //tools/conventions`) audits the Bazel packages, targets,
Godot projects, add-on modules, documentation and agent files of this repository. Each
convention rule has a stable ID, so diagnostics stay searchable when this page is
reorganized. This page owns each rule's ID, applicability, automated coverage and limits;
the [project layout guide](../../rules_godot/docs/public/project-layout.md) owns what the
layout and naming conventions mean. External repositories and source files are separate
identities, not authored target declarations.

| ID | Rule | Policy | Automated coverage | Enforcement |
|---|---|---|---|---|
| [RG001](#rg001) | Package segments use lower snake case | Required | All inventoried owned BUILD paths, relative to the nearest module | Error |
| [RG002](#rg002) | Authored names use lower snake case; owned helpers use dotted roles | Required | Bazel-evaluated owned expansions and explicit roots; computed roots require review | Error; incomplete required ownership fails |
| [RG003](#rg003) | Target declarations pass `name` explicitly | Required | BUILD calls associated with at least one evaluated rule | Error |
| [RG004](#rg004) | Public documentation does not reference test fixtures | Required | Concrete paths into the regression module in public guides and READMEs | Error |
| [RG006](#rg006) | Documented commands name existing targets | Required | Labels of `bazel build`, `run` and `test` commands in documentation | Error |
| [RG007](#rg007) | Godot test operations and their helpers are test-only | Required | Effective flags on recognized Godot test macro expansions | Error; missing evidence is reported as not checked |
| [RG008](#rg008) | Application content lives under `main/` | Required | Production-eligible resource inputs physically owned by a project of a consumer | Error; unresolved membership is reported as not checked |
| [RG009](#rg009) | Projects lie at the fixed places of their consumers | Required | Projects and authored Godot configurations of every consumer | Error |
| [RG012](#rg012) | Production targets are independent of test scopes | Required | Direct authored workspace inputs of every production-eligible declaration outside a test scope, resolved by Bazel | Error; missing role flags are reported as not checked |
| [RG013](#rg013) | Public documentation does not link to internal documentation | Required | Local Markdown and HTML link destinations in public guides and READMEs | Error |
| [RG014](#rg014) | Engine modules, patches and source build files live under `engine/` | Required | Files of every Godot project root of a consumer module, owned by their nearest `project.godot` | Error |
| [RG015](#rg015) | Add-on modules share one layout | Required | Every module `addons/<module>/` of this repository, and every `backends/` directory | Error |
| [RG016](#rg016) | Local links resolve | Required | Local Markdown and HTML link destinations and their fragments in documentation, READMEs, `AGENTS.md` and `SKILL.md` files | Error |
| [RG017](#rg017) | Agent instructions live in `AGENTS.md` | Required | Every `CLAUDE.md` in the working tree | Error |
| [RG018](#rg018) | Skills live in `.agents/skills` and are linked for Claude Code | Required | Every skill in `.agents/skills/` and every entry of `.claude/skills/` | Error |
| [RG019](#rg019) | A package's Godot project is named like its directory | Required | `godot_project` calls of every package that holds a `project.godot` | Error |
| [RG020](#rg020) | Released modules have a registry test module in `bcr/` | Required | The ruleset and every add-on module, their presubmits and `.bazelignore` | Error |
| [RG021](#rg021) | Add-on modules run no Godot | Required | Godot configurations and Godot project and test calls of every add-on module | Error |
| [RG023](#rg023) | Release archives leave out tests, and nothing else needs them | Required | `.gitattributes` and the Starlark files of every released module | Error |

RG005 is retired: Bazel's load and target visibility enforce the boundary it checked (see the
[boundary rules](verification-architecture.md#boundary-rules)). RG010 and RG011, which
required add-ons to keep a demo and a test project inside their own directory and their
implementation independent of that demo, are retired with that layout: add-ons live in
add-on modules, which hold no project ([RG021](#rg021)), and their demos and end-to-end tests
are projects of the root module ([RG009](#rg009)). Choosing the main entry point
and useful package boundaries still requires judgment; the checks do not elect a primary target.

## RG001

**Package segments use lower snake case.** Each segment of an owned Bazel package path
must match `[a-z][a-z0-9]*(?:_[a-z0-9]+)*`: an ASCII lowercase letter first, then lowercase
letters/digits, separated by single underscores. Leading, trailing and repeated underscores
are excluded. This makes package labels predictable and consistent across operating systems.

`addons/platform_paths` and `tools/conventions` conform; `addons/platform-paths`,
`tools/_checks`, `tools/checks_` and `tools/my__checks` do not. Check every ancestor segment,
even when only the leaf directory contains a BUILD file. A module root has no package
segment. Names of directories containing only assets are outside this rule unless they
form part of a package path.

The checker inventories Git-tracked and untracked, non-ignored `BUILD`/`BUILD.bazel` files
and resolves each against its nearest `MODULE.bazel`. It does not scan fetched repositories,
Bazel output trees or generated BUILD templates as if they were maintained packages.

## RG002

**Ordinary target names use lower snake case.** Authored logical target names follow the
same spelling as RG001. Consistent names make labels easy to type and distinguish logical
targets from output filenames and generated artifacts.

```starlark
# Conforming declarations; helper names describe separate responsibilities.
godot_resources(name = "main", srcs = ["game.gd"])
filegroup(name = "linux_package", srcs = [":bundle"])
```

Names such as `LinuxPackage`, `linux-package`, `linux/package` and `linux__package` do not
conform as ordinary authored names. A slash in a target name is not a package boundary.
Preserve meaningful secondary names; do not create aliases or aggregates just for naming.

Additional targets generated by a rules_godot-owned macro are named `<name>.<role>`, as the
[layout guide](../../rules_godot/docs/public/project-layout.md#package-and-target-names)
describes. Bazel's
[symbolic macro schema](https://github.com/bazelbuild/bazel/blob/9.3.0/site/en/extending/macros.md#naming)
allows this separator. The checker examines the Bazel-evaluated expansions of owned macros,
including nested helpers; a compliant main name alone does not establish compliance for its
helpers.

The convention covers every rules_godot-owned public macro and its nested private macros,
including project, test, extension, export-platform and packaging helpers. A generated
repository's independent entrypoints do not acquire a fictitious common main target; apply
the separator where a main target actually has companion targets. Repository names and
output-group keys are separate interfaces.

Upstream-generated identities retain upstream spelling. rules_android and rules_apple derive
delivered basenames from a slash suffix, so a role may continue after a slash with the main
name again, as in `app.android_apk/app.native_apk`; the owning definition explains why.

Source-file labels and external identities retain their required spelling.
An explicit output filename is also distinct: for example,
`cc_binary(name = "libnative.so", linkshared = True)` names a shared library artifact.
The checker recognizes that qualification only for a `cc_binary` with effective
`linkshared = True`, a filename without `/`, and a `.so`, `.dylib` or `.dll` suffix.
A `filegroup` named `libnative.so` has no such output contract and is a violation.

For literal names, the authored declaration establishes the complete main name. Bazel
supplies the emitted labels and the instantiation frames of each evaluated rule; generated
names are checked against that main name, including its existing underscores.

**Computed macro roots remain a review obligation**: `generator_name` may identify an internal
helper instead of the authored invocation. Review the expression and its inputs while
preserving output filenames, registration symbols and resource paths. Record
the roots in `REVIEWED` in [the RG002 module](../../tools/conventions/rules/rg002.py), by BUILD
path. The roots are the call's emitted names without a role; every other emitted owned label is
checked against exactly one of them. A changed root set requires renewed review; stale
reviews fail. Missing required ownership or review evidence fails the check.
Incomplete review evidence is reported as `RG002 not checked`. This strictness does not
change other conventions' coverage policy.

## RG003

**Target declarations pass `name` explicitly.** Show the target's identity at its declaration
so readers can locate it without following an inferred default or a dictionary expansion.
A computed expression still counts as explicit:

```starlark
godot_resources(name = "main", srcs = ["game.gd"])
godot_resources(name = variant + "_resources", srcs = sources)
```

A target-producing call such as `target_macro(**options)` does not express `name` explicitly.
Use `target_macro(name = target_name, **other_options)` instead. Calls such as `load`,
`package`, `exports_files`, `glob` and arbitrary helpers are not target declarations merely
because they appear in a BUILD file.

The checker joins parsed BUILD calls with evaluated rules by their source location. This
classifies actual target-producing calls without a guessed list of function names and
handles macros, aliases and comprehensions. Macro implementation calls inside `.bzl` files
and generated targets are outside this authored-BUILD check. Calls producing no evaluated
rules are outside its coverage. Ambiguous or missing source evidence and failed parsing or
loading stop the audit with an error rather than silently passing.

## RG004

**Public documentation does not reference test fixtures.** Public guides and READMEs show
runnable examples, which users can copy, instead of named consumer scenarios.
The check reports each line with a concrete path such as `e2e/rules_godot/smoke/linux` in Markdown under
`docs/` and in every README, except internal documentation (the `docs/internal/` directories
of the repository and the ruleset) and `AGENTS.md` files. Layout placeholders such as
`tests/smoke/<operating_system>/` are not fixture references. Maintainer fixture commands
belong in internal documentation.

## RG006

**Documented commands name existing targets.** Copying a command from the documentation
works only if its labels exist.
The check reads the labels of `bazel build`, `bazel run` and `bazel test` commands in
Markdown under `docs/` and in every README, except `AGENTS.md` files. Arguments after `--`,
`...` patterns and `//path/to` placeholders are skipped.

Each label resolves in exactly one module that contains its package:

- `@autoload_rules_godot//` labels resolve in the ruleset module, `rules_godot/`.
- A document inside a module resolves labels in its own module first; a document in the
  root module's consumers, such as one in `examples/`, resolves them in the root module.
- `//:target` labels in documents of the root module and the ruleset module are consumer
  templates and are not checked.

The named rule must exist in that package; `:all`, `:*` and `:all-targets` only require the
package. A label is reported at its command's line when no module or several modules
contain the package, or when the package has no such rule. A resolved label does not prove
that the documented workflow succeeds.

## RG007

**Godot test operations and their helpers are test-only.** The targets created by
`godot_test` and the test operations an add-on module declares in its `addon.pkl`
(`testOperations`), such as autoload_gdunit's `gdunit_test`, must have effective
`testonly = True`. This includes their generated case lists, resources and views of
the project. They belong exclusively to the test operation and must not become production
dependencies, following
[test ownership](../../rules_godot/docs/public/project-layout.md#test-ownership).

The operations set `testonly = True` on themselves and their helpers unless the caller
passes `testonly = False`, so a test can sit in a mixed production/test package without
further flags. The rule reports such opt-outs. The checker asks Bazel for
[attribute defaults](https://bazel.build/query/language#xml), so it judges the effective
value, including package defaults, without requiring a literal attribute.
[Bazel's test-only dependency check](https://bazel.build/reference/be/common-definitions#common.testonly)
then protects the marked targets from production consumers.

Applicability comes from the evaluated `generator_function` metadata of these
operations, including source aliases and comprehensions. Each attributed rule target is
checked. Each false flag is reported at the call with the affected target label. Missing
scalar flags or missing generator evidence for a directly named operation are reported as
not checked. Other targets at the same authored call with an unknown or different generator
are also reported as not checked; their ownership must not be inferred from a neighboring
test target. Arbitrary wrappers which hide the operation's
identity are outside automated coverage; a `_test` suffix alone does not establish ownership.

Shared runtime resources, code under test and existing projects supplied as inputs retain
their production eligibility. This rule does not traverse a test's dependency closure or
classify separately declared suites and test data; those still follow the broader ownership
policy. Loading-time flags do not establish configured resource membership or runtime behavior.

## RG008

**Application content lives under `main/` of its physical project.** The place of a project
establishes ownership in every consumer, following [RG009](#rg009). Application cases own
their scenes, scripts and exclusively used assets below `main/`; an add-on a project keeps
for itself lives there too, such as `main/addons/<name>/`. Keep authored UID/import sidecars
beside sources.

For example:

```starlark
godot_resources(
    name = "main",
    srcs = ["main/game.gd", "main/game.tscn"],
)
```

These sources use `res://main/game.gd` and `res://main/game.tscn`. When moving application
files, update configuration, scene/script references, authored import sidecars and
assertions. Do not preserve an old application path through an unnecessary `resource_paths`
entry. Godot plugin namespaces and deliberate resource path regressions can retain explicit
entries; a mounted `addons/` path never changes the project or add-on that physically owns a
source.

The check inspects loaded `godot_resources` inputs declared through `srcs` and
`resource_paths`, including sources supplied across modules. Ownership comes from the
physical source path, not the project consuming it. In an application case, the nearest
authored configuration owns its application inputs; shared inputs without their own
configuration use the case root's `main/`. Contexts for one operating system may each own
their configuration and `main/`. Several resource paths of one physical source produce one
finding.

There is no blanket exemption for regression projects, test-only project compositions or
macro-generated projects. Test-only suites and helpers belong in a project's `tests/` scope;
an add-on module's end-to-end test project in `e2e/addons/<module>/` is test-only as a whole,
so its test-only inputs may lie anywhere in it, in packages named after their topic. Both the
physical test scope and the `godot_resources` target's effective test-only flag establish
that ownership; the flag alone does not waive application layout. Generated outputs and the
build and delivery inputs of extension and platform libraries are outside this declared
Godot-resource subset. Missing role/membership facts and unresolved aggregate inputs are
reported as not checked. The check does not classify undeclared files or require an empty
`main/` where no application-owned resources exist. No manually listed application roots or
reusable-resource exemptions select applicability.

## RG009

**Projects lie at the fixed places of their consumers.** Every consumer places its projects
by path, without typed roots:

| Consumer | Projects |
|---|---|
| Applications, `examples/` | `examples/<name>/` |
| Add-on examples, `examples/addons/<module>/` for each module `addons/<module>/` | the directory itself, or one directory of it per scenario |
| Consumer scenarios, `e2e/rules_godot/` | `e2e/rules_godot/smoke/<operating_system>/`, and `e2e/rules_godot/<scenario>/` for every other scenario |
| Add-on end-to-end tests, `e2e/addons/<module>/` | the directory itself, or one directory of it per add-on, scenario or configuration variant |
| Registry test modules, `<module>/bcr/<name>/` ([RG020](#rg020)) | the module itself, or one directory of it per project |

A project owns a BUILD file and at least one authored Godot configuration; related
operating-system contexts can share one project. No other module holds projects: an add-on
module holds none ([RG021](#rg021)), and the white-box fixture projects of the ruleset module
are outside this check. There is no per-directory admission list.

The check inventories the projects and the authored `project.godot` files of every consumer.
Configurations must belong to a project at a fixed place. Temporary projects constructed
inside source strings and generated configuration templates are outside the inventory. The
check does not require a project or BUILD package for each assertion.

## RG012

**Production targets are independent of test scopes.** A target that is not test-only must
not consume targets or source files owned by a test scope. Mark the consumer `testonly` when
it exists only for tests, or move the input out of `tests/` when production code really
shares it. This applies to applications, add-ons, their demos and the ruleset itself,
following
[test ownership](../../rules_godot/docs/public/project-layout.md#test-ownership).

A test scope is a `tests/` directory below the root of a project or add-on, such as
`<project>/tests/`, `<addon>/tests/`, a demo's `examples/addons/<name>/tests/` or a backend's
`<addon>/native/backends/linux/tests/`. Outside projects and add-ons it is a `tests/`
directory below the module root, such as the ruleset's white-box packages
`godot/private/tests/`, or an add-on module's module-wide unit tests in its `tests/`. Paths
are measured from the owning module. A generator's template of a `tests/` package, a `.tmpl`
file, is no member of a test scope.

```starlark
# game/main/BUILD.bazel
godot_resources(
    name = "main",
    srcs = ["game.gd"],
    deps = ["//game/tests:suites"],  # Reported: suites are test-owned.
)
```

The check resolves inputs from authored label, label-list and
label-keyed-string attributes, resolved by Bazel to their defining target or source file
across the workspace's modules. Declarations inside a test scope and test-only targets are
consumers, not subjects. Missing effective role flags are reported as not checked. Bazel's
own test-only dependency check covers edges to marked targets; this rule also covers
unmarked targets and source files by their location. Indirect paths and configured closures
remain outside this automated subset.

## RG013

**Public documentation does not link to internal documentation.** Consumer guides and
READMEs must stand on their own. Link to public setup and usage guides instead of requiring
readers to follow contributor implementation or verification instructions.

The check resolves static local destinations in Markdown links, images, reference definitions
and quoted or unquoted HTML `href`/`src` attributes against the document's directory.
Root-relative paths, fragments, query strings, percent encoding, Markdown punctuation escapes
and HTML character references are handled too. Inline code, top-level fenced or indented code
blocks and HTML comments are ignored. Merely naming an internal directory or showing a link
inside such a code example does not create a link.

Internal reference pages and agent instructions are outside this public-documentation check.
External URLs and dynamically generated links are outside automated coverage and need
review; the checker does not fetch remote documents.
This source check does not implement a full Markdown renderer: nested list/blockquote blocks
and destinations containing whitespace or nested parentheses need review.

## RG014

**Engine modules, patches and source build files live under `engine/`.** A Godot project
that builds its engine from sources keeps each custom engine module in
`engine/modules/<name>/`, each engine patch as a `.patch` or `.diff` file directly in
`engine/patches/`, and its source build's lock file, `<hub>.lock.json`, with the `.bzl`
files of its engine, such as a gate that keeps its targets out of builds with another
engine, directly in `engine/`. Readers and source recipes then find a project's engine
inputs in one place, separate from its application content under `main/`.

```text
<project>/
  project.godot
  main/
  engine/
    BUILD.bazel
    <hub>.lock.json           # the source build's lock file
    modules/
      <module>/               # config.py, SCsub, register_types.cpp, sources, BUILD.bazel
    patches/
      BUILD.bazel             # exports the patches to the module's recipes
      <change>.patch
```

The check inventories the files of every project root of a consumer module; a
`project.godot` marks a root, and a nested project owns its own files. In each project it
reports:

- any entry of `engine/` other than `modules/`, `patches/`, a BUILD file, lock files and
  `.bzl` files;
- any file directly in `engine/modules/`, and any directory there without both `config.py`
  and `SCsub`;
- any entry of `engine/patches/` other than `.patch`/`.diff` files and a BUILD file,
  including subdirectories;
- any engine module directory outside `engine/` (a directory owning `config.py` together
  with `SCsub` or `register_types.*`), any `.patch`/`.diff` file outside
  `engine/patches/` and any `.lock.json` file outside `engine/`.

A stray directory is reported once, at its first file. An add-on's own `register_types.*`
without `config.py` is an extension, not an engine module. Files outside every project
root, such as dependency patches in `third_party/`, are outside this rule.
The check does not read module or patch contents and does not prove that a recipe consumes
them.

## RG015

**Add-on modules share one layout, and backends live in `native/backends/`.** This
repository's add-on modules in `addons/<module>/` follow the layout of the add-on generator's
template, so that the same tasks build, test and release every module and nothing but the
root module's declaration lists it. Each module:

- is named `autoload_<module>` and owns the files of the generator's module template, such
  as `MODULE.bazel`, `README.md`, `REPO.bazel`, `BUILD.bazel`, `.bazelrc`, `.bazelignore`,
  `addon.pkl` and its registry test module `bcr/smoke`;
- holds in its root only those files and its lock file, its add-ons, `third_party/` with
  what makes its dependencies usable, `tests/` for module-wide unit tests, `bcr/`, and the
  packages its `addon.pkl` declares in `sharedPackages`, such as Firebase's `config`. An
  add-on is a directory whose BUILD file declares a target named like it, as the generator
  writes it;
- owns registry templates in `.bcr/addons/<module>/`: `metadata.template.json`,
  `presubmit.yml` and a `source.template.json` that releases the archive
  `autoload_<module>-{VERSION}`. Templates in `.bcr/addons/` without their module are
  removed with it;
- imports the shared settings: `.bazelrc` imports `addons/module.bazelrc`;
- has an `addon.pkl` that amends the schema `tools/addons/Addon.pkl` and sets only its
  properties: `lanes` (some of `desktop`, `android`, `ios`), and optionally `desktops` (some
  of `linux`, `macos`), `testOperations` and `sharedPackages`. The repository does not evaluate the schema's
  types, so this rule checks the values. A module builds applications when its lanes include
  `android` or `ios`;
- has at least one example project in the root module's
  `examples/addons/<module>/`, the directory itself or one subdirectory per scenario, each
  defining the targets `edit` and `pack`, and `app` when the module builds applications,
  and keeping its tests, such as the exported demo's, in its `tests/` package;
- gives each `godot_cc_extension` a name no other add-on module uses: on iOS it names the
  extension's framework, and an application's frameworks share one directory.

In every add-on, including those of `examples/`, a `backends/` directory sits in `native/`:
the backends implement the platform-independent API beside them. The check reads the files
and their text without loading Bazel; it reports a stray `backends/` directory once.

## RG016

**Local links resolve.** A link in documentation, a README, an `AGENTS.md` or a skill's
`SKILL.md` names a file or directory of the repository, in its exact case, and a fragment
names a heading or an HTML `id` or `name` of the Markdown page it points to. Headings become
fragments as on GitHub: the rendered text in lower case, without punctuation, spaces as
hyphens and a number appended to repeats. Ignored local files, such as `user.bazelrc`, are
no link targets.

The check reads link destinations as [RG013](#rg013) does, and ignores links in code and
comments the same way. External URLs, fragments into files other than Markdown and fragments
after a query, such as `?plain=1#L5`, are outside automated coverage.

## RG017

**Agent instructions live in `AGENTS.md`.** Claude Code and Codex both read `AGENTS.md`, but
Claude Code ignores it while a `CLAUDE.md` exists in its working directory or above it. The
check reports every `CLAUDE.md`; rules for one agent alone go into `AGENTS.md`, marked as such.

## RG018

**Skills live in `.agents/skills` and are linked for Claude Code.** A skill is written once,
as a directory `.agents/skills/<name>/` with a `SKILL.md`, where Codex finds it. Claude Code
finds project skills only in `.claude/skills/`, so `.claude/skills/<name>` is a symbolic link
to `../../.agents/skills/<name>`. `.claude/skills/` holds nothing else: no copies and no
skills without a counterpart.

## RG019

**A package's Godot project is named like its directory.** A package that holds a
`project.godot` and declares projects names one of them like its directory, so the package's
own label names its project: `//examples/addons/sqlite` and `//e2e/addons/sqlite`, not
`//examples/addons/sqlite:demo`. Write that short form in labels and commands. Further
projects of the package, such as a test project beside an application's, take names of their
own. This applies everywhere, the ruleset's fixtures included.

The check reads the `godot_project` calls of every module and reports each package with a
`project.godot` whose projects include none named like its directory. A package without a
`project.godot`, whose project reads its configuration from elsewhere, is outside the check.

## RG020

**Released modules have a registry test module in `bcr/`.** The Bazel Central Registry
tests a release by building a test module from the release archive. Each released module,
the ruleset and every add-on module, has that module in `bcr/<name>/`, so that it is
recognizable by its place:

- the module's registry templates, `.bcr/<module>/presubmit.yml`, run it as their
  `bcr_test_module` with `module_path: "bcr/<name>"`;
- the module's `.bazelignore` lists `bcr`, since each test module is a Bazel module of its
  own;
- the test module is a consumer with a flat project: the test module itself is the project,
  or each project lies directly in one of its directories, without typed roots, which
  [RG009](#rg009) checks.

A test module registers the prebuilt engine itself, as an application does; the add-on
modules register none for consumers. The add-on generator writes `bcr/smoke` with every new
module. `python3 -m tools.ci.release_archive` runs each test module from its module's release
archive, as the release workflow and the registry do.

## RG021

**Add-on modules run no Godot; their end-to-end tests live in the root module.** An add-on
module holds its add-ons and the unit tests of their code. A test that uses an add-on as an
application does, by running Godot or building a project, is an end-to-end test and lives in
`e2e/addons/<module>/`. There the root module declares what the test uses as development
dependencies, which an add-on module could only declare as regular dependencies that every
consumer inherits: the lanes build add-on modules from the root module, where their own
development dependencies are not active.

The check reports, in each add-on module but its registry test modules, every
`project.godot` and every call of `godot_project`, `godot_test`, `godot_metadata_sync` or a
test operation its `addon.pkl` declares in `testOperations`.

## RG023

**Release archives leave out tests, and nothing else needs them.** The ruleset and every
add-on module are released as a `git archive` of their directory
(`.github/workflows/release_prep.sh`). Consumers cannot run a module's tests, whose
development dependencies are not theirs, so each released module's `.gitattributes` leaves
every `tests/` directory, at any depth, out of the archive: `tests export-ignore`. The
registry test modules in `bcr/` keep theirs, since the registry runs them from the archive
([RG020](#rg020)): `bcr/**/tests -export-ignore`. A package
that would then name a missing file or package fails to load for every consumer, so no
Starlark file outside a `tests/` directory may use a path or label inside one. Test code and
fixtures that a package outside `tests/` needs belong to a `tests/` package of their own.

The check parses each released module's BUILD files, `MODULE.bazel` and `.bzl` files. Names
that are never loaded are allowed: target visibility, `package_group` packages and load
visibility, and the arguments of dev dependencies in `MODULE.bazel`, which only the module's
own builds evaluate. Modules that are never released, such as the root module, are outside
it.

## Run and maintain the checks

From the repository root:

```sh
bazel run //tools/conventions
```

The command runs every registered convention rule across all owned modules. Violations
include the stable rule ID, file, line and a link to this catalogue. The checker reports
unreviewed computed macro names separately. Exit status `1` indicates convention findings;
`2` indicates an incomplete audit. The work `conventions` of the `quality` lane runs this
command, and the pre-push hook runs that work.

Run one rule independently or list the registered rules:

```sh
bazel run //tools/conventions -- --rule RG001
bazel run //tools/conventions -- --list-rules
```

Each rule lives in its own module under [`tools/conventions/rules`](../../tools/conventions/rules)
with its regression tests beside it. The convention checks do not prove configured
dependencies or runtime behavior.

Fix findings in their sources. A target rename can change outputs, so update references and
artifact assertions deliberately; there is no automatic rename fixer. Temporary exceptions
belong beside their owning rule, with a reason and removal condition. For automated rules,
keep qualifications and reviewed coverage limits in the owning rule module. There is no
blanket exemption for fixtures or the test tree.

## Rule framework

Each registered rule is an independent object with `info: RuleInfo` and
`evaluate(context) -> Iterable[Finding]`. Its own module owns its ID, title, applicability,
predicates, artifact qualifications, incomplete-coverage findings and records of reviewed
sites. Tests live beside the rule. No rule's implementation is placed in the CLI or tool
adapters.

The [framework](../../tools/conventions/framework.py) validates unique IDs, invokes rules
against one context and attaches their metadata to findings. It sorts diagnostics for
stable output. A rule reports each finding once; a repeated finding is a rule defect and
aborts the run rather than being merged. `Finding.status` distinguishes `violation` from
`not_checked` for every rule. The [registry](../../tools/conventions/registry.py) lists
the rules explicitly and selects them by ID, and the [CLI](../../tools/conventions/check.py)
formats results and chooses the exit status.

The [context](../../tools/conventions/context.py) exposes read-only evidence tools: the
workspace files, documents, modules and typed directories, Starlark calls, Bazel rules and
inspection, and the joins of them (`context.declarations`, `context.sources`). The public
members of `context.py` carry their documentation. The documentation rules share
[documents](../../tools/conventions/documents.py): which pages are internal, which files
are agent instructions (every `AGENTS.md` and `SKILL.md`), and the local links and anchors
of a Markdown source.

Tools load evidence lazily, cache it per tool/context instance and return immutable records
and read-only attribute maps. The first `context.declarations` call loads the calls and
rules of every module concurrently, since each module is a separate Bazel workspace. The
target-name and explicit-name rules share their declaration data, and the documentation-label
rule resolves labels against the same per-module query, so no query runs twice. Missing or
ambiguous source evidence and failed tools raise `EvidenceError` and abort the audit; they
are not converted into an empty successful result.

To add a rule, create its module and adjacent regression tests, register its object, and
declare those sources in the existing Bazel package. A rule consumes available tools and
returns findings; it does not require a branch in the checker or a new report field. Add a
tool capability only when a rule needs a new kind of evidence, keeping retrieval independent
of the policy which consumes it. Tool protocols allow rule tests to use deterministic facts
without launching subprocesses; context tests exercise real parsing and evidence joins.

### Design

- Buildozer's JSON interface exposes the parsed calls of a BUILD file without a Go
  toolchain or buildtools fork of our own.
- Bazel loading identifies which calls produce targets and evaluates the names of Bazel's
  built-in rules, so no list of function names guesses which helpers are target
  declarations.
- The checker uses only Python's standard library and a token scan of the parser's
  formatted call to recognize literal `name` arguments. It never evaluates Starlark with
  Python.
- Semgrep patterns and `rules_lint` alone supply neither the Starlark nor the ownership
  semantics the rules need.
- [Pluggy](https://pluggy.readthedocs.io/en/stable/) would provide hook registration and
  result collection, but the domain context and evidence adapters would still be ours, so
  rules are registered explicitly and not discovered.

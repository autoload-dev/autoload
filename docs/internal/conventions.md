# Repository conventions

The conventions check (`bazel run //tools/conventions`) audits the Bazel packages, targets,
Godot projects, add-on modules, documentation and agent files of this repository. Each
convention rule has a stable name, which says what it requires in the [glossary's](glossary.md)
terms and keeps diagnostics searchable when this page is reorganized. This page owns each
rule's name, applicability, automated coverage and limits; the
[project layout guide](../../rules_godot/docs/public/project-layout.md) owns what the layout
and naming conventions mean. External repositories and source files are separate identities,
not authored target declarations. Coverage that rests on Bazel's evaluation, such as that of
[snake-case-target-names](#snake-case-target-names),
[documented-targets-exist](#documented-targets-exist),
[application-content-under-main](#application-content-under-main),
[production-independent-of-tests](#production-independent-of-tests) and
[godot-process-tests-tagged](#godot-process-tests-tagged), leaves out
the registry test modules ([registry-test-module-in-bcr](#registry-test-module-in-bcr)), which
the check does not load (see the [rule framework](#rule-framework)).

| Name | Rule | Policy | Automated coverage | Enforcement |
|---|---|---|---|---|
| [snake-case-package-paths](#snake-case-package-paths) | Package segments use lower snake case | Required | Every BUILD file, relative to the nearest module | Error |
| [snake-case-target-names](#snake-case-target-names) | Authored names use lower snake case; owned helpers use dotted roles | Required | Bazel-evaluated owned expansions and explicit roots; computed roots require review | Error; incomplete required ownership fails |
| [no-end-to-end-tests-in-public-documentation](#no-end-to-end-tests-in-public-documentation) | Public documentation does not reference end-to-end tests | Required | Concrete paths into `e2e/` in public guides and READMEs | Error |
| [documented-targets-exist](#documented-targets-exist) | Documented commands name existing targets | Required | Labels of `bazel build`, `run` and `test` commands in documentation | Error |
| [application-content-under-main](#application-content-under-main) | Application content lives under its project's `main/` | Required | Production-eligible resource inputs physically owned by a project of a consumer | Error; unresolved membership is reported as not checked |
| [application-tests-under-tests](#application-tests-under-tests) | An application's tests live in its `tests/` package | Required | The test calls of every application project's root package | Error |
| [projects-at-fixed-places](#projects-at-fixed-places) | Projects lie at the fixed places of their consumers | Required | Projects and authored Godot configurations of every consumer | Error |
| [production-independent-of-tests](#production-independent-of-tests) | Production targets are independent of test scopes | Required | Direct authored workspace inputs of every production-eligible declaration outside a test scope, resolved by Bazel, but test-only targets, which Bazel's test-only check guards | Error; missing role flags are reported as not checked |
| [no-internal-links-in-public-documentation](#no-internal-links-in-public-documentation) | Public documentation does not link to internal documentation | Required | Local Markdown and HTML link destinations in public guides and READMEs | Error |
| [engine-files-under-engines](#engine-files-under-engines) | Engine modules, patches and lock files live under `engines/<name>/` | Required | Files of every consumer module, and the Godot project roots among them | Error |
| [addon-module-named-after-directory](#addon-module-named-after-directory) | The module `addons/<module>/` is named `autoload_<module>` | Required | The `module()` of every add-on module | Error |
| [addon-modules-own-template-files](#addon-modules-own-template-files) | Add-on modules own the files of the generator's template | Required | Every add-on module and its registry templates | Error |
| [registry-templates-have-their-module](#registry-templates-have-their-module) | Registry templates belong to an existing add-on module | Required | Every directory of `.bcr/addons/` | Error |
| [no-stray-entries-in-addon-module-roots](#no-stray-entries-in-addon-module-roots) | An add-on module's root holds only its files, add-ons and the packages others load | Required | The root entries of every add-on module | Error |
| [no-test-only-dependencies-in-addon-modules](#no-test-only-dependencies-in-addon-modules) | Add-on modules have no regular dependency that only their tests load | Required | The regular `bazel_dep`s of every add-on module | Error |
| [addon-module-examples-define-edit-and-pack](#addon-module-examples-define-edit-and-pack) | Every add-on module has example projects, each defining `edit` and `pack` | Required | The example projects of every add-on module | Error; computed names are reported as not checked |
| [unique-extension-names](#unique-extension-names) | No two add-on modules' extensions share a name | Required | Every `godot_cc_extension` call of the add-on modules | Error; computed names are reported as not checked |
| [backends-under-native](#backends-under-native) | An add-on's backends live in its `native/backends/` | Required | Every `backends/` directory | Error |
| [no-claude-md](#no-claude-md) | Agent instructions live in `AGENTS.md` | Required | Every `CLAUDE.md` in the working tree | Error |
| [linked-skills](#linked-skills) | Skills live in `.agents/skills` and are linked for Claude Code | Required | Every skill in `.agents/skills/` and every entry of `.claude/skills/` | Error |
| [project-named-after-directory](#project-named-after-directory) | A package's Godot project is named like its directory | Required | `godot_project` calls of every package that holds a `project.godot` | Error |
| [registry-test-module-in-bcr](#registry-test-module-in-bcr) | Released modules have a registry test module in `bcr/` | Required | The ruleset and every add-on module, their presubmits and `.bazelignore` | Error |
| [no-godot-in-addon-modules](#no-godot-in-addon-modules) | Add-on modules run no Godot | Required | Godot configurations and Godot project and test calls of every add-on module | Error |
| [no-component-names-in-tooling](#no-component-names-in-tooling) | The Python tooling names no add-on module or application | Required | String literals of every Python file in `tools/` but tests and test support | Error |
| [release-archives-without-tests](#release-archives-without-tests) | Release archives leave out tests, and nothing else needs them | Required | `.gitattributes` and the Starlark files of every released module | Error |
| [shared-module-files-as-generated](#shared-module-files-as-generated) | Add-on modules keep the shared files as the add-on generator writes them | Required | The shared files of every add-on module and its registry templates | Error |
| [region-headers-named-in-head](#region-headers-named-in-head) | Regions start with a region header the file's head names | Required | Every Python, Starlark, GDScript and C++ file | Error |
| [definitions-before-callers](#definitions-before-callers) | Python definitions stand before their first caller | Required | Every top-level function and class of every Python module | Error |
| [godot-process-tests-tagged](#godot-process-tests-tagged) | Tests that start a Godot process carry the `godot_process` tag | Required | Every test of every module but the registry test modules and the tests `godot_test` declares, which tag themselves, by its loading graph | Error |

The rule of the public API's boundary is retired: Bazel's load and target visibility enforce it
(see the [boundary rules](verification-architecture.md#boundary-rules)). The rules that
required add-ons to keep a demo and a test project inside their own directory and their
implementation independent of that demo are retired with that layout: add-ons live in add-on
modules, which hold no project ([no-godot-in-addon-modules](#no-godot-in-addon-modules)), and
their demos and end-to-end tests are projects of the root module
([projects-at-fixed-places](#projects-at-fixed-places)). Choosing the main entry point and
useful package boundaries still requires judgment; the checks do not elect a primary target.

The rule that required the targets of Godot test operations to be test-only is retired:
`godot_test`, and the test operations built on it, reject `testonly = False`, and Bazel's
test-only check protects their targets. A macro that wraps a test operation and declares
helpers of its own marks them test-only itself; no check covers that.

Other tools enforce what three retired rules checked: explicit target names, resolving local
links and the add-on modules' Python lint. Buildifier's default warnings
`build-args-kwargs`, `positional-args` and `unnamed-macro`, which `.buildifier.json` keeps,
require target declarations to pass `name` as a keyword. Outside them are a legacy macro
whose `name` has a default and positional arguments to a legacy macro of another repository,
which buildifier cannot read; the repository has neither, and rules and symbolic macros take
no positional arguments and require `name`. rumdl's MD057 and MD051 resolve
Markdown links and their fragments, in exact case, over every Markdown file in the
[file lint](verification-recipes.md#the-file-lint); destinations of HTML `href` and
`src` attributes are outside them, so link with Markdown. The lint check fails on an add-on
module's Python target without the tag `lint-genfiles`, which the root module's lint would
skip ([tools/lint/check.bzl](../../tools/lint/check.bzl)).

## snake-case-package-paths

**Package segments use lower snake case.** Each segment of an owned Bazel package path
must match `[a-z][a-z0-9]*(?:_[a-z0-9]+)*`: an ASCII lowercase letter first, then lowercase
letters/digits, separated by single underscores. Leading, trailing and repeated underscores
are excluded. This makes package labels predictable and consistent across operating systems.

`addons/platform_paths` and `tools/conventions` conform; `addons/platform-paths`,
`tools/_checks`, `tools/checks_` and `tools/my__checks` do not. Check every ancestor segment,
even when only the leaf directory contains a BUILD file. A module root has no package
segment. Names of directories containing only assets are outside this rule unless they
form part of a package path.

The check reads each `BUILD`/`BUILD.bazel` file Git lists, tracked or untracked and not
ignored, and resolves it against the nearest `MODULE.bazel` on disk; a BUILD file of a
repository below a module that is no module itself, marked by its `REPO.bazel`, is outside it.
It does not scan fetched repositories, Bazel output trees or generated BUILD templates as if
they were maintained packages.

## snake-case-target-names

**Ordinary target names use lower snake case.** Authored logical target names follow the same
spelling as snake-case-package-paths. Consistent names make labels easy to type and distinguish
logical targets from output filenames and generated artifacts.

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
allows this separator, and enforces for every symbolic macro that its targets lie in its
namespace: the name, or the name followed by `.`, `_` or `-`. The rule adds what Bazel does
not check: the dot, the roles' spelling, and the namespaces of legacy macros. Bazel's query
evidence names each target of a symbolic macro in its own `generator_name`, as it does for
some legacy macros, so the rule cannot tell the two apart and treats them alike. The checker examines the Bazel-evaluated expansions of owned macros,
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
preserving output filenames, registration symbols and resource paths. Record the roots in
`REVIEWED` in
[snake_case_target_names.py](../../tools/conventions/rules/snake_case_target_names.py),
by BUILD path. The roots are the call's emitted names without a role; every other emitted owned
label is checked against exactly one of them. A changed root set requires renewed review; stale
reviews fail. Missing required ownership or review evidence fails the check. Incomplete review
evidence is reported as `snake-case-target-names not checked`. This strictness does not change
other conventions' coverage policy.

## no-end-to-end-tests-in-public-documentation

**Public documentation does not reference end-to-end tests.** Public guides and READMEs,
add-on modules' READMEs included, show runnable examples from `examples/`, which users can
copy, instead of the consumer scenarios and add-on end-to-end tests in `e2e/`.
The check reports each line with a concrete project path into `e2e/`, such as
`e2e/rules_godot/smoke` or `//e2e/addons/sqlite/database`, in Markdown under `docs/` and in
every README, except internal documentation (the `docs/internal/` directories of the
repository and the ruleset) and `AGENTS.md` files. Layout placeholders such as
`e2e/addons/<module>/` are not references, nor is a directory tree that spells a path over
several lines. Maintainer commands for end-to-end tests belong in internal documentation or
`AGENTS.md` files, such as [addons/AGENTS.md](../../addons/AGENTS.md).

## documented-targets-exist

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

## application-content-under-main

**Application content lives under `main/` of its physical project.** The place of a project
establishes ownership in every consumer, following
[projects-at-fixed-places](#projects-at-fixed-places). Application cases own their scenes,
scripts and exclusively used assets below `main/`; an add-on a project keeps for itself lives
there too, such as `main/addons/<name>/`. Keep authored UID/import sidecars beside sources.

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

## application-tests-under-tests

**An application's tests live in its `tests/` package.** An application's tests, such as the
exported demo's of an add-on module, never sit in the project's root package, which holds
what the application ships. The check reports every call in the root package of a project in
`examples/` whose kind ends in `_test` or is a declared test operation, a macro that declares a Godot test under its
own name, such as `godot_test` or autoload_gdunit's `gdunit_test`;
`godot_metadata_sync`'s `update.test` is a consistency check of the project and stays beside
it.

## projects-at-fixed-places

**Projects lie at the fixed places of their consumers.** Every consumer places its projects
by path:

| Consumer | Projects |
|---|---|
| Applications, `examples/` | `examples/<name>/` |
| Add-on examples, `examples/addons/<module>/` for each module `addons/<module>/` | the directory itself, and one directory of it per scenario |
| Consumer scenarios, `e2e/rules_godot/` | `e2e/rules_godot/smoke/<operating_system>/`, and `e2e/rules_godot/<scenario>/` for every other scenario |
| Add-on end-to-end tests, `e2e/addons/<module>/` | the directory itself, and one directory of it per scenario or configuration variant that needs other settings |
| Registry test modules, `<module>/bcr/<name>/` ([registry-test-module-in-bcr](#registry-test-module-in-bcr)) | the module itself, and one directory of it per project |

A project owns a BUILD file and at least one authored Godot configuration; an application, a
project directly in `examples/`, is described in the
[example guidance](../../examples/AGENTS.md#common-workflows). Related operating-system
contexts can share one project. No other module holds projects: an add-on module holds none
([no-godot-in-addon-modules](#no-godot-in-addon-modules)), and the white-box fixture projects
of the ruleset module and the input trees in a `testdata` directory of a Go test outside the
consumers, such as those of the [Gazelle language](gazelle.md#tests), are outside this check.
There is no per-directory admission list.

The check inventories the projects and the authored `project.godot` files of every consumer.
Configurations must belong to a project at a fixed place. Temporary projects constructed
inside source strings and generated configuration templates are outside the inventory. The
check does not require a project or BUILD package for each assertion.

## production-independent-of-tests

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

Bazel's own [test-only dependency check](https://bazel.build/reference/be/common-definitions#common.testonly)
rejects a production target that depends on a test-only target; test operations and most
test packages mark their targets test-only
([test packages](verification-architecture.md#test-only-packages)). The rule covers what that
check leaves through: source files of a test scope, and targets of a test scope that are not
marked test-only, such as those of a mixed package. It resolves inputs from authored label,
label-list and label-keyed-string attributes, resolved by Bazel to their defining target or
source file across the workspace's modules. Declarations inside a test scope and test-only
targets are consumers, not subjects; a test-only input is left to Bazel. Missing effective
role flags are reported as not checked. Indirect paths and configured closures remain
outside this automated subset.

## no-internal-links-in-public-documentation

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

## engine-files-under-engines

**Engine modules, patches and lock files live under `engines/<name>/`.** A custom
engine is a shared resource of the repository, not a part of one application: its directory
`engines/<engine name>/` may lie anywhere in a consumer module, such as `engines/` at the
root of a consuming repository or beside the scenarios that register it, and every
application and test that names the engine uses it. It keeps each custom engine module in
`modules/<module>/`, each engine patch as a `.patch` or `.diff` file directly in
`patches/`, its lock file, `<engine name>.lock.json`, and the `.bzl` files of the
engine, such as a gate that keeps targets out of builds with another engine, directly in
the directory. A `README.md` and a BUILD file also belong there. Registration sets that
only declare engine components, such as `engines/stable/`, follow the same layout with a
BUILD file and `.bzl` files. Readers and source recipes find an engine's inputs in one
place, separate from the application content under `main/`.

```text
engines/<engine name>/
  BUILD.bazel
  README.md
  <engine name>.lock.json     # the engine's lock file
  <gate>.bzl
  modules/
    <module>/                 # config.py, SCsub, register_types.cpp, sources, BUILD.bazel
  patches/
    BUILD.bazel               # exports the patches to the module's recipes
    <change>.patch
```

The check inventories the files of every consumer module. In each `engines/<name>/`
directory it reports:

- any entry other than `modules/`, `patches/`, a BUILD file, lock files, `.bzl` files and
  `README.md`;
- any file directly in `modules/`, and any directory there without both `config.py` and
  `SCsub`;
- any entry of `patches/` other than `.patch`/`.diff` files and a BUILD file, including
  subdirectories.

Elsewhere in the consumer module it reports any engine module directory (a directory
owning `config.py` together with `SCsub` or `register_types.*`), and in every Godot
project, marked by its `project.godot`, any `.patch`/`.diff` file and any `.lock.json` file
that is not in an `engines/<name>/` directory. A nested project owns its own files.

A stray directory is reported once, at its first file. An add-on's own `register_types.*`
without `config.py` is an extension, not an engine module. Files outside every project,
such as dependency patches in `third_party/`, and lock files at the root
of the repository, such as `multitool.lock.json`, are outside this rule. The check does not
read module or patch contents and does not prove that a recipe consumes them.

## addon-module-named-after-directory

**The module `addons/<module>/` is named `autoload_<module>`.** This repository's add-on
modules follow the add-on generator's template, so that the same tasks build, test and
release every module and nothing but the root module's declaration lists it; the root module
names each by the module name its `MODULE.bazel` declares. The check reads that declaration.

## addon-modules-own-template-files

**Add-on modules own the files of the generator's template.** Each module owns the files of
the generator's module template, such as `MODULE.bazel`, `README.md`, `REPO.bazel`,
`BUILD.bazel`, `.bazelrc`, `.bazelignore` and its registry test module `bcr/smoke`, and its
registry templates in `.bcr/addons/<module>/`: `metadata.template.json`, `presubmit.yml` and
`source.template.json`. The contents of those that every module shares are what the
generator writes ([shared-module-files-as-generated](#shared-module-files-as-generated)).

## registry-templates-have-their-module

**Registry templates belong to an existing add-on module.** Templates in
`.bcr/addons/<module>/` are removed with their module; the check reports a directory there
whose module `addons/<module>/` does not exist.

## no-stray-entries-in-addon-module-roots

**An add-on module's root holds only its files, add-ons and the packages others load.** The
root holds the template's files and its lock file, its add-ons, `third_party/` with what
makes its dependencies usable, `tests/` for module-wide unit tests, `bcr/`, and packages that
a Starlark file outside them names by label, as `//<package>` in the module or
`@autoload_<module>//<package>` anywhere, such as Firebase's `config`. An add-on is a
directory whose BUILD file declares a target named like it, as the generator writes it. The
check thus rejects directories nothing uses rather than keep a list of allowed packages.

## no-test-only-dependencies-in-addon-modules

**Add-on modules have no regular dependency that only their tests load.** Every consumer
inherits a module's regular dependencies. CI builds the module from the root module, where
its development dependencies are not active, so tests that need such a library live in
`e2e/addons/<module>/`. The check reports a regular `bazel_dep` whose repository only Starlark
files in `tests/` directories name.

## addon-module-examples-define-edit-and-pack

**Every add-on module has example projects, each defining `edit` and `pack`.** A module has
at least one example project in the root module's `examples/addons/<module>/`, the directory
itself or one subdirectory per scenario. An example project that builds an application
defines `app` too, which its release builds of `examples/releases.bzl` require. The check
reads the parsed calls of the BUILD files; a target name that is no string literal is
reported as not checked.

## unique-extension-names

**No two add-on modules' extensions share a name.** On iOS the name of a `godot_cc_extension`
names the extension's framework, and an application's frameworks share one directory. The
check reads the parsed calls of the add-on modules' BUILD files; a name that is no string
literal is reported as not checked.

## backends-under-native

**An add-on's backends live in its `native/backends/`.** In every add-on, including those of
`examples/`, a `backends/` directory sits in `native/`: the backends implement the
platform-independent API beside them. The check reports a stray `backends/` directory once.

## no-claude-md

**Agent instructions live in `AGENTS.md`.** Claude Code and Codex both read `AGENTS.md`, but
Claude Code ignores it while a `CLAUDE.md` exists in its working directory or above it. The
check reports every `CLAUDE.md`; rules for one agent alone go into `AGENTS.md`, marked as such.

## linked-skills

**Skills live in `.agents/skills` and are linked for Claude Code.** A skill is written once,
as a directory `.agents/skills/<name>/` with a `SKILL.md`, where Codex finds it. Claude Code
finds project skills only in `.claude/skills/`, so `.claude/skills/<name>` is a symbolic link
to `../../.agents/skills/<name>`. `.claude/skills/` holds nothing else: no copies and no
skills without a counterpart.

## project-named-after-directory

**A package's Godot project is named like its directory.** A package that holds a
`project.godot` and declares projects names one of them like its directory, so the package's
own label names its project: `//examples/addons/sqlite` and `//e2e/addons/sqlite`, not
`//examples/addons/sqlite:demo`. Write that short form in labels and commands; in BUILD
files, `aspect format` rewrites the long form of the label attributes that
`tools/format/buildifier_tables.json` names, such as `project` and `pack`. Further
projects of the package, such as a test project beside an application's, take names of their
own. This applies everywhere, the ruleset's fixtures included.

The check reads the `godot_project` calls of every module and reports each package with a
`project.godot` whose projects include none named like its directory. A package without a
`project.godot`, whose project reads its configuration from elsewhere, is outside the check.

## registry-test-module-in-bcr

**Released modules have a registry test module in `bcr/`.** The Bazel Central Registry
tests a release by building a test module from the release archive. Each released module,
the ruleset and every add-on module, has that module in `bcr/<name>/`, so that it is
recognizable by its place:

- the module's registry templates, `.bcr/<module>/presubmit.yml`, run it as their
  `bcr_test_module` with `module_path: "bcr/<name>"`;
- the module's `.bazelignore` lists `bcr`, since each test module is a Bazel module of its
  own;
- the test module is a consumer with a flat project: the test module itself is the project,
  or each project lies directly in one of its directories, which
  [projects-at-fixed-places](#projects-at-fixed-places) checks.

A test module registers the official engine itself, as an application does; the add-on
modules register none for consumers. The add-on generator writes `bcr/smoke` with every new
module. `python3 -m tools.ci.release_archive` runs each test module from its module's release
archive, as the release workflow and the registry do.

## no-godot-in-addon-modules

**Add-on modules run no Godot; their end-to-end tests live in the root module.** An add-on
module holds its add-ons and the unit tests of their code. A test that uses an add-on as an
application does, by running Godot or building a project, is an end-to-end test and lives in
`e2e/addons/<module>/`. There the root module declares what the test uses as development
dependencies, which an add-on module could only declare as regular dependencies that every
consumer inherits: CI builds add-on modules from the root module, where their own
development dependencies are not active.

The check reports, in each add-on module but its registry test modules, every
`project.godot` and every call of `godot_project`, `godot_test`, `godot_metadata_sync`,
`godot_runtime_profile` or a macro that declares a Godot test under its own name, such as
`gdunit_test`.

## no-component-names-in-tooling

**The Python tooling names no add-on module or application.** The tools read what is
specific to a component from its own files, such as its `MODULE.bazel` and BUILD files, or
from Bazel. A new component then needs no change of the tooling, and what is special about
one stays visible beside it.

The check reads the string literals of every Python file in `tools/`, docstrings included,
apart from tests and their support, and reports each that names an add-on module or an
application of `examples/` as a word, also inside a flag or label, such as `--config=<name>`
or `@autoload_<module>//`; a file extension such as `.dart` names none. Comments may name
components, such as to explain an exception.

## release-archives-without-tests

**Release archives leave out tests, and nothing else needs them.** The ruleset and every add-on
module are released as a `git archive` of their directory
(`.github/workflows/release_prep.sh`). Consumers cannot run a module's tests, whose development
dependencies are not theirs, so each released module's `.gitattributes` leaves every `tests/`
directory, at any depth, out of the archive: `tests export-ignore`. The registry test modules
in `bcr/` keep theirs, since the registry runs them from the archive
([registry-test-module-in-bcr](#registry-test-module-in-bcr)): `bcr/**/tests -export-ignore`. A
package that would then name a missing file or package fails to load for every consumer, so no
Starlark file outside a `tests/` directory may use a path or label inside one. Test code and
fixtures that a package outside `tests/` needs belong to a `tests/` package of their own.

The check parses each released module's BUILD files, `MODULE.bazel` and `.bzl` files. Names
that are never loaded are allowed: target visibility, `package_group` packages and load
visibility, and the arguments of dev dependencies in `MODULE.bazel`, which only the module's
own builds evaluate. Modules that are never released, such as the root module, are outside
it.

## shared-module-files-as-generated

**Add-on modules keep the shared files as the add-on generator writes them.** Some files of
the generator's module template are settings every module shares: `.bazelignore`, `.bazelrc`,
`.bazelversion`, `.gitattributes`, `.gitignore`, `REPO.bazel` and the registry test module's
`.bazelrc` and `.bazelversion`, and the registry templates `presubmit.yml`,
`source.template.json` and `metadata.template.json` in `.bcr/addons/<module>/`. They are
listed in [tools/addons/new.py](../../tools/addons/new.py) and stay as the generator writes
them, so a change of the template or of the ruleset's metadata reaches every module:
`aspect generate` writes them again for every add-on module, and the check compares each with
what the generator writes. A module's own files, such as its `MODULE.bazel` and `README.md`,
are outside it.

## region-headers-named-in-head

**Regions start with a region header the file's head names.** A file with several topics is
divided into regions, so that a reader who scans it finds a topic and skips the rest. A region
starts with its region header, a line the eye catches: the comment marker, four `=`, the
region's name, and `=` up to column 80. It runs to the next region header or to the end of
the file; there is no end marker.

```python
# ==== Lexer ===================================================================
```

Python, Starlark (`.bzl`, BUILD files, `MODULE.bazel`) and GDScript start the header with `#`,
C and C++ with `//`; Markdown's headings are its regions. What the whole file needs stands
above the first region header. The file's head names the regions in their order: the
docstring of a Python or Starlark module, the comments above the first region header
elsewhere, with a line such as `Sections: Lexer, Graph.`

The check reports a region header of another width or marker, an indented one, a comment that
marks a section in another form, such as `# ---`, `#region` or `MARK:`, and a head whose list
of regions is missing or differs; in Python it reads comments only, not lines inside strings.
A Python region declares at least two names. Whether a file
needs regions at all is a matter of review: a file with one topic has none. The repository's
`.vscode/settings.json` shows region headers in VS Code's minimap.

## definitions-before-callers

**Python definitions stand before their first caller.** A module reads from its helpers up to
what uses them, in the order Starlark requires on its top level; the head and the region
headers lead a reader to the entry points. A top-level function or class stands above the
first top-level function or class that names it. Definitions that name each other, directly
or through others, are exempt, since one of them has to come second.

The check parses every Python module of the repository; one that does not parse fails the
audit, as for [release-archives-without-tests](#release-archives-without-tests). It reads
names, so a definition that passes another on without calling it counts as a caller as well.
Starlark files are outside it.

## godot-process-tests-tagged

**Tests that start a Godot process carry the `godot_process` tag.** A Godot process, in the
test's build or in the test itself, is what makes a test expensive to rerun; the fast tests
(`--config=fast` of the root module and the ruleset, which `aspect check` runs) are every
test without the tag.
A smoke test starts one and still runs with the fast tests, so it carries no tag; analysis
tests start none, and `manual` tests run only when named.

`godot_test`, and every test operation built on it, such as `gdunit_test`, adds the tag
itself unless the test is tagged `smoke`, so the check leaves the tests it declares out and
judges the others, such as the build tests of applications and the inspection tests of
built outputs. It queries each module's tests that depend on a Godot toolchain type (the editor, the
runtime or the target execution toolchain type of `@autoload_rules_godot//godot`) and reports
such a test without the tag, a test with the tag that depends on none, and a smoke test with
the tag. Registry test modules are outside it.

## Run and maintain the checks

From the repository root:

```sh
bazel run //tools/conventions
```

The command runs every registered convention rule that judges more than one file at a time
across all owned modules. Violations include the rule's name, file, line and a link to this
catalogue. The checker reports unreviewed computed macro names separately. Exit status `1`
indicates convention findings; `2` indicates an incomplete audit. `aspect check`, the
pre-push hook's, and the Linux job run this command.

The rules that judge each file on its own,
[snake-case-package-paths](#snake-case-package-paths), [no-claude-md](#no-claude-md),
[no-end-to-end-tests-in-public-documentation](#no-end-to-end-tests-in-public-documentation),
[no-internal-links-in-public-documentation](#no-internal-links-in-public-documentation),
[region-headers-named-in-head](#region-headers-named-in-head),
[definitions-before-callers](#definitions-before-callers) and
[shared-module-files-as-generated](#shared-module-files-as-generated), run in the
[file lint](verification-recipes.md#the-file-lint) instead, on the files it selects: the
changed files in `aspect check` and the pre-commit hook, every file Git lists in the Linux job.
[files.py](../../tools/conventions/files.py) takes the files by their paths in the repository;
each rule picks its own among them.
`bazel run //tools/conventions -- --rule region-headers-named-in-head` still runs one of them
over the whole checkout, as `/code-health` does.

The Bazel tool caches each loading query's output in `~/.cache/autoload/conventions` (or below
`XDG_CACHE_HOME`), under a key of the query and of everything Bazel's loading can read: the
listed files and the contents of each, but for code that builds compile, assets they
package and documentation, such as Python, GDScript, C++, images or Markdown, which count by
name only
([cache.py](../../tools/conventions/cache.py)). While none of that changes, a run starts no
Bazel server, and the rules evaluate the cached evidence as always. A failed query is never
cached; an entry whose external repositories are gone from the output base misses, and only
the entries of the most recent loading inputs are kept.

Run one rule independently or list the registered rules:

```sh
bazel run //tools/conventions -- --rule project-named-after-directory
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
`evaluate(context) -> Iterable[Finding]`. Its own module owns its name, title, applicability,
predicates, artifact qualifications, incomplete-coverage findings and records of reviewed
sites. Tests live beside the rule. No rule's implementation is placed in the CLI or tool
adapters.

The [framework](../../tools/conventions/framework.py) validates unique names, invokes rules
against one context and attaches their metadata to findings. It sorts diagnostics for
stable output. A rule reports each finding once; a repeated finding is a rule defect and
aborts the run rather than being merged. The rules that judge each file on its own are
registered in [per_file.py](../../tools/conventions/per_file.py), whose library needs no
Bazel: the file lint runs them, and the CLI only when they are named.
`Finding.status` distinguishes `violation` from
`not_checked` for every rule. The [registry](../../tools/conventions/registry.py) lists
the rules explicitly and selects them by name, and the [CLI](../../tools/conventions/check.py)
formats results and chooses the exit status.

The [context](../../tools/conventions/context.py) exposes read-only evidence tools: the
workspace files, documents, modules and projects, Starlark calls, Bazel rules and
inspection, and the joins of them (`context.calls`, `context.target_names`,
`context.declarations`, `context.sources`). The Bazel tool,
which runs the modules' loading queries, is [bazel.py](../../tools/conventions/bazel.py);
the context decodes its output. The public
members of `context.py` carry their documentation. The documentation rules share
[documents](../../tools/conventions/documents.py): which pages are internal and the local
link destinations of a Markdown source. The add-on module rules share
[addon_modules](../../tools/conventions/addon_modules.py): the add-on modules, the files of
the generator's module template and the files of a module. A rule imports evidence modules
only, never another rule's module.

Tools load evidence lazily, cache it per tool/context instance and return immutable records and
read-only attribute maps. Bazel evidence covers the loaded modules
(`workspace.loaded_modules`): every module but the registry test modules, which build only from
a release archive ([registry-test-module-in-bcr](#registry-test-module-in-bcr)). They load in
two Bazel workspaces, each with one server: the ruleset in its own, since only it sees its
development dependencies, and the root module with the add-on modules, which it names through
their repositories, `@autoload_<module>//`; the tool names their labels as the module itself
does. A workspace loads all of its modules in one query. The first `context.declarations` call
loads the calls and rules of every loaded module, the two workspaces concurrently. The rules
that read declarations share their data, and the documentation-label rule resolves labels
against the same per-module query, so no query runs twice. Missing or ambiguous source evidence
and failed tools raise `EvidenceError` and abort the audit; they are not converted into an
empty successful result.

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
- Starlark is read by two parsers and evaluated by neither: Buildozer for the calls of BUILD
  files, and Python's parser, whose syntax covers Starlark's, for what Buildozer does not
  expose, the string literals of BUILD, `MODULE.bazel` and `.bzl` files and the declarations
  of `MODULE.bazel` ([tools/setup/modules.py](../../tools/setup/modules.py)). Buildozer prints
  another name for a call whose `name` is computed, such as the package's inside a
  comprehension, so Python's parser reads Buildozer's formatted call to tell whether `name`
  is a string literal. No regular expression or token scan reads Starlark.
- Semgrep patterns and `rules_lint` alone supply neither the Starlark nor the ownership
  semantics the rules need; ast-grep and Semgrep have no Starlark grammar, and Buildifier and
  Ruff have no plugin interface, so no external engine replaces the checker. Rules that other
  tools enforce are retired instead, as the beginning of this page lists.
- alint 0.23 (November 2026), whose built-in rules check a repository's shape, was tried for
  the rules about files and directories and rejected. It expressed the `CLAUDE.md` rule
  ([no-claude-md](#no-claude-md)) fully, the package segments
  ([snake-case-package-paths](#snake-case-package-paths)) only with a message that names the
  BUILD file but not the segment, and the engine layout
  ([engine-files-under-engines](#engine-files-under-engines)) with nine rules that report two
  of its cases twice; a `**` inside a brace pattern matched nothing without an error. It has no
  rule for the target of a symbolic link ([linked-skills](#linked-skills)) or for a call's name
  ([project-named-after-directory](#project-named-after-directory)). Its whole-tree run took
  0.3 s. One rule it expresses fully does not outweigh a pre-1.0 binary with one maintainer, a
  release every few days and a second rule language beside the checker's.
- The contents of files that the add-on generator writes are checked by comparing them with
  what it writes ([shared-module-files-as-generated](#shared-module-files-as-generated)), not
  by a second description of the same content.
- [Pluggy](https://pluggy.readthedocs.io/en/stable/) would provide hook registration and
  result collection, but the domain context and evidence adapters would still be ours, so
  rules are registered explicitly and not discovered.

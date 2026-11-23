# Capability Matrix

This register records user outcomes, observed workflows and open capability candidates for
rules_godot. Use the [overview](capability-overview.md) for navigation and this matrix to
compare designs and choose specification scope.

**Coverage snapshot:** 2026-11-01, assessed against repository commit
`506d045ec401effdcb93986dfa0ca2064dbfd78a`, Godot 4.7.2 and Bazel 9.3.0.
Goal decisions and their reasons are recorded below independently of this implementation
snapshot. This reference stands on its own; changes may cite it without owning it.
ADD-09's published blueprint coverage, DX-05's example naming description and the add-on
and loadable pack coverage of ADD-07 and PCK-08 and the script check coverage of CHK-01 to
CHK-03 track the current owning guidance; other
coverage entries retain the named baseline above.

## Maintaining capability references

Apply [design freedom](#authority-and-design-freedom), record the [goal basis](#goal-basis)
and keep the [assessment axes](#read-the-axes-independently) separate. These sections own the
meaning of desired, observed and open capabilities; implementation is not a requirement.
Configuration goals describe reuse and deliberate operation-specific differences, not an
assumed shared declaration or configuration object. Assess the stated workflow rather than
counting a generic prerequisite as partial implementation. Give related outcomes a leading
entry and preserve old IDs through explicit references instead of duplicate status records.

## Authority and design freedom

Existing implementation is evidence, not a feature-parity or compatibility contract.
A better model may replace, combine, restrict or omit an observed workflow. User needs,
the [design principles][PRINCIPLES] and a change's agreed scope govern that decision; neither a listed ID
nor an implementation status creates a requirement. Stable IDs preserve references rather
than freezing public concepts, action boundaries or workflow granularity.

A feature may explicitly choose behavior preservation. That local decision does not impose
preservation on future API work. Goal labels below describe desired outcomes, with precise
scenarios and acceptance chosen by a spec. They do not prescribe the current implementation.

## Goal basis

The `U-*` records own the user-selected product direction, including its boundaries. They
are recorded decisions, not conclusions inferred from code. The `P-*` records cite governing
principles. Every G row links to its rationale here; coverage sources establish different
claims and are listed separately. New implementation alone cannot justify a new G label.

| Basis record | Origin | Recorded need and boundary |
|---|---|---|
| <a id="goal-engines">U-ENGINES</a> | User direction | Use official prebuilt and source-built engines for editor and runtime workflows. No commitment to every build option or CPU. |
| <a id="goal-editor">U-EDITOR</a> | User direction | Work live in the Godot editor, including editing, creating, renaming and deleting owned resources, and use changes in later builds. BUILD declaration updates may remain manual; editor view/writeback/sidecar mechanisms remain design choices. |
| <a id="goal-checks">U-CHECKS</a> | User direction | Obtain GDScript checks in the relevant context. This does not select today's checker adapter or case granularity. |
| <a id="goal-tests">U-TESTS</a> | User direction | Run GdUnit suites with the context and dependencies needed for meaningful feedback. Test target declarations and configuration composition remain open. |
| <a id="goal-packs">U-PACKS</a> | User direction | Produce main and DLC content packs, including dependencies and optional content. Pack metadata and delivery interfaces are not selected. |
| <a id="goal-addons">U-ADDONS</a> | User direction | Consume external/prebuilt add-ons and develop owned add-ons; support godot-cpp and native backends, including Android lifecycle integration when needed. Script/resource add-ons do not need a native API. |
| <a id="goal-sentry">U-SENTRY</a> | User reference case | Evaluate prebuilt Sentry consumption as a concrete add-on case. A future spec selects the vendor version, features and operating-system cells; no full vendor acceptance is established. |
| <a id="goal-config">U-CONFIG</a> | User direction, refined 2026-11-01 | Avoid redundant configuration and unintended drift across operations while allowing deliberate differences, including test-specific overrides. No single common project declaration, file or configuration object is required. |
| <a id="goal-selection">U-SELECTION</a> | User direction | Prepare the resources and real context dependencies needed by an operation, rather than unrelated application content. Resource ownership and configuration can be reused under different selections. |
| <a id="goal-platforms">U-PLATFORMS</a> | User direction | Produce runnable applications for Linux, macOS, Android and iOS and retarget equivalent pack/application workflows through build configuration. Formats, signing and individual ABI/device combinations need their own scope; no facade or dispatcher is selected. |
| <a id="goal-layout">U-LAYOUT</a> | User-selected conventions | Use cohesive ownership/package boundaries, acyclic target dependencies and explicit consistent local names. Different targets may justify dependencies in both directions between packages; a package-level cycle alone does not require restructuring. In this repository, whether a directory is a project or an add-on follows `{examples,tests}/{projects,addons}/<name>/`: applications use projects, reusable add-ons use addons in both areas. This does not prescribe an unrelated consumer workspace root. Every add-on has separate `demo/` and `tests/` Godot projects, with needed `unit/` and `integration/` test packages and direct package-named test executables. Deterministic Godot API contracts count as unit tests; real operating-system behavior counts as integration tests. Native unit tests stay add-on/backend-owned and independent of those projects. Application content lives under `main/` and game tests under `tests/`. BUILD `name` arguments remain explicit; package and target names use `lower_snake_case`; clear main targets match the package and use short labels. No rule or provider design follows. |
| <a id="goal-iteration">U-ITERATION</a> | User direction | Get fast incremental builds and checks/tests after native or Godot-resource changes by repeating only affected work. No independent cache or per-test-case scheduler is implied. |
| <a id="goal-reuse">P-REUSE</a> | [Principle I][PRINCIPLE-I] | Avoid unnecessary work across the edit-to-feedback path; preserve unaffected artifacts and valid results. |
| <a id="goal-correctness">P-CORRECT</a> | [Principle II][PRINCIPLE-II] and [IV][PRINCIPLE-IV] | Model relevant build/execution dependencies soundly and make deliberate support tradeoffs. This does not require support for every importer or Godot facility. |
| <a id="goal-usability">P-USABILITY</a> | [Principle III][PRINCIPLE-III] | Keep declarations understandable, avoid reliably derivable wiring and make effects of changes predictable. Existing rule boundaries are revisable. |

## Read the axes independently

| Axis | Values / interpretation |
|---|---|
| Basis | **O** observed workflow, no preservation commitment; **G** desired outcome with a goal-basis reference; **C** candidate whose product scope remains open |
| Coverage | **I** implemented for the row's stated scenario; **P** only part of that scenario is implemented, with the gap named; **N** the stated workflow is not implemented; **U** not sufficiently assessed |
| Scope decision | **Selected** explicitly chosen direction within its stated boundary; **Open** not decided; **Excluded** explicitly not a goal, with a reason. These say nothing about implementation. |
| Applicability | **—** the combination does not apply to the row as defined; not a substitute for open scope or unassessed coverage |
| Assessment basis | **Docs** support/reference documentation; **Inventory** API/source inventory; **Research** the pinned pipeline catalogue; **Source** directly linked code inspection; **Run** execution evidence; **Device** device/signing evidence |

G can already be implemented, and I does not imply G. N/P does not mandate closing a gap.
Open scope and U coverage are different questions. A facet cell `open / U` records both;
plain I/P/N/U cells report coverage only and do not select future scope. Open
execution-platform/signing cells are not proposed support commitments or priorities and
need assessment only if selected.

Assess coverage against the outcome as worded. If a limit excludes part of that outcome,
mark P, state an explicitly bounded subcase, or leave U until assessed. Do not redefine a
desired outcome from current code merely to mark it I. A generic prerequisite does not
establish partial implementation of a more specific end-to-end workflow. Composition support
is assessed independently of example adoption. Published-guidance outcomes such as ADD-09
are assessed against the public reference available to consumers, not migration task counts.

Assessment-basis tags identify the evidence behind the recorded assessment, including gaps
and unknowns. Docs/Inventory are not execution proof; Research inherits its named scope,
not a fresh audit of every row. No new runtime/device verification is claimed by this matrix.

## Scope decisions and open boundaries

| Topic | Decision | Reason / source |
|---|---|---|
| Initial operating systems of applications | Selected: Linux, macOS, Android, iOS; individual cells still need feature scope | [U-PLATFORMS] |
| Package-named main entries and Bazel's short labels | Selected; explicit BUILD names, no default-name wrappers | Naming convention, [U-LAYOUT] |
| Configuration reuse and operation-specific differences | Selected outcome; declaration structure open | [U-CONFIG]; intentional test overrides are allowed |
| Additional execution platforms, including Windows and editing on mobile devices | Open | Current assessed workflows execute on desktop Linux/macOS; no commitment to further execution platforms follows |
| Additional operating systems of applications, including Windows and Web | Open | The initial operating systems do not settle expansion |
| Managed .NET/C# workflows | Open | Language/runtime scope is separate from execution platform and operating system of the application |
| AAB upload signing within Bazel | Open | Current workflow delegates it externally [PLAT]; that boundary is not a permanent exclusion |
| Mobile install/launch and packaged GdUnit execution | Open candidates | RUN-06 and TST-07 |
| Declarative API/backend glue generation | Open candidate | GEN-01/02/04; a Pigeon-like approach is exploratory, not a selected generator architecture |
| Add-on composition declaration(s) | Open | Compatible consumption/authoring expectations are needed; one contract or a dedicated rule is not selected |

## Dimension and scenario checklist

A spec chooses relevant dimensions and explains its scope. This is a checklist, not a
requirement to cover their Cartesian product.

| Dimension | Distinguish |
|---|---|
| Workflow / selection | Edit, check, test, run, process, deliver; application, reusable add-on, suite, helper, main/DLC pack |
| Execution platform | Operating system and CPU of the engine/tool process; the host controlling a run and actual device execution are different |
| Operating system of the application | Target operating system, CPU and ABI, device/simulator and applicable artifact format |
| Engine / configuration | Prebuilt, source-built or supplied; editor/runtime; API/ABI, features, renderer and deliberate operation-specific settings |
| Content / acquisition | Authored/generated/external; resources/GDScript, extension, Android plugin or other platform libraries; source/prebuilt independently |
| Phase / dependencies | Processing/editor/execution/delivery participation and the resources, tools and native dependencies actually needed |
| Validity / evidence | Deterministic inputs versus live state; documentation/source, artifact/execution, simulator/device and signing evidence |

## Capability inventory

Each row records an outcome or workflow and its current coverage. Source abbreviations link
to the [source register](#sources). Placement helps discuss relationships and reuse; it does
not prescribe future scope, public rules or unconditional action dependencies.

### Foundations

#### Engine selection and builds

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-eng-01">ENG-01</a> | Acquire and use a pinned prebuilt editor without a globally installed Godot. | G [U-ENGINES] | I | Supported distribution/version/editor platform constraints still apply. | Docs | [ROOT] [VERS] |
| <a id="cap-eng-02">ENG-02</a> | Use prebuilt runtimes/templates for supported export platforms. | G [U-ENGINES] | I | Runtime availability and device/simulator CPUs are artifact-specific. | Docs | [PLAT] [ENG] |
| <a id="cap-eng-03">ENG-03</a> | Build an editor from pinned source. | G [U-ENGINES] | I | Supported source-build/configure/module scope; no universal SCsub support claim. | Docs | [ENG] |
| <a id="cap-eng-04">ENG-04</a> | Build a runtime from source for the required target platform and ABI. | G [U-ENGINES] | I | Per-target SDK/toolchain/source-build boundaries apply. | Docs | [ENG] |
| <a id="cap-eng-05">ENG-05</a> | Apply patches, select engine modules/options and include owned custom modules. | O | I | Source configure/generator/native dependencies are explicit within supported scope. | Docs | [ENG] |
| <a id="cap-eng-06">ENG-06</a> | Use a supplied compatible editor/runtime and the files it needs beside it. | O | I | Actual binary/provider identity matters in addition to a version string. | Docs, Inventory | [API] [ENG] |
| <a id="cap-eng-07">ENG-07</a> | Keep editor, runtime, extension API/ABI, precision and variant choices compatible. | O | I | Compatibility checks and explicit choices exist; vendor combinations still need assessment. | Docs | [VERS] [EXT] [ENG] |

#### Resources and project context

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-res-01">RES-01</a> | Reuse a scene, script or asset set in several projects without copying its source declaration. | O | I | Resource ownership is context-free; each project imports the resources under its own settings. | Docs, Inventory | [RES] [API] |
| <a id="cap-res-02">RES-02</a> | Use generated and external resources at deliberate, stable logical resource paths. | O | I | Generated/external inputs and explicit resource paths are supported; ownership remains explicit. | Docs | [RES] |
| <a id="cap-res-03">RES-03</a> | Compose shared and application-specific resources without packaging them prematurely. | O | I | Resource composition is independent of producing a PCK. | Docs | [RES] |
| <a id="cap-res-04">RES-04</a> | Declare dynamic resource dependencies and runtime reference cycles without cyclic build dependencies. | O | I | Dynamic/opaque access needs explicit declarations; discovery is bounded. A setting or declared runtime reference that names a directory reaches every member below it. | Docs, Research | [RES] [CAT] |
| <a id="cap-res-05">RES-05</a> | Contribute settings and autoloads from reused resources and resolve conflicts deliberately. | O | I | Explicit conflicts/overrides exist; settings do not discover dependency files. | Docs | [RES] |
| <a id="cap-res-06">RES-06</a> | Avoid redundant configuration and unintended drift across editor, checks, tests, runs and export, with deliberate operation-specific differences. | G [U-CONFIG] | P | Authored settings can be reused; current test adapters compose their own projects and can repeat settings/dependencies. Reuse and explicit override ergonomics are incomplete. | Docs, Research, Source | [DEV] [ADAPTER] [CAT] |
| <a id="cap-res-07">RES-07</a> | Choose only an operation's required resources while preserving its configuration-required dependencies. | G [U-SELECTION] [P-CORRECT] | P | Small test compositions are possible; broad preparation inputs and configuration-required dependencies still limit selection precision. See FAST-06 for preparation cost. | Docs, Research | [DEV] [CAT] |
| <a id="cap-res-08">RES-08</a> | Use the same sources under different configurations with correct identities and generated metadata. | O | I | Different projects are supported; equal sources alone do not imply interchangeable imports/UIDs. | Docs, Research | [RES] [CAT] |
| <a id="cap-res-09">RES-09</a> | Detect conflicting resource paths, authored identities and missing declared dependencies. | O | I | Static diagnostics have format/dynamic limits; they do not prove arbitrary code hermetic. | Docs, Research | [RES] [CAT] |
| <a id="cap-res-10">RES-10</a> | Keep production content independent of test-only sources and frameworks. | G [U-LAYOUT] | I | Separate production/test resource compositions are available. | Docs, Research | [LAYOUT] [TESTS] [CAT] |

#### Add-on consumption and development

An add-on is a reusable composition. Its contents can include resources/GDScript, a
extension, an Android plugin, platform libraries and editor/import/export tools.
These are compatible roles of an add-on's parts, not mutually exclusive add-on categories. Owned versus
external and source-built versus prebuilt are separate dimensions.

Consumption and authoring need compatible expectations for contents, variants, activation
and dependency propagation. Whether one contract or several declarations should express
those expectations remains open. Both workflows can use shared operations; a
script/resource add-on need not define a native API or operating-system backend. Extensions
and platform libraries may also be used directly. See the add-on composition question below.

##### Add-on composition expectations

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-add-07">ADD-07</a> | Propagate add-on resources, settings, extensions and platform libraries so consumers do not repeat internal dependency lists. | G [U-ADDONS] [P-USABILITY] | I | `godot_addon` declares an add-on's runtime and editor parts, autoloads, settings, extensions, platform libraries and Info.plist fragments once, with the add-ons it needs. Every operation whose resources use the add-on, or whose project names it, contains them; applications deliver the native code of the add-ons of every pack they ship (PCK-08). Project-specific plugin activation is intentional (ADD-02), not itself a propagation gap. | Docs, Source | [RES] [PLAT] |

##### Extensions and platform libraries of add-ons

An extension can provide the Godot-facing API while an Android plugin supplies Android
context/lifecycle integration. A source-built add-on and a vendor-prebuilt add-on can use
the same composition pattern. Library origin and library kind must not be conflated.

###### GDExtension integration

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-ext-01">EXT-01</a> | Build a compatible C++ Godot-facing extension with godot-cpp. | G [U-ADDONS] | I | Binding acquisition and generated C++ library integration exist. | Docs | [EXT] [VERS] |
| <a id="cap-ext-02">EXT-02</a> | Build a C-compatible extension without requiring godot-cpp. | O | I | Existing C ABI fixtures use the extension integration. | Docs, Inventory | [API] [EXT] |
| <a id="cap-ext-03">EXT-03</a> | Consume compatible prebuilt extension variants without rebuilding vendor source. | G [U-ADDONS] | I | Feature-tagged libraries/XCFramework/static provider constraints apply. | Docs | [EXT] |
| <a id="cap-ext-04">EXT-04</a> | Provide an extension editor library while building a different extension runtime library. | O | I | A shared extension editor library beside an iOS static or other shared extension runtime library is supported. | Docs | [EXT] |
| <a id="cap-ext-05">EXT-05</a> | Carry dependent libraries, entry symbols and the registration/link requirements of each operating system. | O | I | Includes static iOS retention and Android/Apple platform dependency providers. | Docs | [EXT] [PLAT] |
| <a id="cap-ext-06">EXT-06</a> | Preserve deliberate library identity and compatible debug/release selection when composed with other extensions. | O | I | Unique names/entry symbols and actual descriptor feature selection matter. | Docs | [EXT] [PLAT] |

###### Android plugin integration

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-add-06">ADD-06</a> | Use native Android code with Godot Android plugin registration and lifecycle access. | G [U-ADDONS] | I | Platform Paths demonstrates plugin/context integration; acceptance of individual lifecycle hooks is feature-specific. | Docs | [PATHS] [PLAT] |

##### Consume add-ons

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-add-01">ADD-01</a> | Consume externally sourced GDScript/resource add-ons without copying sources into an application. | G [U-ADDONS] | I | External acquisition uses normal dependency tools plus resource adaptation. | Docs | [RES] [LAYOUT] |
| <a id="cap-add-02">ADD-02</a> | Consume external editor/import/export add-ons with deliberate activation. | O | I | Plugin phase/closure constraints from IMP apply. | Docs | [RES] |
| <a id="cap-add-03">ADD-03</a> | Consume prebuilt native add-ons with their extension editor and runtime libraries and platform dependencies. | G [U-ADDONS] | I | Extension and platform library integrations exist; this is not proof of every vendor distribution. | Docs | [EXT] [PLAT] |
| <a id="cap-add-04">ADD-04</a> | Use a pinned Sentry add-on in editor and exported applications across operating-system cells selected by a future spec. | G [U-SENTRY] | U | A consumption template exists; vendor version/features and complete consumer behavior remain unassessed. | Docs, Research | [EXT] [CAT] |

##### Develop and distribute add-ons

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-add-11">ADD-11</a> | Author reusable add-on contents and any needed Godot-facing API that demo/test projects and applications consume through declared dependencies. | G [U-ADDONS] | I | The documented script/resource and extension patterns support owned reusable compositions. ADD-05 owns native-backend authoring; ADD-07 propagation and ADD-09 published blueprint coverage are separate outcomes. No claim covers arbitrary combinations of add-on parts or candidate generators. | Docs | [RES] [EXT] [PLAT] [LAYOUT] |
| <a id="cap-add-05">ADD-05</a> | Develop an add-on around a shared Godot API and selectable native backends. | G [U-ADDONS] | I | Platform Paths implements the stated shared native API and operating-system backend selection pattern. This does not establish a generator, a universal backend interface or a selected general add-on declaration contract. | Docs, Source | [PATHS] [PATHS-BUILD] |
| <a id="cap-add-08">ADD-08</a> | Express separate runnable demo and integration-test projects for an add-on. | G [U-LAYOUT] | I | Current resource/project/test declarations can compose these separate contexts. This assesses composition support, not how many examples adopt the convention. TST-06 owns independent native unit execution; RES-10 owns production/test isolation. | Docs | [RES] [DEV] [LAYOUT] [TESTS] |
| <a id="cap-add-09">ADD-09</a> | Use published layout and ownership guidance as an add-on blueprint. | G [U-LAYOUT] | I | Public layout guidance describes separate demo/integration contexts, project-owned `main/` and `tests/` groups, reusable add-on ownership and implementation-owned native tests. The SQLite and Platform Paths examples provide concrete compositions. The example grouping does not prescribe a consumer workspace root. This assesses published guidance, not execution evidence or migration task counts. DX-05 owns naming. | Docs | [LAYOUT] [TESTS] |
| <a id="cap-add-10">ADD-10</a> | Publish/reuse an owned add-on outside its original workspace through declared dependencies. | O | I | Composition is external-consumer-capable; a new distributable add-on archive format is not implied. | Docs | [ROOT] [LAYOUT] |

###### Declarative Godot API generation

This candidate belongs to native add-on authoring. If pursued, it would generate Godot API/
registration and backend connections for shared processing. It is optional for authoring and
unnecessary for vendor-prebuilt consumption. GEN-03 below remains a reference to output
compilation/testing acceptance, not a separately partially implemented generator capability.

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-gen-01">GEN-01</a> | Declare a Godot-facing native API once and generate recurring engine type/registration glue. | C | N | Discussed owned-add-on API generator; existing upstream godot-cpp binding generation is a different capability. | Docs, Inventory, Research | [API] [EXT] [CAT] |
| <a id="cap-gen-02">GEN-02</a> | Generate connections between the shared Godot API and operating-system backend implementations. | C | N | No current add-on API/backend generator identified; handwritten backends remain usable. | Docs, Inventory | [API] [PATHS] |
| <a id="cap-gen-04">GEN-04</a> | Diagnose incompatible API/backend declarations before runtime. | C | N | Exact contracts and diagnostics belong in a dedicated generator specification. | Inventory | [API] |

### Shared workflows

These operations work on selected content and its context, whether it belongs to an
application, an add-on demo or an integration-test project. Add-on parts built
from source add preparation dependencies; prebuilt parts supply already produced artifacts.

#### Import and processing tools

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-imp-01">IMP-01</a> | Convert standard supported assets with the selected Godot editor and import settings. | O | I | Format support follows the actual engine; no promise of every upstream importer/tool. | Docs, Research | [RES] [CAT] |
| <a id="cap-imp-02">IMP-02</a> | Preserve connected/grouped resource conversions and their declared dependencies. | O | I | Related files can share a unit; automatic minimal group discovery is not promised. | Docs, Research | [RES] [CAT] |
| <a id="cap-imp-03">IMP-03</a> | Use project-provided import plugins with their resource dependencies. | O | I | Explicit plugin membership/purposes apply; arbitrary plugin IO remains a boundary. | Docs, Research | [RES] [CAT] |
| <a id="cap-imp-04">IMP-04</a> | Use importers and extension types registered by an extension the editor loads. | O | I | Requires appropriate extension editor libraries and declared closure. | Docs, Research | [EXT] [CAT] |
| <a id="cap-imp-05">IMP-05</a> | Use external importer tools and custom auxiliary outputs with sound dependency/output capture. | C | U | No assessed end-to-end external-tool/auxiliary-output workflow is established here. Import-plugin support (IMP-03) is only a generic prerequisite. Catalogue Q01/Q03/Q07 record constraints, not an implemented subset. | Research | [CAT] |
| <a id="cap-imp-06">IMP-06</a> | Control plugin and extension participation independently for processing, editor and execution. | O | I | Current phase policy exists; the future declaration format remains open. | Docs | [RES] [EXT] |

#### Interactive editor and authored metadata

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-edt-01">EDT-01</a> | Open the selected editor with built resources, plugins and required extension editor libraries. | G [U-EDITOR] | I | Editor tool identity and extension editor library availability are explicit dependencies. | Docs | [DEV] [EXT] |
| <a id="cap-edt-02">EDT-02</a> | Persist edits to existing authored scenes, scripts, assets and authored project settings for subsequent builds. | G [U-EDITOR] | I | Writes to linked authored files and authored project settings are supported. Generated or attribute-owned settings retain their declared owner; CRUD/new-file handling is assessed separately in EDT-03. | Docs | [DEV] |
| <a id="cap-edt-03">EDT-03</a> | Create, rename and delete resources in editor and incorporate them into subsequent builds. | G [U-EDITOR] | P | Fully linked directories support creation/rename/delete in the checkout. New files outside them can remain in the view and need explicit placement and BUILD declarations; not every resource path layout has the same editing behavior. Manual declaration updates are allowed by the goal. | Docs | [DEV] [LAYOUT] |
| <a id="cap-edt-04">EDT-04</a> | Distinguish editable owned inputs from generated or external read-only inputs. | O | I | Current editor view uses links versus copies. | Docs | [DEV] |
| <a id="cap-edt-05">EDT-05</a> | Generate, inspect and check missing UID/import sidecars beside their source files. | O | I | Missing-sidecar writeback exists; it does not overwrite stale authored sidecars. | Docs | [DEV] [RES] |
| <a id="cap-edt-06">EDT-06</a> | Preserve authored identities/import settings when resources move or are reused. | O | P | Authored sidecars are supported; moves still need explicit reference/import-path maintenance. | Docs, Research | [RES] [CAT] |

#### Execution

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-run-01">RUN-01</a> | Start the application's normal main scene from declared sources. | O | I | Desktop source execution uses the registered editor. | Docs | [DEV] |
| <a id="cap-run-02">RUN-02</a> | Start a selected scene or executable script without changing the application's normal entrypoint. | O | I | Explicit scene/script entrypoints and arguments are supported. | Docs | [DEV] |
| <a id="cap-run-03">RUN-03</a> | Start exported PCK content for smoke tests or local use. | O | I | Desktop runner and packaged application are distinct execution paths. | Docs | [DEV] [PLAT] |
| <a id="cap-run-04">RUN-04</a> | Choose windowed/headless execution and supply arguments, environment and runtime data. | O | I | Rendering and external-state requirements remain the caller's responsibility. | Docs, Research | [DEV] [CAT] |
| <a id="cap-run-05">RUN-05</a> | Run against an isolated writable environment without modifying authored sources. | O | I | The normal runner stages declared inputs; interactive editor writes are separate. | Docs, Research | [DEV] [CAT] |
| <a id="cap-run-06">RUN-06</a> | Install and launch mobile applications through a common user-facing workflow. | C | U | Applications exist; common install/launch scope and platform tooling integration need assessment. | Docs, Research | [PLAT] [CAT] |

#### Script checks

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-chk-01">CHK-01</a> | Check selected GDScripts with required classes, autoloads and extension types available. | G [U-CHECKS] | I | Every operation validates each unit it contains: its scripts and scenes load under the project with what its `deps` reach, and no project code runs. | Docs, Research | [DEV] [CAT] |
| <a id="cap-chk-02">CHK-02</a> | Check owned add-on scripts with deliberate warning/error policy while excluding unrelated vendor scripts. | O | I | The validation follows the project's warning settings; a test project includes the owned add-on's directory in Godot's `directory_rules`, which exempt the other add-ons. Configuration reuse and deliberate differences are RES-06. | Docs | [DEV] |
| <a id="cap-chk-03">CHK-03</a> | Select/shard checks and obtain per-script diagnostics and CI-readable results. | O | P | A build of an operation, or of its `_validation` output group, selects the units; each unit's validation is a cached action whose failure lists Godot's diagnostics per file. There is no JUnit report or sharding. | Docs | [DEV] |

#### Testing

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-tst-01">TST-01</a> | Run GdUnit suites with their production dependencies, helpers and fixtures. | G [U-TESTS] | I | Candidates and dependency availability are separate; the actual framework recognizes suites. | Docs, Research | [DEV] [CAT] |
| <a id="cap-tst-02">TST-02</a> | Filter/shard suites and forward framework options. | O | I | Filtering/sharding is suite-oriented; it is not cached execution per individual assertion. | Docs | [DEV] |
| <a id="cap-tst-03">TST-03</a> | Publish test failures, logs and JUnit/framework reports to CI. | O | I | Failure/report policy is part of the execution contract. | Docs | [DEV] |
| <a id="cap-tst-04">TST-04</a> | Write script-based smoke/integration tests without requiring GdUnit. | O | I | A test can start a script/scene and report failure through the runtime contract. | Docs | [DEV] |
| <a id="cap-tst-05">TST-05</a> | Test exported desktop application behavior with declared build artifacts. | O | I | Exported-PCK examples and declared executable-artifact testing exist; mobile runtime is a separate cell. | Docs | [EXAMPLES] [DEV] |
| <a id="cap-tst-06">TST-06</a> | Run independent native implementation unit tests without a Godot project. | G [U-LAYOUT] | I | Ordinary native test rules compose with the ruleset; project integration is not required. | Docs | [PATHS] [TESTS] |
| <a id="cap-tst-07">TST-07</a> | Run GdUnit inside the built Android/iOS application through a supported reusable workflow. | C | N | No current reusable mobile GdUnit execution workflow identified; packaged app tests are not equivalent. | Docs, Research | [DEV] [TESTS] [CAT] |
| <a id="cap-tst-08">TST-08</a> | Reuse deterministic test results only when their dependencies remain valid, and account for live native/external state. | G [P-CORRECT] [U-ITERATION] | P | Bazel policies distinguish deterministic and live-state execution; complete feature-specific validity contracts remain incomplete. FAST-04 owns avoiding unrelated reruns. | Docs, Research | [DEV] [TESTS] [CAT] |

#### Resource packs and DLC

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-pck-01">PCK-01</a> | Export the main application resources as a standalone PCK. | G [U-PACKS] | I | Pack content and applications are separate products. | Docs | [RES] |
| <a id="cap-pck-02">PCK-02</a> | Choose complete declared content or reachable content with explicit dynamic dependencies. | O | I | Opaque/dynamic dependencies have bounded support and explicit declaration requirements. | Docs, Research | [RES] [CAT] |
| <a id="cap-pck-03">PCK-03</a> | Build a DLC pack that refers to resources supplied by a prerequisite pack. | G [U-PACKS] | I | Required content identity/load-order declarations exist; delivery is separate. | Docs | [RES] |
| <a id="cap-pck-04">PCK-04</a> | Exclude optional DLC from the main pack while permitting deliberate optional loads. | G [U-PACKS] | I | Optional content and entrypoints are explicit. | Docs | [RES] |
| <a id="cap-pck-05">PCK-05</a> | Deliver additional packs for explicit runtime loading. | O | I | Desktop runner copies packs; application code controls mounting/activation. | Docs | [DEV] [RES] |
| <a id="cap-pck-06">PCK-06</a> | Diagnose missing/conflicting pack dependencies and shared resource identities. | O | I | Current identity checks have authored-sidecar/same-project constraints. | Docs, Research | [RES] [CAT] |
| <a id="cap-pck-07">PCK-07</a> | Change export variant, feature tags, script representation and export options. | O | I | Current exposed options do not cover every upstream preset capability. | Docs | [RES] [PLAT] |
| <a id="cap-pck-08">PCK-08</a> | Deliver the extension libraries of every included pack without duplicating consumer wiring. | G [U-PACKS] [P-CORRECT] | I | `godot_app` delivers the extension libraries, platform libraries and Info.plist fragments of the add-ons of its start pack and of its `loadable_packs`. The application does not contain the loadable PCKs; PCK-05 owns delivering them. | Docs, Source | [PLAT] [RES] |
| <a id="cap-pck-09">PCK-09</a> | Use the same public content/application roles under a selected target platform configuration. | G [U-PLATFORMS] | P | Per-operating-system declarations exist; equivalent public role declarations are still duplicated. | Docs, Research | [PLAT] [CAT] |

#### Application products

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-app-11">APP-11</a> | Produce a runnable application for a selected initial operating system with its resources, extension libraries and platform libraries. | G [U-PLATFORMS] | I | Documented baseline products cover Linux application trees, macOS bundles, Android APKs and iOS apps with their runtime/SDK prerequisites. APP-01–05 record format/target observations; arbitrary ABIs, AAB upload signing and other variants are not implied. | Docs | [PLAT] [ENG] |
| <a id="cap-app-01">APP-01</a> | Produce a runnable Linux application with resources and extension libraries. | O | I | Directory/archive product; see platform matrix for the target axis. | Docs | [PLAT] |
| <a id="cap-app-02">APP-02</a> | Produce a macOS application bundle and archive. | O | I | Unsigned assembly and optional signing are separate workflows. | Docs | [PLAT] |
| <a id="cap-app-03">APP-03</a> | Produce an Android APK with native and Java/resource/manifest dependencies. | O | I | SDK/NDK/Java and engine/provider constraints apply. | Docs | [PLAT] |
| <a id="cap-app-04">APP-04</a> | Produce an Android App Bundle. | O | I | Current AAB output is unsigned; release upload signing remains external. | Docs | [PLAT] |
| <a id="cap-app-05">APP-05</a> | Produce an iOS device or simulator application with native linkage. | O | I | SDK, the runtime of the platform slice, provisioning and rules_apple provider constraints apply. | Docs | [PLAT] [ENG] |
| <a id="cap-app-06">APP-06</a> | Configure application identity, versions, icons, splash, localization, privacy and permissions. | O | I | Per-operating-system applicable metadata; no implication that every setting exists on every operating system. | Docs | [PLAT] |
| <a id="cap-app-07">APP-07</a> | Select debug/release variants and compatible engine/extension CPUs. | O | I | Some selection is explicit; execution/target platform and device/simulator are different axes. | Docs | [PLAT] [EXT] |
| <a id="cap-app-08">APP-08</a> | Obtain matching engine, extension and application debug symbols. | O | I | Symbol content depends on supplied/compiled debug information and build flags. | Docs | [PLAT] [ENG] |
| <a id="cap-app-09">APP-09</a> | Sign applicable application products with deliberate locality and credential handling. | O | P | macOS signing, Android APK and delegated iOS signing exist; AAB upload signing is external. | Docs | [PLAT] |
| <a id="cap-app-10">APP-10</a> | Package app-only platform libraries and platform resources and transitive platform libraries. | O | I | rules_android and rules_apple own linking, resource and manifest/plist merging. | Docs | [PLAT] [EXT] |

### Cross-cutting quality

These quality goals span foundations and shared operations. Evaluate them against actual
affected work/results. Governing requirements come from the design principles and agreed scope;
this grouping does not introduce parallel add-on-specific pipelines.

#### Incremental feedback and caching

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-fast-01">FAST-01</a> | Repeat an unchanged build without rerunning compatible processing/native work. | G [U-ITERATION] [P-REUSE] | I | Bazel action caching exists; live execution results are not implied. | Docs, Research | [ARCH] [CAT] |
| <a id="cap-fast-02">FAST-02</a> | Change one native source/header and rebuild only required native objects and dependents. | G [U-ITERATION] [P-REUSE] | I | Native compile/header graph exists within supported engine/extension builds. | Docs | [ENG] [ARCH] |
| <a id="cap-fast-03">FAST-03</a> | Change an independent asset and preserve unrelated asset conversion/native compilation. | G [U-ITERATION] [P-REUSE] | I | Current import unit boundaries support this; independence must be declared soundly. | Docs, Research | [RES] [CAT] |
| <a id="cap-fast-04">FAST-04</a> | Keep valid check/test results after unrelated edits. | G [U-ITERATION] [P-REUSE] | P | Bazel result cache exists, but full-project dependencies can cause unnecessary invalidation. | Docs, Research | [DEV] [CAT] |
| <a id="cap-fast-05">FAST-05</a> | Share compatible imports automatically between operations with different selected resource closures. | G [U-ITERATION] [P-REUSE] | P | Some project consumers share imports; general reuse across operation selections is incomplete. FAST-08 owns correct invalidation and FAST-09 covers reuse across delivery/build contexts. | Research | [CAT] |
| <a id="cap-fast-06">FAST-06</a> | Avoid whole-project preparation for a small suite while retaining real context dependencies. | G [U-ITERATION] [P-REUSE] | P | Independent test compositions exist; preparation can still include broad initialization/runfiles. RES-07 owns resource-selection correctness, RES-06 configuration reuse. | Docs, Research | [DEV] [CAT] |
| <a id="cap-fast-07">FAST-07</a> | Change export-only options or signing policy without repeating unaffected imports/compilation. | G [U-ITERATION] [P-REUSE] | I | Phase/output separation exists; plugin effects and actual input equality remain conditions. | Docs, Research | [RES] [PLAT] [CAT] |
| <a id="cap-fast-08">FAST-08</a> | Invalidate affected work for importer, plugin, configuration, native-type and tool changes. | G [U-ITERATION] [P-REUSE] | P | Conservative invalidation exists; arbitrary plugin/auxiliary dependency contracts remain open. | Research | [CAT] |
| <a id="cap-fast-09">FAST-09</a> | Reuse compatible outputs between main/DLC packs, variants and local/CI builds. | G [U-ITERATION] [P-REUSE] | P | Action/native reuse exists, with broad project/export dependencies. FAST-05 owns shared import work; this row covers reuse across pack/variant/local-CI contexts. | Docs, Research | [RES] [ARCH] [CAT] |
| <a id="cap-fast-10">FAST-10</a> | Understand why a change causes work to rerun or remain reusable. | G [P-USABILITY] | P | Graph/action inspection exists; unified user-facing explanations are incomplete. DX-03 owns resource inclusion, not action invalidation explanations. | Docs, Research | [RES] [ARCH] [CAT] |

#### Reproducibility and usability

| ID | User outcome / use case | Basis / rationale | Coverage | Observed coverage / limits | Assessment basis | Coverage sources |
| --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-dx-01">DX-01</a> | Pin engines, add-ons and tools for reproducible local/CI setup. | O | I | Module/repository pins exist; source configure/SDK/signing still have explicit external boundaries. | Docs | [ROOT] [VERS] [ENG] |
| <a id="cap-dx-02">DX-02</a> | Use ordinary Bazel dependency, visibility, configuration and test workflows. | O | I | Platform tools and rules compose with core workflows; no second scheduler is required. | Docs, Inventory | [API] [ARCH] |
| <a id="cap-dx-03">DX-03</a> | Inspect resource ownership/references and why a file is included in a pack. | O | I | Graph/selection reports explain resource inclusion with bounded static-format coverage. FAST-10 owns why work reruns. | Docs, Research | [RES] [CAT] |
| <a id="cap-dx-04">DX-04</a> | Receive actionable errors for configuration, resource identity, dependency or platform mismatch. | O | I | Existing checks cover stated cases; unknown combinations are not silently treated as supported. | Docs | [RES] [PLAT] [EXT] |
| <a id="cap-dx-05">DX-05</a> | Find equivalent workflows through consistent explicit local names and low repeated wiring. | G [U-LAYOUT] [P-USABILITY] | P | The example layout guide defines consistent explicit role names across both add-ons and Lichtpost, retaining meaningful platform/signing/symbol qualifiers. Current test adapters still repeat configuration/resource wiring; consistent local names do not establish shared configuration declarations. Scope of name omission is recorded in the boundary table. | Docs, Inventory, Research | [LAYOUT] [CAT] [API] |

## Capability relationships and workflow composition

Use the leading entry for each outcome and related entries only for their distinct scope.
Quality constraints can apply to several workflows without defining those workflows again.

| Concern | Leading entry | Related scope |
|---|---|---|
| Generic add-on authoring | [ADD-11](#cap-add-11) | ADD-05 owns native backends; ADD-07 dependency propagation; ADD-10 cross-workspace reuse |
| Runnable application | [APP-11](#cap-app-11) | APP-01–05 record target/format observations; APP-06–10 cover metadata, variants, symbols, signing and app-only platform libraries |
| Layout and ownership blueprint | [ADD-09](#cap-add-09) | DX-05 owns naming vocabulary; ADD-08 separate demo/integration contexts; TST-06 independent native testing; RES-10 production/test isolation |
| Configuration reuse and intentional differences | [RES-06](#cap-res-06) | RES-07 owns required resource selection; FAST-06 owns preparation cost for small feedback scopes |
| Compatible import work reused across operations | [FAST-05](#cap-fast-05) | FAST-08 owns sound invalidation; FAST-09 covers reuse across pack/variant/local-CI contexts |
| Deterministic versus live-state result validity | [TST-08](#cap-tst-08) | FAST-04 owns avoiding unrelated check/test reruns |
| Resource ownership and inclusion explanations | [DX-03](#cap-dx-03) | RES-09 diagnoses resource identity/dependency conflicts; FAST-10 explains work rerunning/reuse |
| Additional-pack extension library delivery | [PCK-08](#cap-pck-08) | ADD-07 covers general add-on propagation |
| Candidate API/backend generation | [GEN-01](#cap-gen-01), [GEN-02](#cap-gen-02) | GEN-04 owns declaration diagnostics; generic generated-input consumption is RES-02 |

### Reference IDs

These IDs remain valid for prior references. They point to owning outcomes or acceptance
criteria rather than carrying an independent implementation status.

| Reference ID | Owner / successor | Meaning |
|---|---|---|
| <a id="cap-imp-07">IMP-07</a> | [FAST-05](#cap-fast-05), with FAST-08 validity constraints | Import reuse under compatible real inputs; no second reuse status |
| <a id="cap-fast-11">FAST-11</a> | [TST-08](#cap-tst-08) | Sound cached results under live/native/external state; no second validity status |
| <a id="cap-gen-03">GEN-03</a> | [GEN-01](#cap-gen-01) / [GEN-02](#cap-gen-02) acceptance | Generated API/backend glue must compile and be tested if generation is pursued. Existing generic source consumption does not establish partial implementation of that generator workflow. |

### Workflow composition

| Workflow / reference case | Own focus | Related capabilities |
|---|---|---|
| Consume a script/resource add-on | Acquire and compose content with the needed configuration/dependencies | ADD-01/02; RES and applicable shared operations |
| Consume the Sentry reference case | Select compatible prebuilt vendor libraries for the chosen features/operating-system cells | ADD-04; EXT-03 and applicable Android/native integration |
| Develop a script/resource add-on | Define reusable content and any script-facing API, with appropriate demo/tests | ADD-11 leads authoring; ADD-08/09 demonstration/guidance; RES and applicable shared workflows |
| Develop a native add-on | Define its Godot-facing API and any needed operating-system implementations | ADD-11 leads authoring; ADD-05/06 native subcases; EXT and shared build/editor/test/delivery workflows |
| Explore API/backend generation | Generate recurring registration/connection code | GEN-01/02/04; output acceptance is referenced by GEN-03 |

The kind of an add-on part and its acquisition are independent. For example, Android plugin integration can
involve owned source or a prebuilt AAR with manifest/dependency contributions [PLAT]; the
Platform Paths source pattern is not the only possible form. A GDExtension and an Android
plugin are not mutually exclusive, and an Android plugin need not accompany a GDExtension.
The scope/contract for each selected composition still needs an explicit specification.

These relationships organize user needs, not a required rule hierarchy or linear build
schedule. Actual plugin, resource, tool and native dependencies remain relevant to sound
build/execution behavior.

## Operating-system facets

These tables describe observed coverage for selected rows, not a required future support
matrix. Cells use the same implementation vocabulary; they do not imply product commitments
for the listed combinations. Conditional I cells retain documented SDK/engine/artifact
constraints; no row claims every CPU is covered.

### Engine/tool execution platform

| Workflow / capability IDs | Linux execution | macOS execution | Android execution | iOS execution | Boundary |
|---|---|---|---|---|---|
| Interactive editor and authored writeback: EDT-01/02 | I | I | open / U | open / U | Current ruleset editor workflow runs on a desktop host [DEV] |
| Source script/scene run: RUN-01/02/04 | I | I | open / U | open / U | Mobile target selection is not source execution on that device [DEV] |
| GDScript checking: CHK-01/02/03 | I | I | open / U | open / U | Correct extension editor libraries and real context dependencies required [DEV] [EXT] |
| GdUnit source suites: TST-01/02/03 | I | I | open / U | open / U | Suite filtering/cache granularity and rendering requirements still apply [DEV] |
| Engine configure/native builds: ENG-03/04/05 | I | I | open / U | open / U | Target SDK must be available on configuring host; Apple target setup requires appropriate Apple tooling [ENG] |
| GdUnit inside packaged mobile app: TST-07 | — | — | N | N | Candidate reusable device-side test workflow; desktop suite support does not fill these cells [DEV] [TESTS] |

Android/iOS columns above describe where the engine/tool executes, not the application
target. `open / U` leaves future execution-platform scope open and records that the
corresponding workflow was not assessed here; it does not claim an engine-level impossibility.
The desktop cells describe current coverage, not a mandatory list of future execution
platforms.

### Operating system of the application

| Product / capability IDs | Linux | macOS | Android | iOS | Conditions / gap |
|---|---|---|---|---|---|
| Resource PCK export: PCK-01/07 | I | I | I | I | Explicit exporter selection today; compatible execution platform/editor; configured platform role is PCK-09 [RES] |
| Runnable application: APP-11; APP-01–05 observations | I: tree/archive | I: app/archive | I: APK/AAB | I: device/simulator app | Required runtime, ABI and platform tools/providers [PLAT] |
| Extension library delivery/linking: EXT-03–05 | I | I | I | I | Physical shared libs versus Android ABI delivery versus iOS static/framework integration [EXT] |
| Target runtime from prebuilt artifacts: ENG-02 | I | I | I | I | Available platform slices follow the selected archive, not all possible CPU or simulator variants [PLAT] [ENG] |
| Target runtime from supported source build: ENG-04 | I | I | I | I | Supported configure/build scope and SDK constraints apply [ENG] |
| Native symbol products: APP-08 | I | I | I | I | Only debug data supplied/compiled can be retained; appropriate tools/flags [PLAT] [ENG] |
| Application signing: APP-09 | open / U | I | P | I | APK signing exists; AAB upload signing is external. Apple signing needs appropriate identity/provisioning [PLAT] |
| Android plugin/lifecycle integration: ADD-06 | — | — | I | — | Registration/context plumbing exists; a feature's actual hooks/order need its own acceptance [PATHS] |
| Complete Sentry consumer case: ADD-04 | U | U | U | U | Exact pinned vendor version/features and accepted operating-system cells still need assessment [EXT] [CAT] |
| Common managed install/launch: RUN-06 | — | — | U | U | Candidate workflow; Android/Apple SDK install and launch tools are not a claimed common ruleset API [PLAT] |
| Additional-pack extension library aggregation: PCK-08 | I | I | I | I | `loadable_packs` delivers the native code of further packs' add-ons; their PCKs are delivered separately (PCK-05) [PLAT] |

Additional execution platforms, operating systems of applications and language/runtime
families are separate scope questions. Windows execution platforms, Windows and Web
applications and managed .NET/C# remain open in the scope table; upstream availability
alone establishes neither ruleset support nor a goal.

### Engine, content and validity qualifiers

| Facet | Current coverage | Capability references / boundary |
|---|---|---|
| Prebuilt editor; prebuilt runtime; source-built editor; source-built runtime | I for the separately documented workflows | ENG-01–06; execution/target platform ABI and actual capabilities remain explicit |
| Source patches/modules/generators/native object reuse | I within supported source-build translator scope | ENG-05, FAST-02; arbitrary build-system commands/SDK provisioning are not fully covered [ENG] |
| Same sources under different effective configurations | I for separate configurations; configuration-reuse/override ergonomics and cross-operation import sharing P | RES-06–08, FAST-05 |
| Generated versus authored inputs | I for generic input consumption/editor boundaries; candidate API generation is not thereby implemented | RES-02, EDT-02–06; GEN-01/02 acceptance |
| Ordinary unit conversion versus grouped/custom import | I for declared supported units; U for a general external-tool/auxiliary-output workflow | IMP-02/05, FAST-08 |
| Main pack, prerequisite pack, optional DLC | I for content selection/loading declarations; P for complete extension library aggregation | PCK-01–08 |
| Debug/release, strip and symbols | I within selected engine/native support | APP-07/08; symbols are not invented for an artifact lacking debug data |
| Source run versus exported-content run versus application | Separately supported; not equivalent evidence | RUN-01/03, APP-01–05, TST-05/07 |
| Deterministic result versus live-state execution | P for a complete sound feature-by-feature validity contract | TST-08 owns validity; FAST-04 owns unrelated-rerun avoidance |
| Individual suite versus individual test-case result reuse | Suite/target filtering and caching I; per-case cache scope undecided | TST-02, FAST-04; not an additional implicit test scheduler |

## Open scope and design questions

| Question | Related IDs | What remains undecided |
|---|---|---|
| Add-on composition abstraction | ADD-01–11 | Which declarations or contracts best express selected consumption/authoring needs; one shared contract or an add-on rule is not assumed |
| Configuration reuse and deliberate differences | RES-06/07 | Reduce repeated configuration and drift while supporting intentional test/operation overrides; declaration granularity and composition mechanism remain open |
| Automatic import sharing | FAST-05/06/08; IMP-07 reference | Effective-context compatibility, including relevant overrides, and actual input/output contracts; no public import coordination target is assumed |
| Test/result granularity | TST-02/08, FAST-04; FAST-11 reference | Appropriate selected feedback scope and result reuse; no case scheduler or old target granularity is prescribed |
| Declarative Godot API/backend glue | GEN-01/02/04; GEN-03 acceptance | Candidate product scope, declaration/type coverage and backend contract; no chosen language/generator architecture |
| Mobile installation/runtime automation | RUN-06, TST-07 | Candidate scope, device/simulator/emulator expectations and existing platform tool integration |
| Vendor acceptance | ADD-04 | Pin Sentry and choose features/operating-system combinations; generic extension and platform library integrations are not complete vendor acceptance |
| Additional execution platforms, operating systems of applications and language families | Scope table / operating-system facets | Windows or mobile execution platforms, extra operating systems of applications and .NET/C# are separate undecided dimensions |
| Performance acceptance | FAST-01–10; TST-08 validity | Select representative edits/contexts and record necessary invalidation and unaffected reuse; timing budgets require a measured baseline |

These are product-scope questions and capability gaps, not implementation tasks or a
delivery order. Individual specifications choose their own scope and acceptance.

## Sources

Goal rationale is recorded in the goal-basis register, separately from coverage evidence.
The following sources support observed behavior and its limits. The pinned pipeline catalogue
records direct/conditional dependencies and bounded experiments; it is not an API decision.
Docs, inventories, catalogue findings and directly inspected source are distinguished per row.
Run/device evidence requires an actual matching receipt, not inference from a source link.

| Source | Role |
|---|---|
| [ROOT] [API] | Current module setup and public surface; absence of a dedicated workflow is checked against this inventory |
| [RES] [DEV] | Resource/configuration/import/pack and source/check/test/editor behavior |
| [PLAT] [ENG] [EXT] [VERS] | Applications, engine origin/build/version, extension and platform conditions |
| [EXAMPLES] [PATHS] [LAYOUT] [TESTS] | Existing examples, Android/native backend pattern and ownership conventions |
| [ARCH] [CAT] | Cache/dependency boundaries and bounded source/experiment research |
| [ADAPTER] | Direct source for current test adapter composition restrictions; relevant to RES-06 |
| [PATHS-BUILD] | Direct source for shared native API composition and operating-system backend selection in ADD-05 |
| [PRINCIPLES] | Governing principles used by P-* goal records, not implementation evidence |

## How to use and maintain this register

1. Identify the user need independently of current support. Distinguish an observed workflow,
   a desired outcome and an open candidate before selecting platform/configuration cells.
2. A spec cites relevant IDs and explicitly chooses scenarios, coverage, exclusions and
   observable acceptance. Include compatibility or preservation requirements only when they
   are justified by its scope. One ID may span several specs; no spec inherits every row.
3. Compare alternatives, including replacing, combining, restricting or omitting observed
   workflows. Evaluate user benefit, dependency correctness, feedback speed and declaration
   effort. Current feature coverage is evidence for this comparison, not a veto over a
   better model. Explain effects on explicitly selected goals and governing principles.
4. Assess coverage against the outcome and record the evidence type. A generic building
   block is not partial delivery of an unimplemented end-to-end workflow. Before claiming
   improved reuse or validity, compare relevant edits that must invalidate with unrelated
   edits that must preserve work/results. These are acceptance methods, not extra capabilities.
   Record configuration/execution scope; code, CI, simulator and device/signing receipts
   establish different claims.
5. Keep unknown cells unknown until assessed; explain every P/N boundary. Split a row when a
   meaningful subcase has a different state rather than marking a whole family complete.
6. Refresh the snapshot after a material support/scope change, against a named commit, keeping
   stable references. A rename preserves the ID; retire, combine or split IDs explicitly so
   prior references remain traceable. Related entries should cite their leading outcome
   rather than maintain duplicate statuses. Stable IDs do not freeze workflows or boundaries.

The matrix owns recorded coverage and planning classifications; it is not the authority for
mandatory product scope. The overview summarizes families and links here instead of keeping
a second status list. Specs own selected requirements/design/tasks; support guides describe
current supported use. The API documentation remains sourced from actual Starlark
definitions, not this capability register.

[ROOT]: ../../../README.md
[API]: ../public/api/modules.bzl
[RES]: ../public/resources.md
[DEV]: ../public/development.md
[PLAT]: ../public/platforms.md
[ENG]: ../public/engine.md
[EXT]: ../public/gdextension.md
[VERS]: ../public/versions.md
[EXAMPLES]: ../../examples/README.md
[PATHS]: ../../examples/addons/platform_paths/README.md
[LAYOUT]: ../public/project-layout.md
[TESTS]: ../../tests/AGENTS.md
[ARCH]: architecture.md
[CAT]: godot-pipeline/README.md

[ADAPTER]: ../../godot/private/adapter.bzl
[PRINCIPLES]: principles.md
[PRINCIPLE-I]: principles.md#i-avoid-unnecessary-work
[PRINCIPLE-II]: principles.md#ii-model-build-and-execution-dependencies-accurately
[PRINCIPLE-III]: principles.md#iii-faithful-godot-concepts-with-little-ceremony
[PRINCIPLE-IV]: principles.md#iv-research-deeply-build-on-bazel
[U-ENGINES]: #goal-engines
[U-EDITOR]: #goal-editor
[U-CHECKS]: #goal-checks
[U-TESTS]: #goal-tests
[U-PACKS]: #goal-packs
[U-ADDONS]: #goal-addons
[U-SENTRY]: #goal-sentry
[U-CONFIG]: #goal-config
[U-SELECTION]: #goal-selection
[U-PLATFORMS]: #goal-platforms
[U-LAYOUT]: #goal-layout
[U-ITERATION]: #goal-iteration
[P-REUSE]: #goal-reuse
[P-CORRECT]: #goal-correctness
[P-USABILITY]: #goal-usability

[PATHS-BUILD]: ../../examples/addons/platform_paths/BUILD.bazel

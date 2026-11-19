# Capability Overview

rules_godot aims to give developers fast, trustworthy feedback while working on Godot
applications and reusable add-ons with Bazel.

This overview groups user needs and related use cases for design discussion. The
[capability matrix](capabilities.md) owns goal rationale, observed coverage, open scope and
evidence. Its [authority guidance](capabilities.md#authority-and-design-freedom) explains why
existing workflows do not automatically become preservation requirements.

## Foundations

1. **Suitable engines.** Obtain or build editor and runtime engines appropriate for the
   project and selected target, with compatible native APIs and features.
   [Engine goals](capabilities.md#goal-engines) and [engine scenarios](capabilities.md#engine-selection-and-builds).

2. **Reusable content and consistent configuration.** Reuse content and configuration without
   unnecessary duplication or unintended drift. Allow deliberate operation-specific settings,
   including test overrides, and select the resources each operation needs. No single shared
   project declaration, file or configuration object is required.
   [Configuration goal](capabilities.md#goal-config),
   [selection goal](capabilities.md#goal-selection) and [resource scenarios](capabilities.md#resources-and-project-context).

3. **Add-on consumption and authoring.** Acquire or create reusable script/resource/native
   content with the dependencies and activation needed for its use. The kind of an add-on's
   parts and their acquisition are independent: an add-on may contain an extension, an Android
   plugin, both or neither, built from source or prebuilt. Native cases include C++
   GDExtensions via godot-cpp, operating-system backends and Android lifecycle integration.
   [Add-on goal](capabilities.md#goal-addons), [generic authoring](capabilities.md#cap-add-11) and [related scenarios](capabilities.md#add-on-consumption-and-development).

   | Workflow | Own focus | Shared needs |
   |---|---|---|
   | Consume | Select compatible contents and make their dependencies available | Content/configuration composition and the relevant processing, editor, feedback and delivery workflows |
   | Develop | Define reusable contents and any Godot-facing API; for native add-ons, implement the needed backends; provide focused demo/tests | The same shared workflows, plus native building where needed |

   Consumption and authoring need compatible expectations. Whether one contract, several
   declarations or a dedicated add-on rule best expresses them remains open. GDExtensions
   and Android plugins are not mutually exclusive; neither is mandatory for every add-on.
   Exploring declarative API/backend glue generation is an optional native-authoring case,
   not a prerequisite for authoring or consuming add-ons.

## Shared workflows

4. **Usable processed content.** Make selected content usable with its actual processing,
   plugin, tool and native dependencies. Choose which custom processing cases belong in scope
   before defining their support contract.
   [Processing scenarios](capabilities.md#import-and-processing-tools).

5. **Editor changes and controlled execution.** Work live in Godot, editing or reorganizing
   owned resources, and use the changes in later builds; run selected content with the intended
   inputs and environment. The matrix
   records current editing and execution mechanisms separately from these needs. BUILD
   declaration updates for new resources may remain manual.
   [Editor goal](capabilities.md#goal-editor),
   [editor scenarios](capabilities.md#interactive-editor-and-authored-metadata) and
   [execution scenarios](capabilities.md#execution).

6. **Trustworthy check/test feedback.** Get GDScript and GdUnit feedback with the relevant
   configuration, dependencies and selected scope. Other observed test styles, selection
   controls and report formats are recorded in the matrix for separate scope decisions.
   [Check goal](capabilities.md#goal-checks), [GdUnit goal](capabilities.md#goal-tests) and
   [test scenarios](capabilities.md#testing).

7. **Content and application delivery.** Produce main/DLC content and application artifacts
   for the selected export platform with the extension and platform libraries they need. Retarget
   equivalent workflows without repeating their definitions. Product formats, signing and
   additional target platform combinations have their own scope decisions. Initial
   operating systems of applications are Linux, macOS, Android and iOS.
   [Pack goal](capabilities.md#goal-packs), [platform goal](capabilities.md#goal-platforms),
   [pack scenarios](capabilities.md#resource-packs-and-dlc) and
   [runnable application outcome](capabilities.md#cap-app-11) with its
   [target/format observations](capabilities.md#application-products).

## Cross-cutting quality

8. **Incremental feedback.** After native, resource or configuration changes, repeat necessary
   work and reuse unaffected artifacts and valid results. Correctness includes relevant
   external state and intentional configuration differences. Result granularity, action
   ownership and sharing mechanisms remain design choices.
   [Iteration goal](capabilities.md#goal-iteration) and
   [incremental scenarios](capabilities.md#incremental-feedback-and-caching).

9. **Understandable development workflows.** Keep declarations and feedback useful enough to
   predict and explain the effect of a change with little repeated wiring. Existing graph,
   reporting and setup tools are possible means, not required future public concepts.
   [Usability principle](capabilities.md#goal-usability),
   [work explanations](capabilities.md#cap-fast-10) and [workflow naming](capabilities.md#cap-dx-05).

## Reference compositions

| Case | What it illustrates | Scope to choose |
|---|---|---|
| Sentry | Consumption of vendor-prebuilt extension and platform libraries, including applicable Android integration | Vendor version, features and operating-system cells for the reference scenario |
| Platform Paths | A source-built native add-on combining a Godot-facing API with operating-system backends, including Android integration | Which aspects form a reusable authoring pattern |
| Script/resource add-on | Reusable content and optional tool integration without a mandatory native API | Its contents, activation, demo and test needs |

These cases illustrate relationships. Their coverage and assessment belong to the matrix;
they do not define a second status list or a required add-on taxonomy.

## Using these references

Start with a user need, its [goal basis](capabilities.md#goal-basis) and relevant scenarios.
Use [leading outcomes and reference IDs](capabilities.md#capability-relationships-and-workflow-composition)
to avoid treating related quality constraints as duplicate capabilities. A specification
chooses its scenarios, exclusions and acceptance; it does not inherit every existing option.

Execution platform, operating system of the application, ABI and actual device execution
are distinct dimensions.
Consult the [scope decisions](capabilities.md#scope-decisions-and-open-boundaries) before
interpreting an unknown or unsupported combination as either a goal or an exclusion.
The [pipeline catalogue](godot-pipeline/README.md) supplies domain/dependency evidence without
selecting a replacement API.

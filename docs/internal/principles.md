# Design principles

These principles govern product and architectural decisions in rules_godot: designs,
implementation and reviews. Operational repository instructions stay in their owning files;
they do not substitute for these principles. Surface conflicts with those instructions or
with explicit maintainer decisions before implementing.

## Principles

### I. Avoid Unnecessary Work

rules_godot MUST optimize for a short feedback loop when developing and iterating on Godot
applications. Avoiding unnecessary work is the shared objective of incremental builds and
selective test execution: a build produces application artifacts, while a test produces a
result or report whose validity also depends on its inputs.

The design MUST allow unaffected work and valid results to be reused. A local change MUST
NOT force unrelated imports, compilation, packaging, or test execution without a documented
dependency or a justified limitation of the model. Necessary work MUST remain small enough
in scope to benefit from Bazel's incremental execution and caching.

Optimization MUST consider the whole edit-to-feedback path, including preparation, building,
and execution. Faster builds alone are insufficient when every edit still forces unrelated
tests to run. Performance improvements MUST preserve the correctness of artifacts and test
results.

### II. Model Build and Execution Dependencies Accurately

The dependency model MUST distinguish inputs that can affect a build output from inputs
that can affect the behavior or result of an execution. These sets may overlap, but MUST NOT
be assumed identical. Rebuilding a package does not by itself establish that every test is
affected; an unchanged application artifact does not by itself establish that a previous
test result is still valid.

For each build action or execution, the model MUST account for the relevant resources, code,
tools, configuration, and execution conditions. Dynamic resource use and indirect
dependencies MUST have a sound representation or an explicit limitation. Unknown dependencies
MUST NOT be treated as absent merely to avoid work. When independence cannot be established,
invalidation MUST be conservative until the dependency model can be refined.

Dependency boundaries MUST make it possible to reason about which changes can affect which
outputs and executions. This applies to unit tests, visual regression tests, and end-to-end
tests covering larger game flows. These are architectural requirements for evolving the
ruleset, not claims that all these test capabilities already exist. Precise modeling is what
allows work to be skipped safely rather than merely skipped optimistically.

### III. Faithful Godot Concepts with Little Ceremony

The public model MUST reflect the Godot concepts relevant to a workflow and the phases in
which they participate. Import plugins, export plugins, editor plugins, and native extensions
MUST be distinguished by what they do and what they depend on. Their dependencies and effects
MUST enter the appropriate build or execution phases rather than being flattened into an
undifferentiated project dependency.

Rules and macros MUST express these distinctions with declarations that users can understand
and maintain. The model MUST avoid redundant declarations and incidental wiring where that
information can be derived reliably. Simplification MUST NOT conceal dependencies needed for
correct invalidation.

API design MUST be assessed through concrete consuming workflows: can a user express the
intended relationship, understand why it exists, and predict what a change affects?
Existing rule boundaries and implementation details are revisable. They MUST NOT be retained
solely because they are already present when they obstruct a clearer domain model or a faster
feedback loop.

### IV. Research Deeply; Build on Bazel

Designing a feature MUST include in-depth research into the Bazel and Godot concepts and
context relevant to the proposed behavior. Before settling on a design, contributors MUST
understand the applicable lifecycles, extension points, dependency semantics, and constraints
in both systems, including how they interact. Familiar terminology or the current ruleset's
implementation alone is not sufficient evidence of that understanding.

Research MUST begin when the requirements are stated. At that stage, establish the domain
concepts, intended workflows, relevant capabilities, and constraints needed to state and
clarify them. Distinguish factual questions to research from product decisions to ask the
maintainer. Record sources, assumptions, and technical questions deferred to the design.
The design MUST deepen that knowledge into the mechanisms and dependency model needed for
the implementation. Early research need not reach design depth or prematurely choose an
implementation.

Research MUST use authoritative sources, such as upstream documentation and source code,
for the relevant versions. Where documentation leaves consequential behavior unclear,
contributors MUST inspect the implementation or use focused experiments to resolve it.
The feature's design rationale MUST identify the supporting sources, explain the consequences
for the proposed model, and distinguish established behavior from assumptions and open
questions. Research depth MUST be sufficient to resolve questions that could change the
design; decision-critical uncertainty MUST NOT silently become an implementation assumption.

rules_godot MUST use Bazel's dependency graph, action model, caching, and test execution
semantics as the foundation of the Godot development cycle. Designs MUST expose useful work
and dependency boundaries to Bazel rather than hide them behind opaque orchestration or
maintain a competing mechanism that defeats Bazel's reuse.

When Bazel and Godot impose conflicting models, Bazel's semantics MUST take precedence in
how the build graph and build setup are represented. This foundation enables the dependency
precision, reuse, and fast feedback required by the other principles. Deep knowledge of
Godot MUST inform the mapping and its limitations without displacing that foundation.

Compatibility with every Godot feature is not an overriding requirement. A feature MAY be
restricted or left unsupported when its behavior prevents sound dependency modeling or
efficient use of Bazel. Such a decision MUST identify the affected user workflow, explain
the conflict, compare viable alternatives, and state the resulting limitation explicitly.

The tradeoff MUST be deliberate and reviewed against the product goal. Neither full Godot
compatibility at any cost nor rejecting a useful feature merely for implementation convenience
satisfies this principle.

### V. Examples Demonstrate; Test Projects Isolate

Example projects MUST teach users how to use the ruleset, showcase useful workflows, and
provide a place to assess whether rules and macros are practical and understandable. Each
example MUST remain focused on the experience it illustrates.

Examples MUST define tests for their own behavior, and those tests MUST run as part of
validation. Examples MUST NOT accumulate unrelated cases, variants, or complexity to meet
ruleset coverage goals. Their value as demonstrations and API design feedback takes priority
over their usefulness as regression fixtures.

Ruleset tests MUST live outside the examples and have a small scope centered on a particular
behavior or case. Their placement MUST follow the test conventions of established Bazel
rulesets, as the repository's verification architecture states them. End-to-end regression
coverage MUST use these focused tests where additional cases would distort an example.
Testing an example and using an example as a coverage matrix are different responsibilities.

## Product Goal and Design Tradeoffs

The product goal is fast, trustworthy feedback throughout Godot application development:
accurately model dependencies, perform only the work a change requires, and make the necessary
work efficient. Build artifacts and test results are both reusable products of that model,
with different validity conditions where their dependencies differ.

These principles express the intended product direction. The current repository is evidence
about implementation and usability, not the source of authority for these principles.
A gap between implementation and a principle MUST be made explicit when relevant to proposed
work; it MUST NOT be turned into a weaker principle to describe the status quo.

Design decisions MUST balance dependency precision, feedback speed, Godot compatibility,
and the effort required from users. A proposal that sacrifices one of these MUST identify
the benefit, the affected workflows, and why the simpler or more precise alternatives do
not meet the need. A bounded change need not implement every future capability, but MUST
preserve a credible path toward the relevant principles.

## Design checks

A design states the user workflow and the feedback or dependency problem it addresses, and
answers these checks, with a reason when a check does not apply. Before research, identify
known conflicts and missing evidence; pending research stays explicit and is neither a passed
check nor a violation. Resolve decision-critical questions before implementing.

1. **Work avoided:** Which imports, builds, or executions can be reused after a representative
   change, and which must run? Include unchanged-input behavior where relevant.
2. **Dependency correctness:** Which inputs affect build outputs, which affect execution
   results, and how are dynamic or uncertain dependencies handled without stale results?
3. **Domain and usability:** Which Godot concepts and phases are modeled, and what must the
   consuming user declare? Identify redundant ceremony and hidden relationships.
4. **Research, Bazel fit, and compatibility:** Which relevant Bazel and Godot concepts were
   investigated, what sources establish their behavior, and which questions remain open?
   Explain how those findings shape the design, how Bazel sees and reuses the work, and how
   its semantics govern the build graph and setup. State any Godot support limitation,
   alternatives considered, and the reason for the tradeoff.
5. **Examples and regression scope:** Does the example remain a focused demonstration with
   its own tests? Do additional regression cases belong in focused ruleset tests outside the
   examples, placed by the verification architecture?

Implementation reviews MUST compare the resulting behavior with these answers. Changes to
dependency modeling or invalidation MUST validate both sides: a relevant change triggers
necessary work, and an unrelated change preserves reusable work. Tests that assert an
action's declared inputs, together with tests of output determinism, satisfy this validation.
Performance claims MUST be supported by observations appropriate to the claim, such as
executed actions, reused results, selected tests, or timings for representative edits; these
observations are review evidence for the change, not permanent tests.

Where these principles conflict with the test conventions of established Bazel rulesets,
amend the principles to follow them.

## Amendments

Amend this document explicitly, in a reviewed change that explains the product reason, the
affected principles and the consequences for existing work. Existing code or a difficult
implementation does not silently redefine a principle. A violation of a MUST requirement
blocks the conflicting work until the design or implementation is corrected; a tradeoff a
principle permits documents its rationale.

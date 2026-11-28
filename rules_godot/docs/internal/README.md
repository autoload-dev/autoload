# Ruleset internal reference

These are long-lived resources for contributors and agents about the ruleset alone. They
describe user outcomes, architecture and source-backed domain mechanisms independently of any
single change. The [repository's internal reference](../../../docs/internal/README.md) owns
what covers the whole repository, such as verification, conventions and releasing. The
[internal guidance](../../../docs/internal/AGENTS.md) applies to these pages too.

| Resource | Purpose | Review when |
|---|---|---|
| [Design principles](principles.md) | Product goal, the principles that govern designs and reviews, and the design checks | Product direction or a principle changes |
| [Capability matrix](capabilities.md) | The outcomes the ruleset supports, with stable IDs, limits and the guides that own them | Support changes |
| [Architecture](architecture.md) | Ruleset layers and reuse boundaries, build tools and the progress messages of actions | Implementation architecture changes |
| [Godot pipeline catalogue](godot-pipeline/README.md) | Inputs, outputs, operations, dependencies and their source evidence | Engine/plugin/toolchain semantics change |
| [Android shell](android-shell.md) | How the Android shell follows Godot's Gradle export, its remaining differences and the review of a new Godot version | Changing the Android shell or pinning a Godot source |
| [Export option inventory](export-option-inventory.md) | Reviewed disposition of every built-in exporter option and how to compare a new Godot version | Adding a Godot minor or changing owned/rejected export options |
| [Export-plugin hook inventory](export-plugin-hook-inventory.md) | Reviewed disposition and Bazel declaration that replaces every `EditorExportPlugin` hook | Adding a Godot minor or porting an add-on's export plugin |
| [Maintainer tools](maintainer-tools.md) | The resource-graph query and where Godot BUILD declarations come from | Those tools change |
| [API documentation maintenance](api-reference.md) | Public entrypoints, output interfaces and registry metadata | Public surface or documentation tooling changes |

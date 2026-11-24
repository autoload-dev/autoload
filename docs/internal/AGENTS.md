# Internal reference

This area, and the ruleset's own in [rules_godot/docs/internal/](../../rules_godot/docs/internal/README.md),
hold durable architecture, domain research and maintenance procedures. A page that covers the
whole repository lives here; a page about the ruleset alone lives with the ruleset. Use the
[reference index](README.md) when locating an owning page; the scope, tasks and progress of a
change belong in its pull request, and routine run evidence in review/completion reports.

Keep references independent of individual changes. Update them when the underlying
outcomes, engine/toolchain semantics or supported mechanisms change, not after every run.
For research, state version/source scope, established findings, inference and open limits.
Preserve necessary experiment recipes and conclusions; temporary log paths are optional
provenance, never the only evidence. Preserve snapshot dates rather than implying a new audit.

When support changes, update the capability matrix as
[maintaining capability references](../../rules_godot/docs/internal/capabilities.md#maintaining-capability-references)
describes.

Link to owning code and public support guides where useful. Ruleset fixture commands and
setup instructions belong in the relevant [verification recipe](verification-recipes.md);
required timing and completion evidence belong in the [verification policy](verification.md).

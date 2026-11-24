# Documentation

`rules_godot/docs/public/` serves ruleset consumers; `internal/` and
`rules_godot/docs/internal/` serve contributors and agents. Root and example READMEs are
public-facing. This file provides navigation and shared authoring guidance.

Read [public guidance](../rules_godot/docs/public/AGENTS.md) for consumer pages and every user-facing README;
read [internal guidance](internal/AGENTS.md) for architecture, research and maintainer material,
both the repository's in `internal/` and the ruleset's in `rules_godot/docs/internal/`.

Give each fact one owning page and link to the relevant section. Keep commands copyable;
use explicit placeholders such as `//path/to:target` when a user must supply a label.
When moving documentation, update links, generator inputs and owning instructions together.
Preserve a concrete setup and usage path for each supported operating system and feature.

For ordinary prose changes, `aspect pre-push` runs the documentation conventions. API source changes
use the [API documentation recipe](internal/verification-recipes.md#api-documentation)
and the API skill required by the root guidance.

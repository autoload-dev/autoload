# Examples

This directory of the repository's root module teaches consumers to use the public rules,
through public `@autoload_rules_godot` labels only. Applications such as Lichtpost are
projects directly in it; `addons/<module>/` holds the example application of each add-on
module in `addons/`, whose Godot tests live in `e2e/addons/<module>/`.
Each example's README owns its setup, commands and visible success criteria.

## Common workflows

From the repository root, select the example you are changing:

```sh
bazel test --build_tests_only //examples/lichtpost/...
bazel test --build_tests_only //examples/petri/...
aspect work desktop:addon:sqlite        # an add-on module with its example and e2e tests
```

These run the chosen example's tests, as the lanes' work does; an add-on module's example
runs with the module's lanes ([add-on guidance](../addons/AGENTS.md#lanes)).

An application declares how the repository verifies it in its `app.pkl`, which amends
[tools/apps/App.pkl](../tools/apps/App.pkl), such as its lanes. The lanes' work reads it; no
tool names an application (RG022). For a more focused test, editor or sidecar command,
read that example's README. Required timing and the evidence of each lane come from the root
verification policy, not from the existence of these commands.

## Scope and design

Keep each example small, readable and focused on its use case. Keep an independent add-on demo
when it teaches that workflow. Ruleset dependency/packaging regressions and extra coverage
variants belong in ruleset tests, not additional consumer-probe or missing-add-on projects here.

Example applications that run on phones use portrait orientation: a portrait viewport such as
540x960 with `canvas_items` stretch, `expand` aspect and `window/handheld/orientation=1`, and a
layout that also works in a desktop window. Keep controls, text and other important content
inside the display's safe area, clear of notches, the Dynamic Island and system bars: convert
`DisplayServer.get_display_safe_area()` to viewport units and update it when the viewport size
changes or the window moves.

When adding or moving test targets, read [test ownership](../rules_godot/docs/public/project-layout.md#test-ownership);
for composition changes, read [target placement](../rules_godot/docs/public/project-layout.md#target-ownership-and-project-context).
The public layout guide owns those rules; automated conventions cover mechanical structure.

Show how users test through the example's public targets. Do not write custom drivers around
internal tools. If the public API lacks a needed capability, report the gap and scope the
ruleset work separately before depending on it in an example migration.

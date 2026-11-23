# Examples

This independent Bazel module teaches consumers to use the public rules. `addons/` holds
reusable add-ons with demo/test projects; `projects/` holds applications such as Lichtpost.
Each example's README owns its setup, commands and visible success criteria.

## Common workflows

From this directory, select the example you are changing:

```sh
bazel test --build_tests_only //addons/sqlite/...
bazel test --build_tests_only //addons/platform_paths/...
bazel test --build_tests_only //addons/app_auth/...
bazel test --build_tests_only //addons/dart/...
bazel test --build_tests_only //projects/lichtpost/...
bazel test --build_tests_only --config=petri //projects/petri/...
```

These run the chosen example's host tests, as the host lane's `test:example:<name>` work does;
Petri's builds its engine from source with `--config=petri` and belongs to the source-engine
lane. For a more focused test, editor or sidecar command,
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

When adding or moving test targets, read [test ownership](../docs/public/project-layout.md#test-ownership);
for composition changes, read [target placement](../docs/public/project-layout.md#target-ownership-and-project-context).
The public layout guide owns those rules; automated conventions cover mechanical structure.

Show how users test through the example's public targets. Do not write custom drivers around
internal tools. If the public API lacks a needed capability, report the gap and scope the
ruleset work separately before depending on it in an example migration.

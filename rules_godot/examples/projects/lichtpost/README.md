# Lichtpost

A one-button courier runner across floating gardens. Bring the last light to
the greenhouse and collect light groups for a higher score.

Press **Space** or tap the playfield to jump; hold briefly to jump higher.
Avoid gaps and striped pipes. **Esc** or **Pause** pauses the run. After a fall
or delivery, retry the same route or choose **New route**.

Choose **Options** to mute sound or reduce motion. Options and your best score
are saved locally. Reduced motion removes shake, particle bursts and bouncing
animation while keeping the same controls and route.

Run these commands from `examples/` on macOS or Linux:

1. `bazel run //projects/lichtpost:run` opens the game. Choose **Let's go** to play.
2. `bazel run //projects/lichtpost:edit` opens the project in Godot for editing.
   Use `bazel run //projects/lichtpost:test_edit` for the test context with GdUnit and suites.
3. `bazel run //projects/lichtpost:update` writes missing metadata into the checkout:
   sidecars beside their source files, node IDs and resource UIDs into scenes. Use `bazel run //projects/lichtpost:test_update`
   for the test sources in `tests/`.
4. `bazel test //projects/lichtpost/tests` validates the production and test GDScript the
   suites use and runs the gameplay and input suites. All should pass.
5. `bazel build //projects/lichtpost:pack` exports the production PCK.
6. `bazel build //projects/lichtpost:app --@autoload_rules_godot//godot:macos_signing=adhoc` on macOS or
   `bazel build //projects/lichtpost:app` on Linux builds a desktop app for the host using the
   prebuilt Godot runtime. Find its bundle and archive under `bazel-bin/`.

The host workflow needs no mobile SDK. The macOS app is ad-hoc signed for local
use; distribution signing is a separate step. Game tests and their data live
alongside their execution targets in `tests/`. They are not dependencies
of the production project.

For mobile packaging, use the [Android and iOS prerequisites](../../../docs/public/platforms.md)
and stay in `examples/`:

- `bazel build //projects/lichtpost:app --config=android --config=aab`
  produces the unsigned App Bundle. Omit `--config=aab` for a signed APK.
- `bazel build //projects/lichtpost:app --config=simulator` produces the arm64 simulator app
  under `bazel-bin/projects/lichtpost/`. For device signing, follow the
  [iOS signing guide](../../../docs/public/platforms.md#ios).

Replace `--config=android` with `--config=multi_abi` to request the Android distribution
CPUs; [export platforms](../../../docs/public/platforms.md#export-platforms) explain
CPU selection.

Lichtpost plays in portrait on phones and opens a portrait window on desktop; a landscape window
shows more of the route ahead. Mobile uses the same playfield tap and hold controls; tap **Pause**
to pause. The buttons and score stay clear of notches and system bars.

`main/game.tscn` composes the screen flow and `main/run/run.tscn`, the reusable round.
Each scene component in `main/components/` and `main/ui/` has its own folder and script.
`main/levels/level_01/level_01.tres` supplies integer route data, patterns, palette
and background assets. To add a level, create another LevelDefinition resource
and assign it to the game scene; the round and controls are shared. Shared
palette materials, UI theme and font live in `main/shared/`.
Levels must finish within 7,200 ticks (120 seconds) to fit the replay input budget.

## Credits

Game code, geometry and UI use the repository [license](../../../../LICENSE).
[Atkinson Hyperlegible](https://fonts.google.com/specimen/Atkinson+Hyperlegible)
by Braille Institute is included under the [SIL Open Font License](main/shared/ui/OFL.txt).
The six sound cues are original synthesized tones, included with the game code.

The three parallax textures in `main/levels/level_01/` were generated with OpenAI's built-in
image generation on 2026-10-28; the tool does not identify the exact model.
They follow the project's original Lichtpost concept and were selected for
this game, with no third-party image inputs. Transparency came from generation;
the PNGs have no crop, resize or alpha post-processing. Tinting and mirrored
repetition happen in the game. They are distributed under the
repository license; AI-generated output carries no claim of exclusivity (see
[OpenAI's output terms](https://openai.com/policies/terms-of-use/#content)).

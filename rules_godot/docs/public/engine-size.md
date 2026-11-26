# Make the engine small

Godot's official export templates contain every module, class and renderer, so the engine
is often the largest part of an application. An [engine built from source](engine.md#build-an-engine-from-source)
contains only what you choose. This guide goes through the levers from the largest to the
smallest effect. Each lever removes something your application might need, so run the
whole game after each step.

| Step | Lever | Removes |
| --- | --- | --- |
| 1 | [Choose the modules](#1-choose-the-modules) | modules the project does not use |
| 2 | [Choose the renderers](#2-choose-the-renderers) | rendering methods and their drivers |
| 3 | [Turn off engine features](#3-turn-off-engine-features) | 3D, physics, navigation, XR, advanced GUI, compatibility code |
| 4 | [Use a build profile](#4-use-a-build-profile) | single classes the project does not use |
| 5 | [Optimize for size](#5-optimize-for-size) | inlined and unreachable code |

For an iOS application on Godot 4.7.2 that runs GDScript and renders a 2D scene with the
Compatibility renderer, these steps took the engine to an eighth of the official template.
Sizes are of the device executable without symbols, as an App Store build ships it:

| Engine | Size |
| --- | ---: |
| Official template | 64.5 MiB |
| Steps 1 to 3: only `gdscript`, Compatibility renderer, features off (`-O2`) | 24.6 MiB |
| Plus step 5: `size_min` and full LTO | 10.2 MiB |
| Plus step 4: a build profile disabling 177 unused classes | 8.1 MiB |

## Before you start

Give the engine a [`build` tag](engine.md#build-an-engine-from-source), and build release
applications with `-c opt`. The steps below change the `build` tag and, for step 5, build
settings. Every recipe of an engine shares these choices; if two applications need
different engines, register each as its own [named engine](engine.md#name-an-engine).

To compare steps, build the application with `-c opt` and compare what you ship: the APK or
AAB, the `.app` or IPA, or the desktop archive. Compressed sizes tell you the download;
uncompressed sizes tell you install size, memory and load time.

## 1. Choose the modules

`enabled_modules` is an allowlist: every other module stays out. Without it, a recipe
builds only `gdscript` and `text_server_fb`.

```starlark
godot_engines.build(
    engine = "my_engine",
    enabled_modules = ["gdscript", "text_server_fb", "freetype", "webp"],
)
```

Which modules an application needs depends on its project and on how its resources were
imported, not only on the classes its scenes use:

- `freetype` for TrueType and OpenType fonts.
- `webp` for textures imported as lossless or lossy, which Godot stores as WebP. Without it
  the textures fail to load at run time; the build does not fail.
- `text_server_fb` is the smaller text server. It has no complex text shaping and no
  bidirectional text; projects that show Arabic, Hebrew or Indic scripts need
  `text_server_adv` instead. An engine takes one text server: the two define the same
  symbols, so a recipe that enables both fails.
- Modules your scripts reach by name, through `ClassDB`, `load()` or reflection, are not
  visible to any check.

Required upstream dependencies follow automatically: enabling `theora` also enables
`vorbis` and `ogg`. Optional dependencies stay disabled. Reflection, dynamic resource paths,
extensions and external PCKs keep a project scan from inferring every module, so you
choose the list.

## 2. Choose the renderers

`renderers` names the rendering methods the engine contains: `gl_compatibility`, `mobile`
and `forward_plus`. The recipe derives the drivers from them: OpenGL for Compatibility, and
for the other two the platform's RenderingDevice driver, Metal on Apple platforms and
Vulkan on Android and Linux. `build_options` may not set `opengl3`, `metal` or `vulkan`
too. Godot 4.7 builds both RenderingDevice methods or neither; 4.8 builds each on its own
and leaves RenderingDevice out without them. Godot's iOS Simulator build has no Metal, so
a Simulator engine runs `gl_compatibility` only.

With only `gl_compatibility`, the engine leaves out RenderingDevice and its Vulkan or
Metal driver. On iOS, what only Metal needs came to about 12.5 MiB of a full engine: the
shader compilers glslang and SPIRV-Cross and the RenderingDevice renderer.

```starlark
    renderers = ["gl_compatibility"],
```

The project's rendering method on the application's platform,
`rendering/renderer/rendering_method` with its `.mobile` override, must be one of them.
Godot has no fallback for a method an engine lacks, so the build fails instead of the
application at start. Set it to `gl_compatibility` for the example. Without `renderers`,
a recipe keeps Godot's drivers and its `build_options`, and nothing is checked.

## 3. Turn off engine features

`build_options` passes Godot's own switches. These remove whole features from export
templates:

| Option | Removes |
| --- | --- |
| `disable_3d = "yes"` | 3D nodes; for 2D games |
| `disable_physics_2d = "yes"`, `disable_physics_3d = "yes"` | the physics server and physics nodes |
| `disable_navigation_2d = "yes"`, `disable_navigation_3d = "yes"` | navigation |
| `disable_xr = "yes"` | XR nodes and the XR server |
| `disable_advanced_gui = "yes"` | advanced GUI nodes: dialogs (`AcceptDialog`, `FileDialog`), `PopupMenu`, `OptionButton`, `MenuButton`, `SpinBox`, `Tree`, `TextEdit`, `RichTextLabel`, `ColorPicker` and others |
| `deprecated = "no"` | compatibility code for removed features |
| `brotli = "no"` | Brotli decompression and WOFF2 fonts, including Godot's built-in default font |

```starlark
    build_options = {
        "disable_physics_2d": "yes",
        "disable_physics_3d": "yes",
        "disable_navigation_2d": "yes",
        "disable_navigation_3d": "yes",
        "disable_xr": "yes",
        "disable_advanced_gui": "yes",
    },
```

Menus and settings screens often use `OptionButton`, `PopupMenu` or dialogs; check what the
project's UI uses before turning off the advanced GUI.

With `brotli = "no"`, Godot's default theme has no font, and text without a font of the
project's own stays invisible. Set a TrueType or OpenType font as the project's default
theme font before you turn it off.

Editor recipes reject options that apply to templates only, such as `disable_3d`: give
the editors their own `build_options` with an
[`editor` tag](engine.md#build-the-editors-differently).

## 4. Use a build profile

A build profile removes single classes from one application's runtime. Godot's editor writes
one: **Project → Tools → Engine Compilation Configuration Editor**, then **Detect from
Project**, then save the `.gdbuild` file into your repository and pass its label to the
application:

```starlark
godot_app(
    name = "app",
    pack = ":pack",
    build_profile = "release.gdbuild",
)
```

Detection reads the project's scenes, resources and scripts. It does not see classes that
code creates by name or that only some paths of the game load. Review the list, and add
back what the game needs: an application that loads a disabled class fails when it loads
it, not at build time. Tests, imports and the editor keep every class; see
[an application's build profile](engine.md#an-applications-build-profile).

A profile that only disables classes needs no pin: the class list reaches the engine's class
generator when it runs, and only the sources that register classes recompile. A profile with
build options, such as `disable_3d`, needs `MODULE.bazel` to register it with
`godot_engines.runtime_profile`, which gives the engine's runtime recipes a variant with
those options; its options must agree with the recipe's `build_options` and `renderers`. See
[build options in a build profile](engine.md#build-options-in-a-build-profile).

### Derive the profile from the project

`godot_runtime_profile` runs Godot's detection for you, headless, with the editor of the
selected engine, and keeps the result in your repository. It needs the editor only, not an
engine build:

```starlark
load("@autoload_rules_godot//godot:defs.bzl", "godot_runtime_profile")

godot_runtime_profile(
    name = "update_profile",
    project = ":project",
    deps = ["//path/to/game"],
    profile = "runtime.gdbuild",
    keep_classes = ["Camera3D"],
)
```

`bazel run //path/to:update_profile` writes `runtime.gdbuild` beside the target; commit it.
It is one file, as Godot writes it: `disabled_classes` and `disabled_build_options`, which
holds the build options and the module switches the detection turns off, such as
`disable_physics_3d` and `module_openxr_enabled`. Register it in `MODULE.bazel` with a
`godot_engines.runtime_profile` tag, and name it as `godot_app`'s `build_profile`; the
[engine guide](engine.md#build-options-in-a-build-profile) says what the registration does.
The profile also turns off the drivers the detection finds unused; they must agree with the
engine's `renderers` from [step 2](#2-choose-the-renderers).

`bazel test //path/to:update_profile.test` fails while the file is missing or differs from
the detection, and names the command that writes it, so the profile follows the project.

The profile is the detection minus two sets of classes. The first is a list of classes the
engine creates itself, such as `Image`, `Script` and `Shader`, which Godot's detection
names for a project that never mentions them and which an engine cannot start without. The
ruleset keeps that list for each Godot minor. The second is `keep_classes`, the classes
your game creates by name, loads on some paths or gets from an add-on's code, which
detection cannot see. Run the whole game, as [the check below](#check-the-result)
says, and add what fails.

Applying Lichtpost's whole detection, with its 227 classes, the build options and the modules
the detection turns off, took the macOS template of Godot 4.7.2 from 61.3 MB to 33.1 MB.

## 5. Optimize for size

Two build settings compile and link the engine for size, without changing extensions or
application code:

```sh
bazel build //path/to:app -c opt \
  --@autoload_rules_godot//godot:engine_optimize=size_min \
  --@autoload_rules_godot//godot:engine_lto=full
```

`size_min` compiles with `-Oz` and stops Godot's forced inlining; `full` LTO lets the linker
remove code across the whole engine and takes the longest to link. To make it the default
for one application, set them on `godot_app`:

```starlark
godot_app(
    name = "game",
    pack = ":pack",
    application_id = "com.example.game",
    engine_optimize = "size_min",
    engine_lto = "full",
)
```

These settings need a runtime built from source. An application of a catalogued engine
without a `build` tag gets one too: under `-c opt` with settings other than the defaults,
it takes the runtime the engine builds from the release's sources instead of the official
template. An engine with binaries but no sources keeps its prebuilt runtimes and ignores
the settings.

The iOS engine from the start of this guide, after steps 1 to 3:

| `engine_optimize` | `engine_lto=none` | `engine_lto=full` |
| --- | ---: | ---: |
| `speed_trace` (`-O2`) | 24.6 MiB | |
| `size` (`-Os`) | 21.8 MiB | |
| `size_extra` | 18.4 MiB | 17.1 MiB |
| `size_min` | 15.4 MiB | 10.2 MiB |

`size_min` gains most from full LTO. Full LTO took that engine's build from about 33 s to
75–95 s.

A third setting, `--@autoload_rules_godot//godot:engine_vfe` (`godot_app.engine_vfe = "on"`,
off by default), lets the full LTO link drop the virtual functions nothing calls. **It
makes native engines larger, not smaller.** Elimination needs Godot's `TYPED_METHOD_BIND`,
Godot's default under MSVC. Without it, Godot's method binds call virtual setters through
member function pointers cast to a class without a vtable, so elimination sees no call to
them, clears their slots and the engine crashes at start. With it, every class gets its
own copy of each method binding it registers: the engine's method bindings double, which
costs more than elimination saves. With `size_min` and full LTO, on Godot 4.7.2, without
symbols:

| Engine | Without `engine_vfe` | With `engine_vfe` |
| --- | ---: | ---: |
| macOS executable, Lichtpost's modules | 15.5 MiB | 17.0 MiB (+9.6 %) |
| The same with a build profile | 12.0 MiB | 12.8 MiB (+6.9 %) |
| Android `libgodot_android.so`, a 2D engine without 3D, 2D physics and navigation | 16.0 MiB | 16.7 MiB (+4.6 %) |

Compressed, the Android library shrinks by 0.6 % and the macOS executable grows by
about 5 %. Elimination pays off only when the engine's method bindings are already
reduced: a web engine that kept only the bindings its game called shrank by 10 %. Leave
`engine_vfe` off unless you measured a gain for your engine.

It needs `engine_lto=full`, fails the build without it, and needs Clang: Apple's
toolchains and the Android NDK have it, while a Linux engine built with GCC fails to
compile. Elimination assumes that every virtual call into the engine's classes is part of
the engine's LTO link. Custom modules and patches compile as part of the engine, and
GDExtensions call the engine through function pointers, not C++ virtual calls, so both are
unaffected. Apple engines carry their objects into the application's link, where native
code compiled outside the engine, such as a library in `platform_deps`, must not call
virtual functions of engine classes: the call reaches a cleared slot and crashes. Keep such
code inside the engine, as a custom module or a patch.

Smaller code can run slower. Measure frame times on your weakest target device; `size` and
`size_extra` lie between Godot's default and `size_min`.
[Optimization](engine.md#optimization) lists every value.

## Check the result

After each step:

1. Build the application with `-c opt` and compare its size to the previous step.
2. Run every scene and path of the game on each platform, including rarely reached ones:
   menus, settings, result screens, localized text.
3. Watch the log for missing classes, failed resource loads and invisible text.

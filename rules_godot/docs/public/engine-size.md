# Make the engine small

Godot's official export templates contain every module, class and renderer, so the engine
is often the largest part of an application. A [source build](engine.md#build-an-engine-from-source)
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

Declare a [source build](engine.md#declare-a-source-build) for the platforms you ship, and
build release applications with `-c opt`. The steps below change the `source_build` tag
and, for step 5, build settings. Every recipe of a source build shares these choices; if
two applications need different engines, give each its own source build and
[name the engines](engine.md#name-an-engine).

To compare steps, build the application with `-c opt` and compare what you ship: the APK or
AAB, the `.app` or IPA, or the desktop archive. Compressed sizes tell you the download;
uncompressed sizes tell you install size, memory and load time.

## 1. Choose the modules

`enabled_modules` is an allowlist: every other module stays out. Without it, a recipe
builds only `gdscript` and `text_server_fb`.

```starlark
godot_engines.source_build(
    name = "my_engine",
    source = "@godot_sources//:source.json",
    platforms = ["android", "ios"],
    build_targets = ["template_release"],
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
  `text_server_adv` instead. A recipe takes one of the two.
- Modules your scripts reach by name, through `ClassDB`, `load()` or reflection, are not
  visible to any check.

Upstream dependencies follow automatically: enabling `theora` also enables `vorbis` and
`ogg`.

## 2. Choose the renderers

`renderers` names the rendering methods the engine contains: `gl_compatibility`, `mobile`
and `forward_plus`. With only `gl_compatibility`, the engine leaves out RenderingDevice and
its Vulkan or Metal driver. On iOS, what only Metal needs came to about 12.5 MiB of a full
engine: the shader compilers glslang and SPIRV-Cross and the RenderingDevice renderer.

```starlark
    renderers = ["gl_compatibility"],
```

The project's rendering method must be one of them. Set
`rendering/renderer/rendering_method` (and its `.mobile` override) to `gl_compatibility`;
otherwise the application's build fails, since Godot has no fallback at run time.

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

Editor recipes reject options that apply to templates only, such as `disable_3d`.

## 4. Use a build profile

A build profile removes single classes. Godot's editor writes one: **Project → Tools →
Engine Compilation Configuration Editor**, then **Detect from Project**, then save the
`.gdbuild` file into your repository and pass its label:

```starlark
    build_profile = "//engines:game.gdbuild",
)
```

Detection reads the project's scenes, resources and scripts. It does not see classes that
code creates by name or that only some paths of the game load. Review the list, and add
back what the game needs: an application that loads a disabled class fails when it loads
it, not at build time. A profile's `disabled_build_options` must agree with the recipe's
`build_options` and `renderers`.

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
currently makes native engines larger, not smaller.** Elimination needs Godot's
`TYPED_METHOD_BIND`, without which the engine crashes at start, and that switch gives every
class its own copy of each method binding it registers: the engine's method bindings
double, which costs more than elimination saves. With `size_min` and full LTO, on Godot
4.7.2, without symbols:

| Engine | Without `engine_vfe` | With `engine_vfe` |
| --- | ---: | ---: |
| macOS executable, Lichtpost's modules | 15.5 MiB | 17.0 MiB (+9.6 %) |
| The same with a build profile | 12.0 MiB | 12.8 MiB (+6.9 %) |
| Android `libgodot_android.so`, the 2D engine of steps 1 to 3 | 16.0 MiB | 16.7 MiB (+4.6 %) |

Compressed, the Android library shrinks by about 1 % and the macOS executable grows by
about 5 %. Elimination pays off only when the engine's method bindings are already
reduced: a web engine that kept only the bindings its game called shrank by 10 %. Leave
`engine_vfe` off unless you measured a gain for your engine.

It needs `engine_lto=full`, fails the build without it, and needs Clang: Apple's
toolchains and the Android NDK have it, while a Linux engine built with GCC fails to
compile. Keep native code that calls virtual functions of engine classes inside the
engine, as a custom module or a patch: on Apple platforms, a library in `platform_deps`
that does so crashes when the call reaches a removed function.

Smaller code can run slower. Measure frame times on your weakest target device; `size` and
`size_extra` lie between Godot's default and `size_min`.
[Optimization](engine.md#optimization) lists every value.

## Check the result

After each step:

1. Build the application with `-c opt` and compare its size to the previous step.
2. Run every scene and path of the game on each platform, including rarely reached ones:
   menus, settings, result screens, localized text.
3. Watch the log for missing classes, failed resource loads and invisible text.

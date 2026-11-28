# Split the extension rules into their primitives

New issue. The issues on missing extension libraries and on web extensions build on it.

---

## Goal

The parts of a GDExtension map to Bazel targets one to one, and each part is a public
rule: the native code, the extension library Godot loads on a platform, and the extension
with its descriptor. `godot_cc_extension` stays, as a macro over them that builds a C++
extension the same way on every platform.

## Problem

`godot_extension` takes a library "as another rule linked it, in any language".
`godot_cc_extension` is its C++ shorthand, and holds privately everything about linking
native code so that Godot loads it: exporting only the entry symbol, the run paths, the
iOS framework or archive. Nothing else can reach that.

- An extension in another language, or one that mixes a vendor's prebuilt library on one
  platform with its own sources on another, has to repeat that linking by hand.
- A C++ extension cannot say that it supports only some platforms. The platforms are a
  property of the extension, and the shorthand exposes only the sources of the library.
- The web adds a fourth way to link, a side module with the engine's ABI. It belongs to
  linking, not to a macro for C++.

## The parts

| Godot concept | What it is | Target |
| --- | --- | --- |
| Native code | Code compiled against the GDExtension API, in C++ through godot-cpp | `cc_library`, or any rule that provides `CcInfo` |
| Extension library | What Godot loads on a platform: a shared library, an iOS framework or archive, a side module on the web | `godot_extension_library` (new) |
| Extension | The descriptor and what goes with the library: files beside it, platform libraries, Info.plist fragments, the editor's library | `godot_extension` |

## API

### The three primitives

```starlark
load("@autoload_rules_godot//godot/extension:defs.bzl", "godot_extension", "godot_extension_library")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

# The code.
cc_library(
    name = "paths",
    srcs = ["register_types.cc"] + select({
        "@platforms//os:android": ["paths_android.cc"],
        "@platforms//os:ios": ["paths_ios.mm"],
        "@platforms//os:linux": ["paths_linux.cc"],
        "@platforms//os:macos": ["paths_macos.mm"],
    }),
    deps = ["@godot_cpp//:godot_cpp"],
)

# The extension library: the code linked as Godot loads it on the target platform.
godot_extension_library(
    name = "paths_library",
    deps = [":paths"],
    entry_symbol = "platform_paths_init",
)

# The extension.
godot_extension(
    name = "platform_paths",
    library = select({
        "@platforms//os:android": ":paths_library",
        "@platforms//os:ios": ":paths_library",
        "@platforms//os:linux": ":paths_library",
        "@platforms//os:macos": ":paths_library",
        "//conditions:default": None,
    }),
)
```

`godot_extension_library` links what its `deps` provide into the one file the target
platform loads, exports only the entry symbol and lets the library find its shared
dependencies beside it. It passes the entry symbol on, so the extension does not repeat
it.

| Operating system | What it produces |
| --- | --- |
| Linux, Android | a shared library |
| macOS | a dynamic library |
| iOS | a dynamic framework, or with `ios_linkage = "static"` the archive the application links |

### A prebuilt library beside a built one

```starlark
godot_extension(
    name = "crash_reporter",
    # A prebuilt file carries no entry symbol, so the extension names it.
    entry_symbol = "crash_reporter_init",
    library = select({
        "@platforms//os:android": "lib/arm64-v8a/libcrash_reporter.so",
        "@platforms//os:linux": ":crash_reporter_library",
        "//conditions:default": None,
    }),
)
```

The extension fails analysis when a library's entry symbol differs from its own.

### The macro

Unchanged for a C++ extension that builds everywhere:

```starlark
godot_cc_extension(
    name = "game_extension",
    srcs = ["register_types.cc", "movement.cc"],
    entry_symbol = "game_library_init",
)
```

It declares the three targets and nothing else. An extension that supports only some
platforms uses the primitives.

## Open

- Where the iOS attributes go. Linkage and bundle identifier describe the library;
  minimum operating-system versions probably too. On iOS the macro today hands the code's
  `cc_library` to the extension as well, so that applications embed the resources and
  frameworks of its dependencies; that has to travel through the library's provider.
- Whether a plain `cc_binary(linkshared = True)` stays accepted as a library, beside the
  new rule.
- The names of the macro's generated targets, which documentation and tests refer to.

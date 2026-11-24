# Choosing Godot versions

`rules_godot` targets **Godot >=4.7.2 and <5.0.0**. This is a compatibility
range, so a compatible patch or minor release does not need to be added to an
allowlist before you can use it. Godot 5, including its previews, and versions
below 4.7.2 are rejected.

The range is distinct from two narrower lists: the exact downloads bundled with
this ruleset, and the versions exercised by validation. An accepted version is
not evidence that every export platform and build configuration has been tested with
it. See [platform setup](platforms.md) for the configuration of each operating system.

## Pin a release

Every build still selects an **exact version and checksum**. A compatibility
range never causes Bazel to resolve “latest” or change downloads without a
repository change. [Installation](installation.md#add-the-module) shows the registration.

Built-in editor and template digests are available for these versions:

| Rules version string | Official release tag | Editor platforms |
| --- | --- | --- |
| `4.7.2` | `4.7.2-stable` | macOS universal; Linux x86_64 and ARM64 |
| `4.8.0-beta1` | `4.8-beta1` | macOS ARM64 and x86_64 separately; Linux x86_64 and ARM64 |

Built-in pins download from `downloads.godotengine.org` and fall back to the release on
GitHub; the digests verify either source.

The [official archive](https://godotengine.org/download/archive/) and
[4.8 beta 1 release](https://github.com/godotengine/godot-builds/releases/tag/4.8-beta1)
identify the preview used for compatibility checks. Preview releases are an
explicit opt-in:

```starlark
godot_engines.prebuilt(name = "godot", version = "4.8.0-beta1")
```

4.8 beta 1 ships separate ARM64 and x86_64 macOS templates; the catalogue records the
layout, and explicit `templates_urls` describe theirs with `templates_macos_cpus`,
by default `["universal"]`. Catalogued versions also record the CPUs of their iOS
simulator slice and their Android shell AAR.

Version attributes use canonical `major.minor.patch` strings, optionally followed
by `-devN`, `-betaN` or `-rcN`. Include the zero patch component, even when the
upstream tag omits it: `4.8.0-beta1`, not `4.8-beta1`. A preview of 4.7.2 is below
the stable 4.7.2 floor and remains unsupported.

For a compatible release without built-in digests, pin its artifacts on the same tag:
`editor_urls`, `editor_integrity` and `editor_binaries` per editor platform,
`templates_urls` and `templates_integrity`, and optionally the Android shell AAR. This
extends the download catalogue without changing the compatibility policy. For example,
an explicit Linux x86_64 editor and its templates:

```starlark
godot_engines.prebuilt(
    name = "godot_beta",
    version = "4.8.0-beta1",
    editor_urls = {"linux_x86_64": ["https://github.com/godotengine/godot-builds/releases/download/4.8-beta1/Godot_v4.8-beta1_linux.x86_64.zip"]},
    editor_integrity = {"linux_x86_64": "sha512-ruTL88X4bu6HXA8vd8ydgWo/uyIHdOb/yV/VpVemxeyRfythGMCqIAi9EPSyoCEiXceLp7fFR0VBHg8nIfcKZw=="},
    editor_binaries = {"linux_x86_64": "Godot_v4.8-beta1_linux.x86_64"},
    templates_urls = ["https://example.com/Godot_v4.8-beta1_export_templates.tpz"],
    templates_integrity = "sha512-<base64-digest>",
    templates_macos_cpus = ["arm64", "x86_64"],
)
```

Replace the templates URL and digest with a real pinned archive. For another
compatible release, change the version, URLs, binary paths and verified integrity
together. For source-built engines, see [engines](engine.md#build-an-engine-from-source).

## Keep the extension API independent

Choose the editor/runtime release and the GDExtension API baseline separately.
The pinned `godot-cpp` revision and its selected API JSON determine binding
generation and native compilation. The editor toolchain determines resource
imports and pack generation. Changing the engine registration alone must leave those
native compilation inputs unchanged.

Keep `compatibility_minimum = "4.7.2"` when the extension uses only that supported
API. This descriptor field is a stable runtime minimum; it is not the editor
version and does not accept preview suffixes. Raise the API baseline and minimum
only when the extension requires newer functionality. See
[GDExtensions](gdextension.md) for the compatibility contract and validation.

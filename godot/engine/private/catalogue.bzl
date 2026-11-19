"""Built-in pins of official Godot releases for godot_engines.prebuilt."""

visibility(["//godot/..."])

# The CPUs, as Godot's CPU tags, of the Linux templates (templates/linux_*.<cpu>) and the
# Android shell AAR's engine libraries (jni/<abi>/libgodot_android.so) in Godot's official
# builds. A release whose templates differ records its own linux_cpus or android_cpus.
TEMPLATE_CPUS = {
    "linux": ["arm32", "arm64", "x86_32", "x86_64"],
    "android": ["arm32", "arm64", "x86_32", "x86_64"],
}

# Release tag, editor platforms, macOS template layout and archive digests per version.
RELEASES = {
    "4.7.2": {
        "tag": "4.7.2-stable",
        "editor_platforms": ["macos", "linux_x86_64", "linux_arm64"],
        "macos_cpus": ["universal"],
        "macos": "sha512-OKoW5buiCDlB/Fs+VL4Aib1Mw14yQV9bn9mopqe5gYJV1EUy6o75S1rvVsS0B8LWNPpPZX5Ovmgeu/Wbe6xpyg==",
        "linux_x86_64": "sha512-mqAPemBSAJQLzjAnpWe3gvSb2OlA3Qaunph71lruGxRn7dVu2E/Ny91ENUv2E727Tl0pE+klhQNo4VDFntVMZQ==",
        "linux_arm64": "sha512-3VmRjaCGvUm94vVFC15Wf/hlDL3pq717j0yhGX/4xgm6o4g0Zm0DLer7RwmQeNeCInnioOBuVmV0VGjyZTPn4g==",
        "templates": "sha512-yk1xxNe4HfwV0amLqgdTSqlbA/3aeKAHWwZnLhZI0uX0CYDJrcKNI+G5LnMu5780YZl6qASvdOwvzXqTzLhAeQ==",
        # The official simulator XCFramework slice has x86_64 code only.
        "ios_simulator_cpus": ["x86_64"],
        # Official Android shell AARs are template_release builds; Maven Central publishes them.
        "android_shell": {
            "urls": ["https://repo.maven.apache.org/maven2/org/godotengine/godot/4.7.2.stable/godot-4.7.2.stable.aar"],
            "integrity": "sha256-h5Huz+fJak3i0YigvM/puDuSWJpaaCWEdHNBapkOhik=",
        },
    },
    "4.8.0-beta1": {
        "tag": "4.8-beta1",
        "editor_platforms": ["macos_arm64", "macos_x86_64", "linux_x86_64", "linux_arm64"],
        "macos_cpus": ["arm64", "x86_64"],
        "macos_arm64": "sha512-6t31QYJJNz1rfHi63Da+qrodLvWXIyDPaIYtSfPozOddP4IZ9LcRyI3kZW7MpiyDPy0vkbSJRWzdcVfVqBzAjw==",
        "macos_x86_64": "sha512-IOaHvjKo+dnGv4YwhurU3wPYk+W+3UCRl+3+xY1udNk6xXpPg/eH+OEJDnCwuJpdBd3ADbCO9v17oy61G1nyDw==",
        "linux_x86_64": "sha512-ruTL88X4bu6HXA8vd8ydgWo/uyIHdOb/yV/VpVemxeyRfythGMCqIAi9EPSyoCEiXceLp7fFR0VBHg8nIfcKZw==",
        "linux_arm64": "sha512-9cErbuo8ETH9AAHc+XIMJ/IKuGKGsyNbsbLYdVvcll6ufe5G1cDYYp2+Zjouu16hlgY5MA6Tqtiyw2dZjvM4dQ==",
        "templates": "sha512-+lOtaIOubHjunS+NFMpNNIUvohxGLR9LD1mRONfeQIl8wFjxUIOh+oDH1LdZCyIi3qbwVr57SeOlhOtk/DCwtw==",
        # The simulator XCFramework slices of the prerelease engine and AccessKit have
        # incompatible CPUs.
        "ios_simulator_cpus": [],
    },
}

EDITOR_PLATFORMS = {
    "macos": struct(
        suffix = "macos.universal",
        binary = "Godot.app/Contents/MacOS/Godot",
        platform = "macos",
        cpus = ["arm64", "x86_64"],
    ),
    "macos_arm64": struct(
        suffix = "macos.arm64",
        binary = "Godot.app/Contents/MacOS/Godot",
        platform = "macos",
        cpus = ["arm64"],
    ),
    "macos_x86_64": struct(
        suffix = "macos.x86_64",
        binary = "Godot.app/Contents/MacOS/Godot",
        platform = "macos",
        cpus = ["x86_64"],
    ),
    "linux_x86_64": struct(
        suffix = "linux.x86_64",
        binary = "Godot_v{tag}_linux.x86_64",
        platform = "linux",
        cpus = ["x86_64"],
    ),
    "linux_arm64": struct(
        suffix = "linux.arm64",
        binary = "Godot_v{tag}_linux.arm64",
        platform = "linux",
        cpus = ["arm64"],
    ),
}

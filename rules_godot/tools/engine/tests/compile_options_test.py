import unittest
from pathlib import Path

from tools.engine.configure import (
    deployment_target,
    engine_link_options,
    normalize_command,
    platform_compile_options,
)


class CompileOptionsTest(unittest.TestCase):
    def test_bazel_owns_dependency_files_and_their_target_names(self) -> None:
        flags, includes = normalize_command(
            [
                "clang++",
                "-MD",
                "-MMD",
                "-MP",
                "-MF",
                "/host/obj.d",
                "-MT",
                "old.o",
                "-MQquoted.o",
                "-MFother.d",
                "-std=c++17",
                "-c",
                "file.cpp",
            ],
            "file.cpp",
            Path("/source"),
        )
        self.assertEqual(flags, ["-std=c++17"])
        self.assertEqual(includes, [])

    def test_deployment_target_is_captured_from_scons_and_not_replayed(self) -> None:
        flags = ["-arch", "arm64", "-mmacosx-version-min=11.0", "-Wl,-dead_strip"]
        self.assertEqual(deployment_target(flags), "11.0")
        self.assertEqual(deployment_target(["-miphoneos-version-min=12.0"]), "12.0")
        self.assertEqual(deployment_target(["-mios-simulator-version-min=12.0"]), "12.0")
        self.assertEqual(deployment_target(["-O2"]), "")
        replayed, _ = normalize_command(["clang++", *flags], "", Path("/source"))
        self.assertEqual(replayed, ["-Wl,-dead_strip"])

    def test_ios_class_name_does_not_collide_with_apple_toolchain_macro(self) -> None:
        upstream = ["-DIOS_ENABLED"]
        self.assertEqual(
            platform_compile_options("ios", upstream)[-2:], [*upstream, "-UOS_IOS"]
        )
        self.assertNotIn("-UOS_IOS", platform_compile_options("macos", upstream))

    def test_toolchain_only_warnings_are_disabled_before_upstream_flags(self) -> None:
        upstream = ["-Wall", "-Wthread-safety", "-w"]
        for platform, disabled in [
            (
                "android",
                ["-Wno-variadic-macro-arguments-omitted", "-Wno-c++20-designator"],
            ),
            (
                "macos",
                [
                    "-Wno-thread-safety",
                    "-Wno-shorten-64-to-32",
                    "-Wno-undeclared-selector",
                ],
            ),
        ]:
            with self.subTest(platform=platform):
                # Later flags win, so an upstream or patched -W flag stays enabled.
                self.assertEqual(
                    platform_compile_options(platform, upstream)[
                        : len(disabled) + len(upstream)
                    ],
                    [*disabled, *upstream],
                )
        self.assertEqual(
            platform_compile_options("ios", [])[:-1],
            platform_compile_options("macos", []),
        )
        self.assertEqual(
            platform_compile_options("linuxbsd", upstream),
            [*upstream, "-ffunction-sections", "-fdata-sections"],
        )

    def test_bazel_flags_decide_optimization_debug_information_and_stripping(
        self,
    ) -> None:
        upstream = ["-O3", "-Os", "-Og", "-g2", "-gdwarf-4", "-ffast-math", "-DNDEBUG"]
        self.assertEqual(
            platform_compile_options("linuxbsd", upstream),
            ["-ffast-math", "-DNDEBUG", "-ffunction-sections", "-fdata-sections"],
        )
        apple = ["-Wl,-S", "-Wl,-x", "-Wl,-dead_strip", "-ObjC", "-framework", "Metal"]
        self.assertEqual(
            engine_link_options("macos", [*apple, "-O2"]),
            ["-Wl,-dead_strip", "-ObjC", "-framework", "Metal"],
        )
        self.assertEqual(engine_link_options("android", ["-s", "-llog"]), ["-llog"])
        # The iOS application still drops the engine objects it never reaches.
        self.assertEqual(engine_link_options("ios", ["-O2"]), ["-Wl,-dead_strip"])
        # So does a Linux application, from sections of their own per function and datum,
        # as the Android one does through upstream's flags.
        self.assertEqual(
            engine_link_options("linuxbsd", ["-s", "-lpthread"]),
            ["-lpthread", "-Wl,--gc-sections"],
        )

    def test_debug_symbol_flags_keep_their_relative_paths(self) -> None:
        flags, _includes = normalize_command(
            [
                "clang++",
                "-gdwarf-4",
                "-g2",
                "-ffile-prefix-map=/source=.",
                "-c",
                "core/object.cpp",
            ],
            "core/object.cpp",
            Path("/source"),
        )
        self.assertEqual(flags, ["-gdwarf-4", "-g2"])

    def test_android_debug_info_names_no_sandbox_directory(self) -> None:
        # Bazel's flags decide whether there is debug information.
        self.assertEqual(
            platform_compile_options("android", ["-DNDEBUG"])[-1],
            "-fdebug-compilation-dir=.",
        )
        self.assertNotIn(
            "-fdebug-compilation-dir=.", platform_compile_options("ios", ["-DNDEBUG"])
        )

    def test_apple_sdk_includes_come_from_cc_toolchain(self) -> None:
        flags, includes = normalize_command(
            [
                "clang++",
                "-I/SDK/usr/include",
                "-I/SDK/System/Library/Frameworks/OpenGLES.framework/Headers",
                "-Iplatform/ios",
                "-c",
                "file.mm",
            ],
            "file.mm",
            Path("/source"),
            ["/SDK"],
        )
        self.assertEqual(
            flags,
            [
                "-I__BAZEL_XCODE_SDKROOT__/usr/include",
                "-I__BAZEL_XCODE_SDKROOT__/System/Library/Frameworks/OpenGLES.framework/Headers",
            ],
        )
        self.assertEqual(includes, ["platform/ios"])
        with self.assertRaisesRegex(ValueError, "outside engine source"):
            normalize_command(
                ["clang++", "-I/undeclared/include", "file.mm"],
                "file.mm",
                Path("/source"),
                ["/SDK"],
            )

    def test_cc_toolchain_owns_compiler_cpu_and_sdk(self) -> None:
        flags, includes = normalize_command(
            [
                "host-clang++",
                "-o",
                "out.o",
                "-c",
                "-arch",
                "arm64",
                "-isysroot",
                "/host/SDK",
                "-std=gnu++17",
                "-Icore",
                "-DMODULE=yes",
                "core/file.cpp",
            ],
            "core/file.cpp",
            Path("/source"),
        )
        self.assertEqual(flags, ["-std=gnu++17", "-DMODULE=yes"])
        self.assertEqual(includes, ["core"])


if __name__ == "__main__":
    unittest.main()

import argparse
import tempfile
import unittest
from pathlib import Path

from tools.engine.configure import (
    engine_renderers,
    has_renderer_switches,
    renderer_options,
    require_renderer_options_unset,
    with_renderer_modules,
)


class RenderersTest(unittest.TestCase):
    def test_renderers_decide_the_drivers_of_each_platform(self) -> None:
        self.assertEqual(
            renderer_options(["gl_compatibility"], "ios", False),
            ["opengl3=yes", "metal=no", "vulkan=no"],
        )
        self.assertEqual(
            renderer_options(["mobile"], "android", False),
            ["opengl3=no", "vulkan=yes"],
        )
        self.assertEqual(
            renderer_options(["gl_compatibility", "forward_plus"], "linuxbsd", False),
            ["opengl3=yes", "vulkan=yes"],
        )
        # Godot 4.8 leaves out RenderingDevice and each renderer on its own.
        self.assertEqual(
            renderer_options(["mobile"], "macos", True),
            [
                "opengl3=no",
                "metal=yes",
                "vulkan=no",
                "rendering_device=yes",
                "forward_plus_renderer=no",
                "forward_mobile_renderer=yes",
            ],
        )
        with self.assertRaisesRegex(ValueError, "Unknown rendering methods: vulkan"):
            renderer_options(["vulkan"], "ios", False)

    def test_an_engine_runs_the_methods_its_drivers_bring(self) -> None:
        # Without 4.8's switches a RenderingDevice driver brings both of its renderers.
        self.assertEqual(
            engine_renderers(["mobile"], "android", "", False), ["mobile", "forward_plus"]
        )
        self.assertEqual(engine_renderers(["mobile"], "android", "", True), ["mobile"])
        # Godot's iOS Simulator build turns Metal and Vulkan off.
        self.assertEqual(
            engine_renderers(["gl_compatibility", "mobile"], "ios", "simulator", False),
            ["gl_compatibility"],
        )
        self.assertEqual(
            engine_renderers(["gl_compatibility", "mobile"], "ios", "device", False),
            ["gl_compatibility", "mobile", "forward_plus"],
        )

    def test_renderer_switches_are_detected_in_godots_sconstruct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for text, expected in [
                ('opts.Add(BoolVariable("vulkan", "Vulkan", True))', False),
                # Godot 4.8 wraps the option's arguments over several lines.
                ('opts.Add(\n    BoolVariable(\n        "rendering_device",\n', True),
            ]:
                (root / "SConstruct").write_text(text)
                self.assertEqual(has_renderer_switches(root), expected, text)

    def test_renderingdevice_methods_bring_the_shader_compiler(self) -> None:
        graph = {"gdscript": [], "glslang": []}

        def modules(renderers: str, environment: str = "device") -> list[str]:
            args = argparse.Namespace(
                modules=["gdscript"],
                renderers=renderers,
                platform="ios",
                environment=environment,
            )
            return with_renderer_modules(args, graph)

        self.assertEqual(modules("gl_compatibility,mobile"), ["gdscript", "glslang"])
        self.assertEqual(modules("gl_compatibility"), ["gdscript"])
        self.assertEqual(modules(""), ["gdscript"])
        # Godot's iOS Simulator build has no RenderingDevice driver and rejects glslang.
        self.assertEqual(modules("mobile", "simulator"), ["gdscript"])

    def test_renderers_and_build_options_cannot_both_set_a_driver(self) -> None:
        derived = renderer_options(["gl_compatibility"], "ios", False)
        require_renderer_options_unset(derived, ["disable_3d=yes"])
        with self.assertRaisesRegex(ValueError, "renderers decides metal, opengl3"):
            require_renderer_options_unset(derived, ["opengl3=yes", "metal=no"])


if __name__ == "__main__":
    unittest.main()

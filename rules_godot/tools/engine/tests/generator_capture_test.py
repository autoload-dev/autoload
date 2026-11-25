import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.engine.configure import (
    include_closure,
    is_directory_action,
    normalize_value,
    scalar_environment,
)


class GeneratorCaptureTest(unittest.TestCase):
    def test_scons_callable_actions_need_no_function_name(self) -> None:
        # SCons' Android Copy/Move actions use ActionCaller objects rather than
        # Python functions. They must reach platform staging classification.
        class ActionCaller:
            def __call__(self) -> None:
                pass

        self.assertFalse(
            is_directory_action([SimpleNamespace(execfunction=ActionCaller())])
        )

    def test_generator_environment_excludes_unused_build_options(self) -> None:
        env = {"used": True, "unrelated_module_enabled": True}
        self.assertEqual(
            scalar_environment(env, 'def build(env):\n    return env["used"]'),
            {"used": True},
        )

    def test_generator_environment_follows_helpers_without_capturing_unrelated_options(
        self,
    ) -> None:
        class Env(dict):
            dev_build = False

        def compress(buffer: bytes, env: Env) -> bytes | None:
            return buffer if env["production"] or env.dev_build else None

        env = Env(production=True, unrelated_module_enabled=True)
        self.assertEqual(
            scalar_environment(
                env,
                'def build(env):\n    return compress(b"", env)',
                {"compress": compress},
            ),
            {"production": True, "dev_build": False},
        )

    def test_unresolved_environment_forwarding_fails_instead_of_omitting_inputs(
        self,
    ) -> None:
        def helper(env: dict[str, bool]) -> bool:
            return env.get("production", False)

        with self.assertRaisesRegex(
            ValueError, "Unsupported generator helper receiving env: callback"
        ):
            scalar_environment(
                {"production": True},
                "def build(env):\n    callback = helper\n    return callback(env)",
                {"helper": helper},
            )
        with self.assertRaisesRegex(ValueError, "environment alias or escape"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    settings = env\n    return helper(settings)",
                {"helper": helper},
            )
        with self.assertRaisesRegex(
            ValueError, "Unsupported generator helper receiving env: helper"
        ):
            scalar_environment(
                {"production": True},
                "def build(env):\n    helper = replacement\n    return helper(env)",
                {"helper": helper},
            )
        with self.assertRaisesRegex(
            ValueError, "Unsupported generator helper receiving env: helper"
        ):
            scalar_environment(
                {"production": True},
                "def build(env):\n    from local_helpers import helper\n    return helper(env)",
                {"helper": helper},
            )

        def renamed(settings: dict[str, bool]) -> bool:
            return settings.get("production", False)

        with self.assertRaisesRegex(ValueError, "parameter named env"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    return renamed(env)",
                {"renamed": renamed},
            )

        def keywords(**settings: dict[str, bool]) -> bool:
            return settings.get("env", {}).get("production", False)

        with self.assertRaisesRegex(ValueError, "parameter named env"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    return keywords(env=env)",
                {"keywords": keywords},
            )
        with self.assertRaisesRegex(ValueError, "environment method: env.copy"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    settings = env.copy()\n    return settings.get('production', False)",
                {},
            )

    def test_missing_environment_keys_preserve_get_defaults(self) -> None:
        self.assertEqual(
            scalar_environment(
                {}, 'def build(env):\n    return env.get("optional", True)'
            ),
            {},
        )

    def test_module_value_paths_are_repository_relative(self) -> None:
        root = Path("/engine/source")
        self.assertEqual(
            normalize_value({"custom": "/engine/source/_custom_modules/demo"}, root),
            {"custom": "_custom_modules/demo"},
        )

    def test_shader_dependencies_follow_relative_and_root_includes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shaders").mkdir()
            (root / "thirdparty").mkdir()
            (root / "shaders/main.glsl").write_text(
                '#include "common.inc"\n#include "thirdparty/shared.h"'
            )
            (root / "shaders/common.inc").write_text("")
            (root / "thirdparty/shared.h").write_text("")
            self.assertEqual(
                include_closure(root, ["shaders/main.glsl"]),
                {"shaders/main.glsl", "shaders/common.inc", "thirdparty/shared.h"},
            )


if __name__ == "__main__":
    unittest.main()

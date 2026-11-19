"""Run the pinned upstream godot-cpp generator as a hermetic Bazel action."""

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_module(path: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", required=True)
    parser.add_argument("--api", required=True)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--bits", choices=["32", "64"], default="64")
    parser.add_argument("--precision", choices=["single", "double"], default="single")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--profile-generator")
    args = parser.parse_args()
    # The pinned upstream generator imports its sibling interface generator.
    # Both files are explicit action inputs.
    sys.path.insert(0, str(Path(args.generator).resolve().parent))
    generator = load_module(args.generator, "godot_cpp_binding_generator")
    output = Path(args.output_root)
    output.mkdir(parents=True, exist_ok=True)
    if args.profile:
        profile = load_module(args.profile_generator, "godot_cpp_build_profile")
        api = profile.generate_trimmed_api(args.api, args.profile)
        generator._generate_bindings(
            api, args.api, args.interface, True, args.bits, args.precision, str(output)
        )
    else:
        generator.generate_bindings(
            args.api, args.interface, True, args.bits, args.precision, str(output)
        )


if __name__ == "__main__":
    main()

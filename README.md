# Autoload

[![CI](https://github.com/autoload-dev/autoload/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/autoload-dev/autoload/actions/workflows/ci.yml)
[![License: MPL 2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](LICENSE)

Tooling and support for the [Godot](https://godotengine.org) ecosystem. Each component lives
in its own directory and is released on its own:

| Component | What it is |
| --- | --- |
| [rules_godot](rules_godot/README.md) | Bazel rules for building, testing and packaging Godot games, `autoload_rules_godot` |
| [Add-ons](addons/README.md) | Godot add-ons with their native SDKs, one Bazel module each, `autoload_<module>` |

The repository root holds only what the components share: the tooling in `tools/`, the CI in
`.github/`, the task and hook configuration in `mise.toml` and `hk.pkl`, and the maintainer
documentation in `docs/`.

## Contributing

Issues and pull requests are welcome. See the [repository instructions](AGENTS.md) for
working conventions and verification.

## License

Autoload is licensed under the [Mozilla Public License 2.0](LICENSE).

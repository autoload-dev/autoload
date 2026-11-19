# Vendored release

An add-on declared from a Sentry-shaped release directory, kept as upstream ships it: its
scripts, a descriptor of its own and prebuilt libraries per operating system under `bin/`.
The add-on selects the scripts as its runtime part; its extension takes the prebuilt library
of the configured operating system, and rules_godot writes the descriptor packs list.

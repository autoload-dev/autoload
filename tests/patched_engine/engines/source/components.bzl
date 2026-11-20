"""Consumer-owned assembly of registration sets of runtime components from shared payloads."""

load("@autoload_rules_godot//godot/engine:defs.bzl", "godot_runtime_component")

def desktop_runtimes(name, payloads, version, origin = ""):
    """
    Declare one registrable runtime component per desktop slot.

    Args:
        name: Prefix of the components, named <name>_<platform>_<cpu>_<variant>.
        payloads: Dictionary of "<platform>/<cpu>/<variant>" slot keys to runtime payload labels.
        version: The payloads' Godot version.
        origin: Human-readable origin recorded in each component's provenance.
    """
    for slot, payload in payloads.items():
        platform, cpu, variant = slot.split("/")
        godot_runtime_component(
            name = "%s_%s_%s_%s" % (name, platform, cpu, variant),
            cpu = cpu,
            origin = origin,
            platform = platform,
            runtime = payload,
            tags = ["manual"],
            variant = variant,
            version = version,
        )

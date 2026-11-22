"""Read Godot export preset options, which godot_pack holds as Godot literals."""

visibility(["//godot/..."])

_FIELDS = ["key", "owner", "authored", "placement", "when", "derive"]
_OPERANDS = {
    "constant": ["value"],
    "first_cpu": [],
    "cpu_member": ["cpu"],
    "application_value": ["source"],
    "application_enum": ["source", "choices"],
    "android_sdk": ["sdk"],
}

def _policy_error(version, operating_system, key, message):
    fail("Godot %s / %s / %s: %s" % (version, operating_system, key, message))

def _validate_policy(profile, operating_system, version):
    rows = profile.get("owned_export_options", {}).get(operating_system)
    if type(rows) != "list":
        _policy_error(version, operating_system, "<policy>", "expected an owned option row list")
    seen = {}
    rejected = dict(profile["rejected_export_options"].get(operating_system, {}))
    owners = profile["option_owners"]
    for row in rows:
        key = row.get("key", "<missing>") if type(row) == "dict" else "<row>"
        if type(row) != "dict" or any([field not in row for field in _FIELDS]):
            _policy_error(version, operating_system, key, "missing required policy fields")
        if any([type(row[field]) != "string" or not row[field] for field in _FIELDS]):
            _policy_error(version, operating_system, key, "policy fields must be nonempty strings")
        if key in seen:
            _policy_error(version, operating_system, key, "duplicate owned option")
        seen[key] = True
        if row["owner"] not in owners:
            _policy_error(version, operating_system, key, "unknown diagnostic owner")
        if (row["authored"] not in ["reject", "match", "live"] or
            row["placement"] not in ["pack", "preset", "prelude"]):
            _policy_error(version, operating_system, key, "unknown authored mode or placement")
        if row["when"] not in ["always", "application_identity", "macos_application", "ios_application", "android_application"]:
            _policy_error(version, operating_system, key, "unknown applicability guard")
        operation = row["derive"]
        if operation not in _OPERANDS:
            _policy_error(version, operating_system, key, "unknown derivation")
        operands = _OPERANDS[operation]
        allowed = _FIELDS + operands + ["exception"]
        if (any([field not in row for field in operands]) or
            any([field not in allowed for field in row])):
            _policy_error(version, operating_system, key, "missing or unexpected operation operands")
        if "exception" in row and (type(row["exception"]) != "string" or not row["exception"].strip()):
            _policy_error(version, operating_system, key, "exception must document its reason and removal condition")
        if row["authored"] == "match" and row["placement"] != "pack":
            _policy_error(version, operating_system, key, "matched mirrors must be pack values")
        if row["authored"] == "live" and (
            operating_system != "macos" or
            key != "binary_format/embed_pck" or
            operation != "constant" or
            row["placement"] != "prelude" or
            "exception" not in row
        ):
            _policy_error(version, operating_system, key, "a live derived value requires a documented prelude exception")
        if operation in ["first_cpu", "cpu_member"] and row["placement"] == "pack":
            _policy_error(version, operating_system, key, "derived CPU values cannot be pack mirrors")
        if operation == "constant" and type(row["value"]) not in ["bool", "int", "string"]:
            _policy_error(version, operating_system, key, "constant must be a typed scalar")
        if operation == "first_cpu" and operating_system not in ["linux", "macos"]:
            _policy_error(version, operating_system, key, "first_cpu requires a desktop exporter")
        if operation == "cpu_member":
            cpus = {"android": profile["android"]["abis"], "ios": profile["ios"]["cpus"]}.get(operating_system, [])
            if type(row["cpu"]) != "string" or row["cpu"] not in cpus:
                _policy_error(version, operating_system, key, "cpu must name a profile CPU tag")
        if operation == "application_value" and row["source"] not in ["application_id", "macos_minimum_os_version", "ios_minimum_os_version"]:
            _policy_error(version, operating_system, key, "unsupported application context value")
        if operation == "application_enum":
            choices = row["choices"]
            if (row["source"] != "ios_families" or
                type(choices) != "dict" or
                any([type(choice) != "string" for choice in choices]) or
                sorted(choices) != ["ipad", "ipad,iphone", "iphone"] or
                any([type(value) != "int" for value in choices.values()])):
                _policy_error(version, operating_system, key, "expected normalized iOS family choices with integer values")
        if operation == "android_sdk" and (operating_system != "android" or row["sdk"] not in ["min", "target"]):
            _policy_error(version, operating_system, key, "a derived SDK value requires android and min or target")
        if key in rejected:
            _policy_error(version, operating_system, key, "overlap with the rejected export options")
        if row["authored"] == "reject":
            rejected[key] = row["owner"]
    return rows, rejected

def _active(guard, application_values):
    if guard == "application_identity":
        return bool(application_values.get("application_id", ""))
    if guard == "macos_application":
        return "macos_minimum_os_version" in application_values
    if guard == "ios_application":
        return "ios_families" in application_values
    if guard == "android_application":
        return "android_min_sdk_version" in application_values
    return True

def _application_value(application_values, source, expected_type, version, operating_system, key):
    if source not in application_values or type(application_values[source]) != expected_type:
        _policy_error(version, operating_system, key, "missing or invalid application context value " + source)
    return application_values[source]

def _derive(row, context, profile, version):
    operation = row["derive"]
    application_values = context.application_context
    operating_system = context.operating_system
    key = row["key"]
    if operation == "constant":
        return row["value"]
    if operation == "first_cpu":
        if len(context.cpus) != 1:
            _policy_error(version, operating_system, key, "desktop CPU selection must be a singleton")
        return context.cpus[0]
    if operation == "cpu_member":
        return row["cpu"] in context.cpus
    if operation == "application_value":
        return _application_value(application_values, row["source"], "string", version, operating_system, key)
    if operation == "application_enum":
        families = _application_value(application_values, row["source"], "list", version, operating_system, key)
        if any([type(family) != "string" for family in families]):
            _policy_error(version, operating_system, key, "invalid iOS family set")
        normalized = ",".join(sorted(families))
        if normalized not in row["choices"]:
            _policy_error(version, operating_system, key, "invalid iOS family set")
        return row["choices"][normalized]
    minimum = _application_value(application_values, "android_min_sdk_version", "int", version, operating_system, key)
    target = _application_value(application_values, "android_target_sdk_version", "int", version, operating_system, key)
    minimum = minimum or int(profile["android"]["min_sdk"])
    target = target or int(profile["android"]["target_sdk"])
    if target < minimum or minimum < int(profile["android"]["min_sdk"]):
        _policy_error(version, operating_system, key, "Android target SDK must be >= minimum SDK, and minimum must support the selected engine")
    return str(minimum if row["sdk"] == "min" else target)

def resolve_export_options(authored, context, profile, version):
    """
    Resolve the owned export options of the engine profile into the option sets of a pack.

    Args:
        authored: Original option-to-Godot-literal map.
        context: Configured context with the operating system, CPUs and application context.
        profile: Selected engine profile, including owned and rejected options.
        version: Editor version for policy diagnostics.

    Returns:
        Fresh pack_options, preset_options, preset_prelude and rejected_options maps.
    """
    rows, rejected = _validate_policy(profile, context.operating_system, version)
    validate_supported_options(authored, rejected, profile["option_owners"])
    option_sets = {"pack": dict(authored), "preset": {}, "prelude": {}}
    for row in rows:
        if not _active(row["when"], context.application_context):
            continue
        value = _derive(row, context, profile, version)
        key = row["key"]
        literal = json.encode(value)
        if (row["authored"] == "match" and key in authored and
            json.decode(authored[key]) != value):
            _policy_error(
                version,
                context.operating_system,
                key,
                "authored %s conflicts with authoritative godot_app value %s; %s owns it: %s" % (
                    authored[key],
                    literal,
                    row["owner"],
                    profile["option_owners"][row["owner"]],
                ),
            )
        option_sets[row["placement"]][key] = literal
    return struct(
        pack_options = option_sets["pack"],
        preset_options = option_sets["pack"] | option_sets["preset"],
        preset_prelude = option_sets["prelude"],
        rejected_options = rejected,
    )

def string_option(options, name):
    """
    Return a string export option the pack sets, or an empty string.

    Analysis reads only the options that decide which files a rule declares;
    Godot reports every other option to the build tools.

    Args:
        options: GodotPackInfo.export_options.
        name: Option name, such as application/liquid_glass_icon.

    Returns:
        The option's string.
    """
    literal = options.get(name, '""').strip()
    if not literal.startswith('"'):
        fail("Export option %s must be a quoted string, got %r" % (name, literal))

    # Godot keeps line breaks and tabs of multiline text unescaped.
    for character, escape in [("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")]:
        literal = literal.replace(character, escape)
    return json.decode(literal)

def validate_supported_options(options, rejected, owners):
    """
    Reject unsupported or Bazel-owned authored options before executing Godot.

    Args:
        options: Authored option-to-literal map.
        rejected: The selected exporter's rejected options, by owner ID.
        owners: Consumer-facing alternatives for the owner IDs Bazel provides.
    """
    for key in options:
        if key in rejected:
            owner = rejected[key]
            fail("Export option %s is %s; %s owns it: %s" % (
                key,
                "bazel-owned" if owner in owners else "unsupported",
                owner,
                owners.get(owner, "unsupported in this workflow"),
            ))

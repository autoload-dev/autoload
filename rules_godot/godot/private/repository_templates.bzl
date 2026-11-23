"""Fill text templates in repository rules, which have no template actions."""

visibility("//godot/...")

def fill_template(repository_ctx, template, substitutions):
    """
    Return a template file's text with each substitution key replaced.

    Use it for blocks a repository repeats or omits; expand a whole file with
    repository_ctx.template instead.

    Args:
        repository_ctx: Repository rule context.
        template: Label of the template file.
        substitutions: Placeholder such as "{NAME}" to its replacement text.

    Returns:
        The filled text, without the template file's final newline.
    """
    text = repository_ctx.read(template).removesuffix("\n")
    for key, value in substitutions.items():
        text = text.replace(key, value)
    return text

def starlark_list(items, indent = ""):
    """
    Render values as a Starlark list the way buildifier formats BUILD files.

    Args:
        items: Values with a Starlark repr, such as strings.
        indent: Indentation of the line the list starts on.

    Returns:
        One line for up to one item, otherwise one item per line.
    """
    if len(items) < 2:
        return repr(items)
    return "[\n%s%s]" % (
        "".join(["%s    %s,\n" % (indent, repr(item)) for item in items]),
        indent,
    )

def starlark_dict(entries, indent = ""):
    """
    Render a dictionary as a Starlark dict with one entry per line.

    Args:
        entries: Keys and values with a Starlark repr, such as strings.
        indent: Indentation of the line the dict starts on.

    Returns:
        The dict literal.
    """
    return "{\n%s%s}" % (
        "".join([
            "%s    %s: %s,\n" % (indent, repr(key), repr(value))
            for key, value in entries.items()
        ]),
        indent,
    )

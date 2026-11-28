"""
Test that each third-party archive's URLs and package URL carry its version.

Shared file of the add-on modules with third-party archives (tools/addons/new.py).
"""

def _quote(text):
    return "'" + text.replace("'", "'\\''") + "'"

def _archive_versions_test_impl(ctx):
    script = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(script, is_executable = True, content = "#!/bin/sh\n" + "".join([
        "echo %s >&2\n" % _quote(failure)
        for failure in ctx.attr.failures
    ]) + "exit %d\n" % (1 if ctx.attr.failures else 0))
    return [DefaultInfo(executable = script)]

_archive_versions_test = rule(
    implementation = _archive_versions_test_impl,
    attrs = {"failures": attr.string_list()},
    test = True,
)

def archive_versions_test(name, archives, **kwargs):
    """
    Test that the URLs each archive is fetched from and its package URL name its version.

    Args:
        name: Name of the test.
        archives: The module's archives, `github_archive` structs by their repositories'
            names.
        **kwargs: Attributes of the test, such as size.
    """
    failures = []
    for repository, archive in archives.items():
        failures += [
            "%s: the URL %s does not carry the version %s" % (
                repository,
                url,
                archive.version,
            )
            for url in archive.attrs["urls"]
            if archive.version not in url
        ]
        if not archive.purl.endswith("@" + archive.version):
            failures.append("%s: the package URL %s does not carry the version %s" % (
                repository,
                archive.purl,
                archive.version,
            ))
    _archive_versions_test(name = name, failures = failures, **kwargs)

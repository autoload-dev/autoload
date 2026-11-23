"""Mocks of module_ctx, repository_ctx and File for Starlark unit tests.

Module extensions and repository rules export their logic with a context parameter and a
`_fail` parameter; a test passes these mocks and collects errors instead of stopping.
"""

visibility([
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/tests/...",
])

def _tag(**attrs):
    """A module-extension tag with the given attributes."""
    return struct(**attrs)

def _module(name = "consumer", *, is_root = False, version = "", **tags):
    """A module of module_ctx.modules; each keyword names a tag class and lists its tags."""
    return struct(name = name, is_root = is_root, version = version, tags = struct(**tags))

def _module_ctx(modules, *, os_name = "linux", arch = "amd64", environ = {}):
    """A module_ctx over the given modules."""
    return struct(
        modules = modules,
        os = struct(name = os_name, arch = arch, environ = environ),
        getenv = lambda name, default = None: environ.get(name, default),
        extension_metadata = lambda **kwargs: struct(**kwargs),
    )

def _record(calls, method, **kwargs):
    calls.append(struct(method = method, **kwargs))

def _key(value):
    """The string a mock keys a label, string or mock path by."""
    return value.path if type(value) == "struct" else str(value)

def _path_struct(path, exists, readdir):
    return struct(
        path = path,
        exists = exists,
        basename = path.rpartition("/")[2],
        dirname = path.rpartition("/")[0],
        readdir = readdir,
    )

def _path(path, *, exists = True, children = []):
    """
    A repository path with the fields the ruleset reads.

    Args:
        path: The path as a string or label.
        exists: Whether the path exists.
        children: Names of the entries `readdir()` lists.

    Returns:
        A struct with `path`, `exists`, `basename`, `dirname` (strings and a bool) and
        `readdir()`.
    """
    key = str(path)
    return _path_struct(key, exists, lambda: [_path(key + "/" + child) for child in children])

def _tree_path(entries, path):
    """A path over a static tree: it exists when an entry is it or lies below it."""
    key = _key(path)
    prefix = key + "/"
    children = sorted({
        entry[len(prefix):].partition("/")[0]: None
        for entry in entries
        if entry.startswith(prefix)
    }.keys())
    return _path_struct(
        key,
        key in entries or bool(children),
        lambda: [_tree_path(entries, prefix + child) for child in children],
    )

def _getenv(calls, environ, variable, default):
    calls.append(struct(method = "getenv", variable = variable))
    return environ.get(variable, default)

def _execute(calls, results, args, kwargs):
    arguments = [str(argument) for argument in args]
    calls.append(struct(method = "execute", args = arguments, kwargs = kwargs))
    for prefix, result in results.items():
        if " ".join(arguments).startswith(prefix):
            return struct(
                return_code = result.get("return_code", 0),
                stdout = result.get("stdout", ""),
                stderr = result.get("stderr", ""),
            )
    return struct(return_code = 0, stdout = "", stderr = "")

def _download(calls, method, kwargs):
    calls.append(struct(method = method, **kwargs))
    return struct(
        success = True,
        sha256 = kwargs.get("sha256", ""),
        integrity = kwargs.get("integrity", ""),
    )

def _read(files, path):
    key = _key(path)
    if key not in files:
        fail("mock repository_ctx has no file %r; known: %s" % (key, sorted(files.keys())))
    return files[key]

def _repository_ctx(
        *,
        attr = {},
        name = "repository",
        files = {},
        which = {},
        execute = {},
        environ = {},
        os_name = "linux",
        path = None,
        tree = None):
    """A repository_ctx that records its side effects in `calls`.

    Args:
        attr: Attribute values, read as `ctx.attr`.
        name: The repository's name.
        files: Contents that `read` returns, keyed by the string of the path.
        which: Tool paths that `which` returns, keyed by tool name; absent tools return None.
        execute: Results of `execute`, keyed by a prefix of the space-joined arguments, each a
            dict of `return_code`, `stdout` and `stderr`. Other commands succeed silently.
        environ: Environment variables that `getenv` and `os.environ` see.
        os_name: The host operating system name.
        path: Maps a label or string to a path. Defaults to `str`, the form command lines
            take, unless `tree` is given.
        tree: Paths, as strings, of a static repository tree. With it, `path` returns
            `mocks.path` structs whose `exists` and `readdir()` follow the tree and the
            `files` keys; a path exists when an entry is it or lies below it.

    Returns:
        A struct with the repository_ctx methods the ruleset uses and a `calls` list.
    """
    calls = []
    if path:
        to_path = path
    elif tree != None:
        entries = list(tree) + files.keys()
        to_path = lambda value: _tree_path(entries, value)
    else:
        to_path = lambda value: str(value)
    return struct(
        calls = calls,
        attr = struct(**attr),
        name = name,
        os = struct(name = os_name, environ = environ),
        path = to_path,
        read = lambda path, **_: _read(files, path),
        which = lambda tool: which.get(tool),
        getenv = lambda variable, default = None: _getenv(calls, environ, variable, default),
        execute = lambda args, **kwargs: _execute(calls, execute, args, kwargs),
        file = lambda path, content = "", executable = True, **kwargs: _record(
            calls,
            "file",
            path = _key(path),
            content = content,
            executable = executable,
        ),
        template = lambda path, template, substitutions = {}, executable = True, **kwargs: _record(
            calls,
            "template",
            path = _key(path),
            template = str(template),
            substitutions = substitutions,
            executable = executable,
        ),
        symlink = lambda target, link_name: _record(calls, "symlink", target = _key(target), link_name = _key(link_name)),
        delete = lambda path: _record(calls, "delete", path = _key(path)),
        watch = lambda path: _record(calls, "watch", path = _key(path)),
        watch_tree = lambda path: _record(calls, "watch_tree", path = _key(path)),
        download = lambda **kwargs: _download(calls, "download", kwargs),
        download_and_extract = lambda **kwargs: _download(calls, "download_and_extract", kwargs),
        extract = lambda archive, output = "", stripPrefix = "", **kwargs: _record(
            calls,
            "extract",
            archive = _key(archive),
            output = _key(output),
            stripPrefix = stripPrefix,
            **kwargs
        ),
        report_progress = lambda status = "": None,
        repo_metadata = lambda **kwargs: struct(**kwargs),
    )

def _file(path, *, is_source = True):
    """A File with the fields tests read."""
    basename = path.rpartition("/")[2]
    return struct(
        path = path,
        short_path = path,
        basename = basename,
        dirname = path.rpartition("/")[0],
        extension = basename.rpartition(".")[2] if "." in basename else "",
        is_source = is_source,
    )

def _calls(ctx, method):
    """The recorded calls of one method."""
    return [call for call in ctx.calls if call.method == method]

def _errors():
    """A list and a `_fail` replacement that appends the message to it."""
    errors = []
    return errors, lambda *parts: errors.append(" ".join([str(part) for part in parts]))

mocks = struct(
    tag = _tag,
    module = _module,
    module_ctx = _module_ctx,
    repository_ctx = _repository_ctx,
    path = _path,
    file = _file,
    calls = _calls,
    errors = _errors,
)

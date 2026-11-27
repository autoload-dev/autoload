"""
Open a declared project in the Godot editor on a view that links into the checkout.

Sections: Layout, Placement, Reports, Editor session.
"""

import argparse
import contextlib
import dataclasses
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path, PurePosixPath

from tools.checkout.metadata_sync import place_metadata
from tools.inputs.originals import Original, executable, open_original, same_content
from tools.inputs.runfiles import report, runfile_locator
from tools.project.config import write_back
from tools.resources.files import (
    DIRECTORY_MARKERS,
    EXTENSION_LIST,
    is_hidden,
    is_sidecar_named,
    sidecar_source,
)
from tools.staging.files import extension_list, generated_files, validate_staged_paths

# The runner's own state inside a view, beside Godot's.
STATE = ".godot/rules_godot"


class EditorError(RuntimeError):
    """A view that cannot be prepared, with the reason for the user."""


# ==== Layout ==================================================================


def _ancestors(path: str) -> Iterator[str]:
    """The directories a resource path lies in, outermost first."""
    parts = path.split("/")
    for index in range(1, len(parts)):
        yield "/".join(parts[:index])


def linked_parent(path: str, linked: dict[str, str]) -> str | None:
    """The linked directory a resource path lies in, if any."""
    return next(
        (directory for directory in _ancestors(path) if directory in linked), None
    )


def _link_target(directory: str, path: str, source: str) -> str | None:
    """The workspace directory that holds source as directory holds path, if any."""
    rest = path[len(directory) + 1 :]
    # The workspace root itself contains the views and is never linked.
    return source[: -len(rest) - 1] if source.endswith("/" + rest) else None


def _link_candidates(checkout: dict[str, str], owned: set[str]) -> dict[str, str | None]:
    """Each project directory to its one workspace directory, or None if it has none."""
    candidates: dict[str, str | None] = {}
    for path, source in checkout.items():
        for directory in _ancestors(path):
            target = _link_target(directory, path, source)
            if candidates.setdefault(directory, target) != target:
                candidates[directory] = None
    for path in owned:
        candidates.update(dict.fromkeys(_ancestors(path)))
    return candidates


def link_directories(checkout: dict[str, str], owned: set[str]) -> dict[str, str]:
    """
    Choose the project directories a view links as a whole.

    A directory qualifies when every checkout file below it lies in one checkout
    directory at the same relative path and no other file of the view does; the
    highest qualifying directory is linked. The project root never is, since it
    holds the view's project.godot and Godot's state.

    Args:
        checkout: Resource paths of checkout files to their workspace paths.
        owned: Resource paths of files the view copies from the build.

    Returns:
        Linked project directories to their workspace directories.
    """
    candidates = _link_candidates(checkout, owned)
    linked: dict[str, str] = {}
    for directory in sorted(candidates, key=lambda value: value.count("/")):
        target = candidates[directory]
        if target and linked_parent(directory, linked) is None:
            linked[directory] = target
    return linked


@dataclasses.dataclass
class Layout:
    """What a view contains, by resource path."""

    # Symbolic links to workspace directories.
    directories: dict[str, str]
    # Symbolic links to checkout files outside those directories.
    links: dict[str, str]
    # Read-only copies of generated and external project files.
    copies: dict[str, Original]
    # Godot's state and generated sidecars, which the editor may rewrite.
    caches: dict[str, Original]


def plan_layout(
    checkout: dict[str, str],
    copies: dict[str, Original],
    generated: dict[str, Original],
    sidecars: dict[str, str] | None = None,
) -> Layout:
    """
    Lay out a view.

    Args:
        checkout: Resource paths of checkout files to their workspace paths.
        copies: Resource paths of generated and external files to their bytes.
        generated: Import results and Godot's caches by resource path.
        sidecars: Resource paths of undeclared sidecars that exist in the
            checkout to their workspace paths; the view links them, so editing
            their import settings changes the checkout.

    Returns:
        The view's layout.
    """
    validate_staged_paths({path: "" for path in [*checkout, *copies]})
    directories = link_directories(checkout, set(copies))
    links = {
        path: source
        for path, source in {**checkout, **(sidecars or {})}.items()
        if linked_parent(path, directories) is None
    }
    # Declared files and sidecars in the checkout take precedence. A linked
    # directory shows the checkout's own files only.
    caches = {
        path: original
        for path, original in generated.items()
        if path not in links
        and path not in copies
        and linked_parent(path, directories) is None
    }
    # Load extensions before the first scan, as staged projects do.
    extensions = extension_list([*checkout, *copies])
    if extensions:
        caches[EXTENSION_LIST] = extensions
    return Layout(directories, links, copies, caches)


# ==== Placement ===============================================================


def _stamp(path: Path) -> str:
    """
    Identify a file's state by its inode, size and modification time, as Git's index does.

    A rebuilt output is a new file; the inode tells it apart from its predecessor
    even within one tick of the file system's clock.
    """
    status = path.stat()
    return f"{path}:{status.st_ino}:{status.st_size}:{status.st_mtime_ns}"


def _origin(original: Original) -> str:
    """Identify the bytes of an original without reading a file's content."""
    if isinstance(original, bytes):
        return hashlib.sha256(original).hexdigest()
    if isinstance(original, Path):
        return _stamp(original)
    archive, member = original
    return f"{_stamp(archive)}:{member.name}"


def place_file(
    path: Path, original: Original, mode: int, known: list | None = None
) -> list:
    """
    Place original's bytes at path, unless they are there already.

    Args:
        path: Where the bytes belong.
        original: The bytes.
        mode: The file's permissions.
        known: The fingerprint this returned when it last placed path; a file
            that still matches it is not read again.

    Returns:
        The fingerprint of the placed file.
    """
    origin = _origin(original)
    if path.is_symlink():
        path.unlink()
    elif path.is_file():
        status = path.stat()
        fingerprint = [origin, status.st_size, status.st_mtime_ns]
        if known == fingerprint:
            # The bytes are placed; the mode can still change, as when an original
            # becomes executable. chmod keeps the modification time of the fingerprint.
            path.chmod(mode)
            return fingerprint
        if not same_content(path, original):
            path.unlink()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open_original(original) as data, path.open("wb") as copy:
            shutil.copyfileobj(data, copy)
    path.chmod(mode)
    status = path.stat()
    return [origin, status.st_size, status.st_mtime_ns]


def _remove_entries(entries: Iterable[Path], placed: Callable[[Path], bool]) -> set:
    """Remove the entries that placed accepts, in order; return their directories."""
    emptied = set()
    for entry in entries:
        if placed(entry):
            entry.unlink()
            emptied.add(entry.parent)
    return emptied


def _is_empty_directory(directory: Path) -> bool:
    return directory.is_dir() and not any(directory.iterdir())


def _remove_empty(view: Path, emptied: set[Path]) -> None:
    """
    Remove the directories that removing entries left empty, and their empty parents.

    So a linked directory can take their place; directories the editor created are
    left alone.
    """
    for directory in sorted(emptied, key=lambda value: len(value.parts), reverse=True):
        while directory != view and _is_empty_directory(directory):
            directory.rmdir()
            directory = directory.parent


def _files_below(directory: Path) -> list[str]:
    return sorted(
        str(PurePosixPath(Path(root).relative_to(directory)) / name)
        for root, _, names in os.walk(directory)
        for name in names
    )


def _conflict(entry: Path, source: Path, path: str, target: str) -> str | None:
    """Why what the view holds at res://path cannot give way to a link, if it cannot."""
    if entry.is_dir():
        created = ", ".join(f"res://{path}/{name}" for name in _files_below(entry))
        return (
            f"res://{path} now links to {target}, but the view holds files "
            f"created there: {created}; move them to {target} or delete them"
        )
    if entry.exists() and not same_content(entry, source):
        return (
            f"res://{path} was created in the view and differs from {target}; "
            "move or delete it"
        )
    return None


def _clear_for_link(entry: Path, source: Path, path: str, target: str) -> bool:
    """
    Make way for a link to source at entry, the view's res://path.

    Returns:
        Whether the link is there already.
    """
    if entry.is_symlink():
        if Path(os.readlink(entry)) == source:
            return True
    elif message := _conflict(entry, source, path, target):
        raise EditorError(message)
    entry.unlink(missing_ok=True)
    return False


def _place_link(view: Path, workspace: Path, path: str, target: str) -> None:
    """Link the view's res://path to the workspace's target."""
    entry = view / path
    source = workspace / target
    if not source.exists():
        raise EditorError(f"{target} is declared in the project but missing")
    if _clear_for_link(entry, source, path, target):
        return
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.symlink_to(source)


def _file_mode(path: str, original: Original, layout: Layout) -> int:
    """The permissions of a file the view copies: copies are read-only."""
    mode = 0o444 if path in layout.copies else 0o644
    return mode | (0o111 if executable(original) else 0)


def sync(view: Path, workspace: Path, layout: Layout, record: dict) -> dict:
    """
    Bring a view to layout; keep what the editor added and Godot's other state.

    Args:
        view: The view's root directory.
        workspace: The checkout's root directory.
        layout: What the view contains.
        record: What the previous sync placed, as it returned it; empty for a new
            view.

    Returns:
        What this sync placed.
    """
    links = {**layout.directories, **layout.links}
    files = {**layout.copies, **layout.caches}
    known = record.get("files", {})
    stale_links = (
        view / path
        for path, target in record.get("links", {}).items()
        if links.get(path) != target
    )
    emptied = _remove_entries(stale_links, Path.is_symlink)
    stale_files = (view / path for path in known if path not in files)
    emptied |= _remove_entries(stale_files, Path.is_file)
    _remove_empty(view, emptied)
    for path, target in sorted(links.items()):
        _place_link(view, workspace, path, target)
    placed = {
        path: place_file(
            view / path,
            original,
            _file_mode(path, original, layout),
            known.get(path),
        )
        for path, original in files.items()
    }
    return {"links": links, "files": placed}


# ==== Reports =================================================================


# Files of Bazel packages, which Godot does not show, in linked directories.
_BAZEL_FILES = {"BUILD", "BUILD.bazel", "REPO.bazel", "MODULE.bazel", "WORKSPACE"}


def _move_hint(path: str, sources: dict[str, str]) -> str:
    """Where a view file belongs: the checkout directory of its siblings, if any."""
    directory = sources.get(str(PurePosixPath(path).parent))
    return f" to {directory}/" if directory else ""


def source_directories(checkout: dict[str, str]) -> dict[str, str]:
    """Project directories to the checkout directory their first file comes from."""
    directories: dict[str, str] = {}
    for path, source in sorted(checkout.items()):
        directories.setdefault(
            str(PurePosixPath(path).parent), str(PurePosixPath(source).parent)
        )
    return directories


def _view_entries(view: Path) -> Iterator[tuple[str, Path]]:
    """The files and directory links in a view by resource path, but Godot's state."""
    for root, directories, names in os.walk(view):
        relative = Path(root).relative_to(view)
        if relative == Path("."):
            directories[:] = [name for name in directories if name != ".godot"]
            names = [name for name in names if name != "project.godot"]
        links = [name for name in directories if (Path(root) / name).is_symlink()]
        for name in sorted(names + links):
            yield str(PurePosixPath(relative) / name), Path(root) / name


def _unplaced(path: str, entry: Path, sources: dict[str, str]) -> str:
    """Describe a file or link in the view that its layout did not place."""
    if entry.is_symlink():
        return (
            f"res://{path} links to {os.readlink(entry)} and was moved in the "
            "editor; the checkout keeps it at its declared path"
        )
    return (
        f"res://{path} exists only in the view; move it"
        f"{_move_hint(path, sources)} and declare it"
    )


def view_only(view: Path, layout: Layout, sources: dict[str, str]) -> list[str]:
    """Describe files and links in the view that its layout did not place."""
    placed = {*layout.directories, *layout.links, *layout.copies, *layout.caches}
    messages = [
        _unplaced(path, entry, sources)
        for path, entry in _view_entries(view)
        if path not in placed and not entry.name.startswith(".")
    ]
    # Godot replaces its own state as it pleases.
    messages += [
        f"res://{path} was moved or deleted in the editor"
        for path in sorted(placed)
        if not path.startswith(".godot/") and not os.path.lexists(view / path)
    ]
    return messages


def changed_sidecars(
    view: Path, layout: Layout, record: dict, sources: dict[str, str]
) -> list[str]:
    """Describe the generated sidecars in the view that the editor changed."""
    messages = []
    for path, original in sorted(layout.caches.items()):
        entry = view / path
        if not is_sidecar_named(path) or not entry.is_file():
            continue
        status = entry.stat()
        if record["files"][path][1:] == [status.st_size, status.st_mtime_ns]:
            continue
        if not same_content(entry, original):
            messages.append(
                f"the editor changed the generated res://{path}; to keep it, copy "
                f"it{_move_hint(path, sources)} and declare it with its file"
            )
    return messages


def _is_ignored(relative: PurePosixPath, names: list[str]) -> bool:
    """Godot's ignore rule (tools/resources/files.py): the project's root is never skipped."""
    return str(relative) != "." and any(name in names for name in DIRECTORY_MARKERS)


def _scanned_directories(
    root: Path, directory: str
) -> Iterator[tuple[Path, PurePosixPath, list[str]]]:
    """Each directory Godot scans below a linked one: its path, resource path and files."""
    for current, directories, names in os.walk(root):
        relative = PurePosixPath(directory) / Path(current).relative_to(root)
        if _is_ignored(relative, names):
            directories[:] = []
            continue
        directories[:] = [name for name in directories if not is_hidden(name)]
        yield Path(current), relative, names


def _is_bazel_file(name: str) -> bool:
    return name in _BAZEL_FILES or name.endswith(".bzl")


def _beside_source(current: Path, name: str) -> bool:
    """Whether a file is a sidecar whose source file lies beside it."""
    source = sidecar_source(name)
    return source is not None and (current / source).exists()


def _needs_no_declaration(current: Path, name: str) -> bool:
    """Whether Godot does not show a file, or the view generates it for its source."""
    if is_hidden(name) or _is_bazel_file(name):
        return True
    return _beside_source(current, name)


def _undeclared_below(
    root: Path, directory: str, checkout: dict[str, str]
) -> Iterator[str]:
    """Resource paths of the files below a linked directory that the project lacks."""
    for current, relative, names in _scanned_directories(root, directory):
        for name in sorted(names):
            path = str(relative / name)
            if path not in checkout and not _needs_no_declaration(current, name):
                yield path


def undeclared(workspace: Path, layout: Layout, checkout: dict[str, str]) -> list[str]:
    """Resource paths of files in linked directories that the project does not declare."""
    return [
        path
        for directory, target in sorted(layout.directories.items())
        for path in _undeclared_below(workspace / target, directory, checkout)
    ]


# ==== Editor session ==========================================================


_GITIGNORE = Path(__file__).parent / "editor_view.gitignore.tpl"


def reconcile_settings(view: Path, workspace: Path, manifest: dict) -> None:
    """Write editor changes of authored settings back; report the others."""
    baseline_file = view / STATE / "project.godot"
    edited_file = view / "project.godot"
    if not baseline_file.is_file() or not edited_file.is_file():
        return
    baseline = baseline_file.read_text(encoding="utf-8")
    edited = edited_file.read_text(encoding="utf-8")
    if baseline == edited:
        return
    authored_path = manifest["authored_project_file"]
    authored_file = workspace / authored_path if authored_path else None
    # A generated base project.godot takes nothing; the baseline stands in.
    authored = authored_file.read_text(encoding="utf-8") if authored_file else baseline
    result = write_back(authored, baseline, edited, manifest["composed_settings"])
    if authored_file and result.text != authored:
        authored_file.write_text(result.text, encoding="utf-8")
    for setting in result.written:
        report(
            f"wrote {setting} to {authored_path}"
            if authored_file
            else f"{setting} changed, but the project's project.godot is generated"
        )
    for message in result.reported:
        report(message)
    baseline_file.write_text(edited, encoding="utf-8")


def check_ignored(workspace: Path, views: str) -> None:
    """Fail unless Bazel ignores the views, whose links would duplicate packages."""
    ignore = workspace / ".bazelignore"
    if ignore.is_file():
        lines = {line.strip().rstrip("/") for line in ignore.read_text().splitlines()}
        if views in lines:
            return
    repository = workspace / "REPO.bazel"
    if repository.is_file() and f'"{views}"' in repository.read_text():
        return
    raise EditorError(
        f"Add the line {views} to {ignore}: editor views link to package "
        "directories, which `bazel build //...` would otherwise find twice"
    )


@contextlib.contextmanager
def locked(view: Path) -> Iterator[None]:
    """Hold the view for one editor."""
    with (view / STATE / "lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EditorError(f"Another editor is open on {view}") from None
        yield


def wait(process: subprocess.Popen) -> int:
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            # The editor receives the interrupt as well; wait for it to close.
            continue


def _read_record(record_file: Path, label: str, view: Path) -> dict:
    """What the previous sync placed in the view, which must be the project's own."""
    record = json.loads(record_file.read_text()) if record_file.is_file() else {}
    if record and record["label"] != label:
        raise EditorError(f"{view} belongs to {record['label']}")
    return record


def _metadata_sidecars(manifest: dict, runfile: Callable[[str], Path]) -> list[dict]:
    """The sidecars the project's metadata lists."""
    metadata = json.loads(runfile(manifest["metadata"]).read_text(encoding="utf-8"))
    return [sidecar for sidecar in metadata if sidecar["kind"] == "sidecar"]


def _prepare_view(
    manifest: dict, workspace: Path, view: Path, runfile: Callable[[str], Path]
) -> tuple[Layout, dict, list[dict]]:
    """
    Bring the view to the project's layout.

    Returns:
        The layout, what the sync placed, and the sidecars the checkout misses.
    """
    state = view / STATE
    record_file = state / "view.json"
    record = _read_record(record_file, manifest["label"], view)
    # Changes from a session that ended without the runner, if any.
    reconcile_settings(view, workspace, manifest)
    generated = generated_files(manifest, runfile)
    # Before the editor scans the checkout, which writes its own otherwise.
    # The editor saves node IDs and resource UIDs itself; only
    # godot_metadata_sync writes them into the checkout.
    sidecars = _metadata_sidecars(manifest, runfile)
    missing = place_metadata(sidecars, workspace, write=manifest["write_sidecars"])
    layout = plan_layout(
        manifest["checkout"],
        {path: runfile(key) for path, key in manifest["copies"].items()},
        generated,
        {
            sidecar["path"]: sidecar["workspace"]
            for sidecar in sidecars
            if (workspace / sidecar["workspace"]).exists()
        },
    )
    record = sync(view, workspace, layout, record)
    record_file.write_text(
        json.dumps({"label": manifest["label"], **record}, indent=2) + "\n"
    )
    project = runfile(manifest["project_file"])
    place_file(view / "project.godot", project, 0o644)
    place_file(state / "project.godot", project, 0o644)
    return layout, record, missing


def _start_editor(
    manifest: dict, view: Path, extra: list[str], runfile: Callable[[str], Path]
) -> subprocess.Popen:
    """Run the editor on the view with the project's environment."""
    environment = dict(os.environ)
    environment.update(manifest["env"])
    report(f"opening {view}")
    return subprocess.Popen(
        [str(runfile(manifest["editor"])), "--editor", "--path", str(view), *extra],
        cwd=view,
        env=environment,
    )


def _missing_messages(missing: list[dict]) -> list[str]:
    """Describe the sidecars the checkout misses."""
    return [
        f"{sidecar['workspace']} is missing; Godot writes its own when it finds the file"
        for sidecar in missing
    ]


def _undeclared_messages(manifest: dict, workspace: Path, layout: Layout) -> list[str]:
    """Describe the files in linked directories that the project does not declare."""
    return [
        f"res://{path} is in a linked directory but not in {manifest['label']}"
        for path in undeclared(workspace, layout, manifest["checkout"])
    ]


def open_editor(
    manifest: dict,
    workspace: Path,
    extra: list[str],
    runfile: Callable[[str], Path] | None = None,
) -> int:
    """Prepare the view, run the editor on it and carry changes back; return its exit code."""

    runfile = runfile or runfile_locator(manifest["workspace"])
    check_ignored(workspace, manifest["views"])
    place_file(workspace / manifest["views"] / ".gitignore", _GITIGNORE, 0o644)
    view = workspace / manifest["view"]
    (view / STATE).mkdir(parents=True, exist_ok=True)
    with locked(view):
        layout, record, missing = _prepare_view(manifest, workspace, view, runfile)
        process = _start_editor(manifest, view, extra, runfile)
        # Reports come while the editor starts.
        sources = source_directories(manifest["checkout"])
        for message in [
            *_missing_messages(missing),
            *_undeclared_messages(manifest, workspace, layout),
            *view_only(view, layout, sources),
        ]:
            report(message)
        code = wait(process)
        reconcile_settings(view, workspace, manifest)
        for message in [
            *view_only(view, layout, sources),
            *changed_sidecars(view, layout, record, sources),
        ]:
            report(message)
        return code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", required=True, type=Path)
    # Everything after the manifest is the editor's.
    args = parser.parse_args(sys.argv[1:3])
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        report("open the editor with bazel run")
        raise SystemExit(1)
    try:
        code = open_editor(
            json.loads(args.manifest.read_text(encoding="utf-8")),
            Path(workspace),
            sys.argv[3:],
        )
    except (EditorError, OSError, ValueError) as error:
        report(str(error))
        raise SystemExit(1) from None
    raise SystemExit(code)


if __name__ == "__main__":
    main()

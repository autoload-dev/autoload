"""
The staged project of a Godot process: the staged files copied into a project directory,
with the editor plugins and settings of its purpose and the metadata completions.
"""

import contextlib
import shutil
import tempfile
from collections.abc import Collection, Iterable, Iterator, Mapping
from pathlib import Path

from tools.inputs.manifest import resource_path
from tools.inputs.originals import Original, copy_file, executable, open_original
from tools.project.config import compose_project, enable_plugins, enabled_plugins
from tools.staging.files import completed_texts, staged_files


def configure(root: Path, plugins: Iterable[str], settings: Mapping[str, str]) -> None:
    """Enable editor plugins and set settings, such as importers' import settings, in the staged project.godot."""
    if not plugins and not settings:
        return
    project = root / "project.godot"
    text = project.read_text(encoding="utf-8")
    plugins = [*plugins, *enabled_plugins(text)]
    if settings:
        text = compose_project(text, dict(settings), {}, "")
    project.write_text(enable_plugins(text, plugins), encoding="utf-8")


def stage(manifest: dict, root: Path, execroot: Path) -> dict[str, Original]:
    """
    Stage the project; return where each staged file's bytes came from.

    Its editor plugins, such as the importers an import stages, are enabled
    in the staged project.godot, which also takes its settings, such as the import
    settings of those importers. Godot's scans compare against the originals, which hold
    the metadata completions as the staged files do.
    """
    originals: dict[str, Original] = {
        "project.godot": execroot / manifest["project_file"],
        **staged_files(manifest, execroot),
    }
    for relative, original in originals.items():
        destination = root / resource_path(relative)
        if isinstance(original, Path):
            copy_file(original, destination)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open_original(original) as data, destination.open("wb") as copy:
            shutil.copyfileobj(data, copy)
        if executable(original):
            destination.chmod(destination.stat().st_mode | 0o111)
    configure(root, manifest.get("editor_plugins", []), manifest.get("settings", {}))
    return originals


@contextlib.contextmanager
def staged_project(
    manifest: dict, execroot: Path, prefix: str
) -> Iterator[tuple[Path, Path, dict[str, Original]]]:
    """Yield (work, root, originals): a temporary work directory with the staged project."""
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        work = Path(temporary)
        root = work / "project"
        root.mkdir()
        originals = stage(manifest, root, execroot)
        yield work, root, originals


def apply_metadata(
    root: Path, index: dict, kinds: Iterable[str], staged: Collection[str]
) -> dict[str, bytes]:
    """
    Complete the staged text files with the metadata kinds the index lists for them.

    Returns:
        The updated files' bytes by resource path; their sources keep theirs.
    """
    texts = completed_texts(
        index,
        kinds,
        staged,
        lambda path: (root / resource_path(path)).read_text(encoding="utf-8", newline=""),
    )
    for path, text in texts.items():
        (root / resource_path(path)).write_text(text, encoding="utf-8", newline="")
    return {path: text.encode("utf-8") for path, text in texts.items()}

"""Contract tests for hermetic Godot execution and its exit-code outcome."""

import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from unittest import mock

from tools.inputs.runfiles import locate
from tools.pack.pck import write_pck
from tools.source_run.run import ExecutionError, pack_descriptors, run
from tools.tests.stub_program import write_stub_program


def run_manifest(**fields: Any) -> dict[str, Any]:
    """Common fields emitted by the current Bazel run-manifest producer."""
    manifest = {
        "workspace": "",
        "editor": "editor",
        "headless": True,
        "stop_on_error": False,
        "main": "",
        "engine_errors": "fail",
        "env": {},
        "additional_packs": {},
    }
    manifest.update(fields)
    return manifest


def alive(pid: int) -> bool:
    """
    Whether a process still runs.

    An orphan whose new parent never reaps it, as a container's first process may
    not, remains a zombie that signals still reach.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] == "Z")


# What rules_godot's logger autoload does when the game starts: create the errors
# file the override.cfg in Godot's working directory names.
START_LOGGER = """import pathlib as _pathlib, re as _re, sys as _sys
_override = _pathlib.Path(_sys.argv[_sys.argv.index("--path") + 1]) / "override.cfg"
if _override.exists():
    _found = _re.search(r'run/errors="([^"]*)"', _override.read_text())
    if _found:
        _pathlib.Path(_found.group(1)).touch()
"""


def fake_editor(base: Path, body: str, logger: bool = True) -> Path:
    """An executable standing in for the Godot editor, with the logger unless disabled."""
    return write_stub_program(base / "editor", (START_LOGGER if logger else "") + body)


# A fake editor's stand-in for rules_godot's logger autoload: it records an error
# where the override.cfg Godot reads names the errors file.
RECORD_ERROR = """import pathlib, re, sys
root = pathlib.Path(sys.argv[sys.argv.index("--path") + 1])
override = (root / "override.cfg").read_text()
errors = re.search(r'run/errors="([^"]*)"', override).group(1)
pathlib.Path(errors).write_text(
    '{"type": "script", "location": "res://main.gd:3", "function": "_ready", "text": "boom"}\\n'
)
"""


def existing_runfile(key: str) -> Path:
    """Resolve fixture runfile keys like the runner, failing for absent files."""
    if not Path(key).exists():
        raise FileNotFoundError(key)
    return Path(key)


def run_project(
    base: Path, project: Path, members: dict[str, str], imports: Iterable[str] = ()
) -> dict[str, Any]:
    """A run-manifest project whose runfile keys are absolute fixture paths."""
    (base / "imports.txt").write_text("".join(path + "\n" for path in imports))
    (base / "initialized").mkdir(exist_ok=True)
    return {
        "project_file": str(project),
        "member_resource_paths": members,
        "import_resource_paths": {},
        "imports": str(base / "imports.txt"),
        "initialized": str(base / "initialized"),
    }


# A fake editor that starts a child process, records both process IDs in a file and
# waits to be cancelled.
WAIT_FOR_CANCELLATION = """import json, os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"])
print("runtime started", flush=True)
pidfile = pathlib.Path({pids!r})
pidfile.with_suffix(".tmp").write_text(json.dumps([os.getpid(), child.pid]))
pidfile.with_suffix(".tmp").replace(pidfile)
time.sleep(90)
"""


def cancellation_manifest(base: Path, engine_pids: Path) -> Path:
    """Write a run manifest whose editor waits to be cancelled, and return its path."""
    project = base / "project.godot"
    project.write_text("config_version=5\n")
    script = base / "main.gd"
    script.write_text("fixture")
    editor = fake_editor(base, WAIT_FOR_CANCELLATION.format(pids=str(engine_pids)))
    manifest = base / "manifest.json"
    manifest.write_text(
        json.dumps(
            run_manifest(
                editor=str(editor),
                main="main.gd",
                project=run_project(base, project, {"main.gd": str(script)}),
            )
        )
    )
    return manifest


def start_runner(base: Path, manifest: Path, reports: Path) -> subprocess.Popen:
    """Start the runner's command line in its own interpreter."""
    # rules_python initializes sys.path in its launcher. A nested
    # interpreter needs those same declared runfiles explicitly.
    python_path = os.pathsep.join(str(Path(path).absolute()) for path in sys.path)
    runner_file = sys.modules[run.__module__].__file__
    if runner_file is None:
        raise AssertionError("The runner module has no source file")
    env = {
        **os.environ,
        "PYTHONPATH": python_path,
        "RUNFILES_DIR": str(base),
        "TEST_UNDECLARED_OUTPUTS_DIR": str(reports),
    }
    return subprocess.Popen(
        [sys.executable, str(Path(runner_file).absolute()), "--manifest", str(manifest)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_runner(process: subprocess.Popen) -> None:
    """Stop the runner if it still runs, and collect its output."""
    if process.poll() is not None:
        process.communicate()
        return
    process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def kill_engine(pids: list[int], engine_pids: Path) -> None:
    """Kill the engine's process group, which a failed cancellation may leave behind."""
    if not pids and engine_pids.exists():
        pids = json.loads(engine_pids.read_text())
    if pids:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pids[0], signal.SIGKILL)


# A fake editor's checks of what a source run gives Godot: the cached import and
# initialization, the original settings with the project's features and flags, and
# Bazel's test environment.
CHECK_SOURCE_RUN = """import os, pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index("--path") + 1])
assert (root / ".godot/imported/seed.bin").read_bytes() == b"cached"
assert pathlib.Path(os.environ["HOME"]).is_dir()
# The project's cached initialization replaces an editor pass at run time.
assert "--import" not in sys.argv
assert (root / ".godot/global_script_class_cache.cfg").read_text() == "initialized"
settings = (root / "project.godot").read_text()
assert "autoload" in settings and "run/main_scene" in settings
# The project's custom features, which Godot reads from the root key.
assert settings.startswith('_custom_features="production,debug_tools"\\n'), settings
# The project's settings from flags, in the staged project.godot.
assert 'config/build_number=57\\nconfig/commit="abc"\\n' in settings, settings
assert "--headless" in sys.argv
assert sys.argv[-4:] == ["--script", "res://runtime.gd", "--", "user argument"]
# Bazel's test contract and declared env reach the engine; the rest does not.
assert os.environ["TEST_SHARD_INDEX"] == "1"
runfiles = pathlib.Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"]
assert (runfiles / "data.txt").read_text() == "declared runfile"
assert pathlib.Path(os.environ["RUNFILES_DIR"]) / "demo" == runfiles
assert pathlib.Path(os.environ["RUNFILES_MANIFEST_FILE"]).read_text() == "demo/data.txt " + str(runfiles / "data.txt")
assert os.environ["DECLARED"] == "value"
assert "UNDECLARED" not in os.environ
print("source run passed")
"""


def cached_import(base: Path) -> Path:
    """Write an import result and the project's cached initialization; return the result."""
    imported = base / "import-result"
    (imported / ".godot/imported").mkdir(parents=True)
    (imported / ".godot/imported/seed.bin").write_bytes(b"cached")
    (base / "initialized/.godot").mkdir(parents=True)
    (base / "initialized/.godot/global_script_class_cache.cfg").write_text("initialized")
    return imported


def bazel_test_environment(base: Path, reports: Path) -> dict[str, str]:
    """Write a runfiles tree with one declared runfile; return Bazel's test environment."""
    runfiles = base / "runfiles"
    (runfiles / "demo").mkdir(parents=True)
    (runfiles / "demo/data.txt").write_text("declared runfile")
    runfiles_manifest = base / "MANIFEST"
    runfiles_manifest.write_text("demo/data.txt " + str(runfiles / "demo/data.txt"))
    return {
        "TEST_UNDECLARED_OUTPUTS_DIR": str(reports),
        "TEST_SHARD_INDEX": "1",
        "TEST_SRCDIR": str(runfiles),
        "TEST_WORKSPACE": "demo",
        "RUNFILES_DIR": str(runfiles),
        "RUNFILES_MANIFEST_FILE": str(runfiles_manifest),
        "UNDECLARED": "value",
    }


class ExecutionTest(unittest.TestCase):
    def test_pack_run_stages_extension_library_runfiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pack = base / "authored.pck"
            pack.write_bytes(b"resource pack")
            library = base / "library.so"
            library.write_bytes(b"extension library")
            descriptor = base / "descriptor.gdextension"
            descriptor.write_text("[configuration]\n")
            editor = fake_editor(
                base,
                """import pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index("--path") + 1])
assert pathlib.Path(sys.argv[sys.argv.index("--main-pack") + 1]).read_bytes() == b"resource pack"
assert (root / "native/libhello.so").read_bytes() == b"extension library"
assert (root / "native/hello.gdextension").read_text() == "[configuration]\\n"
""",
            )
            with mock.patch("tools.inputs.runfiles.locate", side_effect=existing_runfile):
                self.assertEqual(
                    0,
                    run(
                        run_manifest(
                            editor=str(editor),
                            pack=str(pack),
                            extension_resource_paths={
                                "native/libhello.so": str(library),
                                "native/hello.gdextension": str(descriptor),
                            },
                        )
                    ),
                )

    def test_pack_run_lists_desktop_release_libraries_for_the_editor(self) -> None:
        # A merged pack descriptor, as the pack writers write it.
        release = (
            "[configuration]\n"
            'entry_symbol="init"\n\n'
            "[dependencies]\n"
            'macos.arm64.release={"res://bin/libdep.dylib": ""}\n\n'
            "[libraries]\n"
            'android.arm64.release="res://bin/libhello.so"\n'
            'macos.arm64.release="res://bin/libhello.dylib"\n'
        )
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "pack.pck"
            # Godot's export names the files with res://.
            write_pck(pack, {"res://hello.gdextension": release.encode()}, (4, 7, 2))
            replaced = pack_descriptors(
                {"pack": str(pack), "release_descriptors": ["hello.gdextension"]}, Path
            )
        # The editor that runs the pack has the editor_runtime feature tag, not release;
        # Android entries stay as they are.
        self.assertEqual(
            {
                "res://hello.gdextension": (
                    b"[configuration]\n"
                    b'entry_symbol="init"\n\n'
                    b"[dependencies]\n"
                    b'macos.arm64.release={"res://bin/libdep.dylib": ""}\n'
                    b'macos.arm64.editor_runtime={"res://bin/libdep.dylib": ""}\n\n'
                    b"[libraries]\n"
                    b'android.arm64.release="res://bin/libhello.so"\n'
                    b'macos.arm64.release="res://bin/libhello.dylib"\n'
                    b'macos.arm64.editor_runtime="res://bin/libhello.dylib"\n'
                )
            },
            replaced,
        )

    def test_missing_common_manifest_fields_fail_before_engine_launch(self) -> None:
        manifest = run_manifest(pack="pack", extension_resource_paths={})
        for field in run_manifest():
            incomplete = {key: value for key, value in manifest.items() if key != field}
            with (
                self.subTest(field=field),
                mock.patch("tools.inputs.runfiles.locate") as locate,
                self.assertRaisesRegex(
                    ExecutionError, f"Missing required run manifest field: '{field}'"
                ),
            ):
                run(incomplete)
            locate.assert_not_called()

    def run_editor_with_stderr(
        self, body: str, logger: bool = True, **fields: Any
    ) -> tuple[int, str]:
        """Run a project with a fake editor; return the exit code and the stderr."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project.godot"
            project.write_text("config_version=5\n")
            manifest = run_manifest(
                editor=str(fake_editor(base, body, logger)),
                project=run_project(base, project, {}),
                **fields,
            )
            stderr = io.StringIO()
            with (
                mock.patch("tools.inputs.runfiles.locate", side_effect=existing_runfile),
                mock.patch.dict(
                    os.environ, {"TEST_UNDECLARED_OUTPUTS_DIR": str(base / "outputs")}
                ),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(stderr),
            ):
                return run(manifest), stderr.getvalue()

    def run_editor(self, body: str, **fields: Any) -> int:
        return self.run_editor_with_stderr(body, **fields)[0]

    def test_exit_code_decides_the_outcome(self) -> None:
        self.assertEqual(self.run_editor("print('ok')\n"), 0)
        self.assertEqual(self.run_editor("raise SystemExit(3)\n"), 3)

    def test_a_recorded_error_fails_a_zero_exit(self) -> None:
        code, stderr = self.run_editor_with_stderr(RECORD_ERROR)
        self.assertEqual(1, code)
        self.assertIn(
            "rules_godot: Godot reported 1 error(s) while the game ran, first at "
            "res://main.gd:3: boom",
            stderr,
        )
        self.assertEqual(3, self.run_editor(RECORD_ERROR + "raise SystemExit(3)\n"))

    def test_reported_errors_keep_the_exit_status(self) -> None:
        code, stderr = self.run_editor_with_stderr(RECORD_ERROR, engine_errors="report")
        self.assertEqual(0, code)
        self.assertIn("Godot reported 1 error(s)", stderr)

    def test_a_run_without_its_logger_fails_unless_it_reports(self) -> None:
        for engine_errors, expected in [("fail", 1), ("report", 0)]:
            with self.subTest(engine_errors=engine_errors):
                code, stderr = self.run_editor_with_stderr(
                    "", logger=False, engine_errors=engine_errors
                )
                self.assertEqual(expected, code)
                self.assertEqual(
                    engine_errors == "fail", "the run logger did not start" in stderr
                )

    def test_a_logger_godot_cannot_load_is_named(self) -> None:
        body = """print('SCRIPT ERROR: Parse Error: Function "_init()" has no static return type.')
print('          at: GDScript::reload (/tmp/work/rules_godot_errors.gd:63)')
"""
        code, stderr = self.run_editor_with_stderr(body, logger=False)
        self.assertEqual(1, code)
        self.assertIn(
            "the run logger did not start, so errors Godot reported were not recorded; "
            'Godot could not load it: SCRIPT ERROR: Parse Error: Function "_init()" has no '
            "static return type.",
            stderr,
        )

    def test_output_alone_decides_nothing(self) -> None:
        for output in ["SCRIPT ERROR: parse failed", "ERROR: 1 resources still in use"]:
            with self.subTest(output=output):
                self.assertEqual(0, self.run_editor(f"print({output!r})\n"))

    def test_the_logger_joins_through_override_cfg(self) -> None:
        body = """import pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index("--path") + 1])
print((root / "override.cfg").read_text())
"""
        for fields, stop in [
            ({}, "false"),
            ({"stop_on_error": True}, "true"),
            ({"stop_on_error": True, "engine_errors": "report"}, "false"),
        ]:
            with self.subTest(**fields), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                project = base / "project.godot"
                project.write_text("config_version=5\n")
                authored = base / "override.cfg"
                authored.write_text("[display]\n\nwindow/size/mode=2")
                manifest = run_manifest(
                    editor=str(fake_editor(base, body)),
                    project=run_project(base, project, {"override.cfg": str(authored)}),
                    **fields,
                )
                stdout = io.StringIO()
                with (
                    mock.patch(
                        "tools.inputs.runfiles.locate", side_effect=existing_runfile
                    ),
                    contextlib.redirect_stdout(stdout),
                ):
                    self.assertEqual(0, run(manifest))
                override = stdout.getvalue()
                self.assertTrue(
                    override.startswith("[display]\n\nwindow/size/mode=2\n"), override
                )
                self.assertRegex(
                    override, r'RulesGodotErrors="\*/.*/rules_godot_errors\.gd"'
                )
                self.assertRegex(override, r'run/errors="/.*/reports/errors\.jsonl"')
                self.assertIn(f"run/stop_on_error={stop}", override)

    def test_headless_false_runs_with_a_display(self) -> None:
        body = "import sys\nassert '--headless' not in sys.argv, sys.argv\n"
        self.assertEqual(0, self.run_editor(body, headless=False))

    def test_additional_packs_are_staged_in_the_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "extra.pck"
            pack.write_bytes(b"additional pack")
            body = """import pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index("--path") + 1])
assert pathlib.Path.cwd() == root.resolve()
assert pathlib.Path("dlc/extra.pck").read_bytes() == b"additional pack"
"""
            self.assertEqual(
                0, self.run_editor(body, additional_packs={"dlc/extra.pck": str(pack)})
            )

    def test_additional_pack_colliding_with_a_staged_file_fails(self) -> None:
        cases = {
            "pack run": lambda base: {
                "pack": str(base / "data.bin"),
                "extension_resource_paths": {},
                "additional_packs": {"main.pck": str(base / "extra.pck")},
            },
            "project run": lambda base: {
                "project": run_project(
                    base, base / "project.godot", {"data.bin": str(base / "data.bin")}
                ),
                "additional_packs": {"data.bin": str(base / "extra.pck")},
            },
        }
        for case, fields in cases.items():
            with self.subTest(case), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                (base / "project.godot").write_text("config_version=5\n")
                (base / "data.bin").write_bytes(b"staged")
                (base / "extra.pck").write_bytes(b"additional pack")
                started = base / "started"
                manifest = run_manifest(
                    editor=str(fake_editor(base, f"open({str(started)!r}, 'w')\n")),
                    **fields(base),
                )
                name = next(iter(manifest["additional_packs"]))
                message = f"Additional pack {name} collides with a staged file"
                with (
                    mock.patch(
                        "tools.inputs.runfiles.locate", side_effect=existing_runfile
                    ),
                    mock.patch.dict(
                        os.environ, {"TEST_UNDECLARED_OUTPUTS_DIR": str(base / "outputs")}
                    ),
                    self.assertRaisesRegex(ExecutionError, f"^{message}$"),
                ):
                    run(manifest)
                runner = json.loads((base / "outputs/godot/runner.json").read_text())
                self.assertEqual(message, runner["error"])
                self.assertFalse(started.exists())

    def wait_for_engine(self, process: subprocess.Popen, engine_pids: Path) -> list[int]:
        """Return the engine's process IDs once it runs; fail if it does not start."""
        deadline = time.monotonic() + 10
        while (
            not engine_pids.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        if not engine_pids.exists():
            if process.poll() is None:
                process.terminate()
            output, _ = process.communicate(timeout=10)
            self.fail(
                f"Engine did not start (runner exit {process.returncode}):\n{output}"
            )
        return json.loads(engine_pids.read_text())

    def assert_stops(self, pid: int) -> None:
        deadline = time.monotonic() + 5
        while alive(pid):
            self.assertLess(
                time.monotonic(), deadline, f"Engine process {pid} survived cancellation"
            )
            time.sleep(0.02)

    @unittest.skipIf(os.name == "nt", "POSIX process-group cancellation contract")
    def test_cancellation_stops_engine_and_children_and_publishes_failure(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            with (
                self.subTest(signal=signum.name),
                tempfile.TemporaryDirectory() as temporary,
            ):
                base = Path(temporary)
                engine_pids = base / "engine-pids.json"
                reports = base / "outputs"
                manifest = cancellation_manifest(base, engine_pids)
                process = start_runner(base, manifest, reports)
                pids = []
                try:
                    pids = self.wait_for_engine(process, engine_pids)
                    process.send_signal(signum)
                    output, _ = process.communicate(timeout=10)
                    self.assertNotEqual(process.returncode, 0, output)
                    diagnostic = f"Godot interrupted by {signum.name}"
                    self.assertIn(diagnostic, output)
                    self.assertEqual(
                        json.loads((reports / "godot/runner.json").read_text())["error"],
                        diagnostic,
                    )
                    self.assertIn(
                        "runtime started", (reports / "godot/runtime.log").read_text()
                    )
                    for pid in pids:
                        self.assert_stops(pid)
                finally:
                    stop_runner(process)
                    kill_engine(pids, engine_pids)

    def test_source_run_starts_from_cached_initialization_with_original_settings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project.godot"
            original = 'config_version=5\n[application]\nrun/main_scene="res://scene.tscn"\n[autoload]\nSingleton="*res://singleton.gd"\n'
            project.write_text(original)
            script = base / "runtime.gd"
            script.write_text("fixture")
            # An import unit without importable files has an empty import result, which
            # Bazel leaves out of runfiles.
            manifest = run_manifest(
                project=run_project(
                    base,
                    project,
                    {"runtime.gd": str(script)},
                    [str(cached_import(base)), str(base / "empty-unit")],
                )
            )
            reports = base / "outputs"
            manifest.update(
                editor=str(fake_editor(base, CHECK_SOURCE_RUN)),
                main="runtime.gd",
                env={"DECLARED": "value"},
            )
            manifest["project"]["custom_features"] = ["production", "debug_tools"]
            manifest["project"]["flag_settings"] = {
                "application/config/commit": '"abc"',
                "application/config/build_number": "57",
            }
            with (
                mock.patch("tools.inputs.runfiles.locate", side_effect=existing_runfile),
                mock.patch.dict(os.environ, bazel_test_environment(base, reports)),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(run(manifest, ["--", "user argument"]), 0)
            self.assertEqual(project.read_text(), original)
            self.assertIn(
                "source run passed", (reports / "godot/runtime.log").read_text()
            )
            self.assertIsNone(
                json.loads((reports / "godot/runner.json").read_text())["error"]
            )


class LocateTest(unittest.TestCase):
    def test_manifest_keys_may_contain_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "with space.txt"
            target.write_text("")
            manifest = Path(directory) / "MANIFEST"
            # Bazel escapes a space of a key in a line that then starts with one.
            manifest.write_text(f" _main/dir\\swith\\sspace/file.txt {target}\n")
            environment = {"RUNFILES_MANIFEST_FILE": str(manifest)}
            with mock.patch.dict(os.environ, environment, clear=True):
                found = locate("_main/dir with space/file.txt")
        self.assertEqual(target.resolve(), found)


if __name__ == "__main__":
    unittest.main()

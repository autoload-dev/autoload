"""Regression tests for CI's plan of every lane and the assignment of tasks to jobs."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ci.verification import (
    JOBS,
    LANES,
    SCHEDULED_LANES,
    addon_task_name,
    all_lanes,
    excluded_hosts,
    for_host,
    lane_for,
    output_name,
    plan_outputs,
    run_tasks,
    task_command,
    verify_results,
    without_scheduled_lanes,
)

ROOT = Path(__file__).resolve().parents[2]


def plan_outputs_of(**planned: str) -> dict[str, str]:
    """CI's plan outputs, every job's empty but those given."""
    return {output_name(job): "[]" for job in JOBS} | planned


def needs_of(**planned: str) -> dict:
    """CI's jobs after a successful plan."""
    return {"plan": {"result": "success", "outputs": plan_outputs_of(**planned)}}


class VerificationTest(unittest.TestCase):
    def test_every_lane_but_the_scheduled_ones_has_a_job_and_host_runs_on_both_hosts(
        self,
    ) -> None:
        lanes = [lane for lane, _ in JOBS.values()]
        self.assertEqual(set(lanes), set(LANES) - set(SCHEDULED_LANES))
        hosts = {host for lane, host in JOBS.values() if lane == "host"}
        self.assertEqual(hosts, {"linux", "macos"})

    def test_planned_lane_cannot_be_satisfied_by_api_docs_success(self) -> None:
        needs = needs_of(android='["android"]') | {
            "api-docs": {"result": "success"},
            "android": {"result": "skipped"},
        }
        with self.assertRaisesRegex(ValueError, "android.*skipped"):
            verify_results(needs)
        needs["android"]["result"] = "success"
        verify_results(needs)

    def test_host_tasks_require_the_host_job_of_each_host(self) -> None:
        for job in ("tests-linux", "tests-macos"):
            with self.subTest(job=job):
                needs = needs_of(**{output_name(job): '["test:bazel"]'}) | {
                    job: {"result": "skipped"}
                }
                with self.assertRaisesRegex(ValueError, f"{job}.*skipped"):
                    verify_results(needs)
                needs[job]["result"] = "success"
                verify_results(needs)

    def test_runs_leave_the_scheduled_source_engine_lane_out(self) -> None:
        lanes = {lane: [] for lane in LANES} | {
            "host": ["test:bazel"],
            "source-engine": ["source-engine", "test:example:petri"],
        }
        planned = without_scheduled_lanes(lanes)
        self.assertEqual(planned["source-engine"], [])
        self.assertEqual(planned["host"], ["test:bazel"])

    def test_source_engine_workflow_runs_every_source_engine_case(self) -> None:
        workflow = (ROOT / ".github/workflows/source-engine.yml").read_text()
        self.assertIn("""tools.ci.verification run '["source-engine:full"]'""", workflow)
        with mock.patch("subprocess.run") as run:
            run_tasks(["source-engine:full"])
        run.assert_called_once_with(["mise", "run", "source-engine:full"], check=True)

    def test_missing_plan_output_is_not_an_empty_task_list(self) -> None:
        empty = {"plan": {"result": "success", "outputs": {}}}
        with self.assertRaisesRegex(ValueError, "missing.*formatting"):
            verify_results(empty)
        outputs = plan_outputs_of()
        del outputs["tests_macos"]
        with self.assertRaisesRegex(ValueError, "missing.*tests_macos"):
            verify_results({"plan": {"result": "success", "outputs": outputs}})

    def test_missing_plan_and_cancelled_jobs_fail_verification(self) -> None:
        with self.assertRaisesRegex(ValueError, "plan"):
            verify_results({})
        with self.assertRaisesRegex(ValueError, "cancelled"):
            verify_results(needs_of() | {"tests-linux": {"result": "cancelled"}})
        with self.assertRaisesRegex(ValueError, "failure"):
            verify_results(needs_of() | {"ios": {"result": "failure"}})

    def test_every_run_plans_every_lane_but_the_scheduled_ones(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mise.toml").write_text(
                "".join(
                    f'[tasks."{task}"]\nrun = "true"\n'
                    for task in (
                        "lint",
                        "docs",
                        "test:bazel",
                        "test:example:petri",
                        "android",
                        "format",
                        "addon:host",
                    )
                )
            )
            for module, lanes in (("widget", '"host", "ios"'), ("gadget", '"host"')):
                (root / "addons" / module).mkdir(parents=True)
                (root / "addons" / module / "MODULE.bazel").write_text(
                    f'module(name = "autoload_{module}")\n'
                )
                (root / "addons" / module / "addon.pkl").write_text(
                    f'amends "../../tools/addons/Addon.pkl"\nlanes = List({lanes})\n'
                )
            lanes = without_scheduled_lanes(all_lanes(root))
            (root / "mise.toml").write_text('[tasks."test:gdscript"]\nrun = "true"\n')
            with self.assertRaisesRegex(ValueError, "test:gdscript"):
                all_lanes(root)
        self.assertEqual(lanes["quality"], ["lint"])
        self.assertEqual(lanes["docs"], ["docs"])
        self.assertEqual(lanes["source-engine"], [])
        self.assertEqual(
            lanes["host"],
            [
                "test:bazel",
                "host:addon:gadget",
                "host:addon:widget",
                "host:addon-template@linux",
            ],
        )
        self.assertEqual(lanes["android"], ["android", "android:addon-template"])
        self.assertEqual(lanes["ios"], ["ios:addon:widget", "ios:addon-template"])

    def test_every_task_of_mise_toml_has_a_lane_or_is_another_task(self) -> None:
        lanes = all_lanes(ROOT)
        self.assertIn("test:regressions", lanes["host"])
        self.assertIn("ios", lanes["ios"])

    def test_unknown_tasks_have_no_lane(self) -> None:
        for task in (
            "new-check",
            "contracts:desktop",
            "desktop:addon:widget",
            "host:addon:",
        ):
            with self.subTest(task=task), self.assertRaises(ValueError):
                lane_for(task)

    def test_a_host_lane_limited_to_some_hosts_names_them(self) -> None:
        self.assertEqual(
            addon_task_name("host", "widget", ("linux", "macos")), "host:addon:widget"
        )
        self.assertEqual(
            addon_task_name("host", "widget", ("macos",)), "host:addon:widget@macos"
        )
        self.assertEqual(addon_task_name("ios", "widget", ("macos",)), "ios:addon:widget")

    def test_add_on_tasks_run_the_generic_add_on_tasks(self) -> None:
        for task, lane in (
            ("host:addon:widget", "host"),
            ("android:addon:widget", "android"),
            ("host:addon:gadget@macos", "host"),
            ("ios:addon-template", "ios"),
        ):
            self.assertEqual(lane_for(task), lane)
        self.assertEqual(
            task_command("android:addon:widget"),
            ["mise", "run", "addon:android", "widget"],
        )
        self.assertEqual(
            task_command("host:addon:gadget@macos"),
            ["mise", "run", "addon:host", "gadget"],
        )
        self.assertEqual(
            task_command("ios:addon-template"), ["mise", "run", "addon:template", "ios"]
        )
        self.assertEqual(
            task_command("host:addon-template@linux"),
            ["mise", "run", "addon:template", "host"],
        )
        self.assertEqual(task_command("test:setup"), ["mise", "run", "test:setup"])

    def test_a_host_lane_limited_to_macos_runs_on_macos_only(self) -> None:
        lanes = {lane: [] for lane in LANES} | {
            "host": ["test:bazel", "host:addon:gadget@macos"]
        }
        self.assertEqual(for_host(lanes["host"], "linux"), ["test:bazel"])
        self.assertEqual(
            for_host(lanes["host"], "macos"), ["test:bazel", "host:addon:gadget@macos"]
        )
        only_linux = {lane: [] for lane in LANES} | {"host": ["host:addon:gadget@linux"]}
        outputs = plan_outputs(only_linux)
        self.assertEqual(outputs["tests_linux"], ["host:addon:gadget@linux"])
        self.assertEqual(outputs["tests_macos"], [])

    def test_the_plan_says_which_host_jobs_need_the_android_sdk(self) -> None:
        lanes = {lane: [] for lane in LANES} | {"host": ["host:addon:widget"]}
        self.assertFalse(plan_outputs(lanes)["tests_linux_android"])
        lanes["host"].append("test:bazel")
        self.assertTrue(plan_outputs(lanes)["tests_linux_android"])
        self.assertTrue(plan_outputs(lanes)["tests_macos_android"])

    def test_a_fork_pull_request_stays_off_the_self_hosted_runners(self) -> None:
        def event(head: dict | None) -> dict:
            return {
                "repository": {"full_name": "org/repo"},
                "pull_request": {"head": {"repo": head}},
            }

        self.assertEqual(
            excluded_hosts("pull_request", event({"full_name": "org/repo"})), set()
        )
        for head in ({"full_name": "fork/repo"}, None):
            with self.subTest(head=head):
                self.assertEqual(excluded_hosts("pull_request", event(head)), {"macos"})
        self.assertEqual(excluded_hosts("merge_group", {}), set())
        lanes = {lane: [] for lane in LANES} | {"host": ["test:bazel"], "ios": ["ios"]}
        outputs = plan_outputs(lanes, frozenset({"macos"}))
        self.assertEqual(outputs["tests_linux"], ["test:bazel"])
        self.assertEqual(outputs["tests_macos"], [])
        self.assertEqual(outputs["ios"], [])

    def test_the_plan_assigns_each_job_its_lane_on_its_host(self) -> None:
        lanes = {lane: [] for lane in LANES} | {
            "host": ["test:bazel", "host:addon:widget@linux"],
            "ios": ["ios:addon:widget"],
        }
        self.assertEqual(
            plan_outputs(lanes),
            {
                "formatting": [],
                "api_docs": [],
                "tests_linux": ["test:bazel", "host:addon:widget@linux"],
                "tests_linux_android": True,
                "tests_macos": ["test:bazel"],
                "tests_macos_android": True,
                "android": [],
                "ios": ["ios:addon:widget"],
            },
        )


if __name__ == "__main__":
    unittest.main()

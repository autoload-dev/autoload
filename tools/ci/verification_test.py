"""Regression tests for fail-closed CI selection and the assignment of tasks to lanes."""

import unittest
from pathlib import Path
from unittest import mock

from tools.ci.verification import (
    JOBS,
    LANES,
    SCHEDULED_LANES,
    for_host,
    lane_plan,
    output_name,
    plan_outputs,
    run_tasks,
    selection_args,
    task_command,
    verify_results,
    without_scheduled_lanes,
)

ROOT = Path(__file__).resolve().parents[2]


def selection_outputs(**selected: str) -> dict[str, str]:
    """CI's selection outputs, every job's empty but those given."""
    return {output_name(job): "[]" for job in JOBS} | selected


def needs_of(**selected: str) -> dict:
    """CI's jobs after a successful selection."""
    return {"selection": {"result": "success", "outputs": selection_outputs(**selected)}}


class VerificationTest(unittest.TestCase):
    def test_every_lane_but_the_scheduled_ones_has_a_job_and_host_runs_on_both_hosts(
        self,
    ) -> None:
        lanes = [lane for lane, _ in JOBS.values()]
        self.assertEqual(set(lanes), set(LANES) - set(SCHEDULED_LANES))
        hosts = {host for lane, host in JOBS.values() if lane == "host"}
        self.assertEqual(hosts, {"linux", "macos"})

    def test_selected_lane_cannot_be_satisfied_by_api_docs_success(self) -> None:
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
        self.assertIn("""verification.py run '["source-engine:full"]'""", workflow)
        with mock.patch("subprocess.run") as run:
            run_tasks(["source-engine:full"])
        run.assert_called_once_with(["mise", "run", "source-engine:full"], check=True)

    def test_missing_selection_output_is_not_an_empty_task_list(self) -> None:
        empty = {"selection": {"result": "success", "outputs": {}}}
        with self.assertRaisesRegex(ValueError, "missing.*formatting"):
            verify_results(empty)
        outputs = selection_outputs()
        del outputs["tests_macos"]
        with self.assertRaisesRegex(ValueError, "missing.*tests_macos"):
            verify_results({"selection": {"result": "success", "outputs": outputs}})

    def test_missing_selection_and_cancelled_jobs_fail_verification(self) -> None:
        with self.assertRaisesRegex(ValueError, "selection"):
            verify_results({})
        with self.assertRaisesRegex(ValueError, "cancelled"):
            verify_results(needs_of() | {"tests-linux": {"result": "cancelled"}})
        with self.assertRaisesRegex(ValueError, "failure"):
            verify_results(needs_of() | {"ios": {"result": "failure"}})

    def test_documentation_does_not_request_lane_work(self) -> None:
        lanes = lane_plan(
            {
                "steps": [
                    {"name": "conventions:docs", "status": "included"},
                    {"name": "android", "status": "skipped"},
                    {"name": "ios", "status": "skipped"},
                ]
            }
        )
        self.assertEqual(lanes["quality"], ["conventions:docs"])
        self.assertFalse(any(tasks for name, tasks in lanes.items() if name != "quality"))

    def test_setup_validation_does_not_become_an_app_build(self) -> None:
        lanes = lane_plan(
            {
                "steps": [
                    {"name": "test:setup", "status": "included"},
                    {"name": "lint:ci", "status": "included"},
                ]
            }
        )
        self.assertEqual(lanes["quality"], ["test:setup", "lint:ci"])
        self.assertFalse(any(tasks for name, tasks in lanes.items() if name != "quality"))

    def test_complementary_conventions_retain_local_selection(self) -> None:
        lanes = lane_plan(
            {
                "steps": [
                    {"name": "conventions:code", "status": "included"},
                    {"name": "conventions:docs", "status": "included"},
                    {"name": "test:example:sqlite", "status": "included"},
                ]
            }
        )
        self.assertEqual(lanes["quality"], ["conventions:code", "conventions:docs"])
        self.assertEqual(lanes["host"], ["test:example:sqlite"])

    def test_unknown_step_or_status_cannot_silently_drop_required_work(self) -> None:
        for step in (
            {"name": "new-check", "status": "included"},
            {"name": "contracts:desktop", "status": "included"},
            {"name": "desktop:addon:widget", "status": "included"},
            {"name": "host:addon:", "status": "included"},
            {"name": "host:addon-other", "status": "included"},
            {"name": "ios", "status": "error"},
        ):
            with self.subTest(step=step), self.assertRaises(ValueError):
                lane_plan({"steps": [step]})

    def test_add_on_tasks_run_the_generic_add_on_tasks(self) -> None:
        lanes = lane_plan(
            {
                "steps": [
                    {"name": name, "status": "included"}
                    for name in (
                        "host:addon:widget",
                        "android:addon:widget",
                        "host:addon:gadget@macos",
                        "ios:addon-template",
                    )
                ]
            }
        )
        self.assertEqual(lanes["host"], ["host:addon:widget", "host:addon:gadget@macos"])
        self.assertEqual(lanes["android"], ["android:addon:widget"])
        self.assertEqual(lanes["ios"], ["ios:addon-template"])
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
        self.assertEqual(for_host(lanes, "linux")["host"], ["test:bazel"])
        self.assertEqual(
            for_host(lanes, "macos")["host"], ["test:bazel", "host:addon:gadget@macos"]
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

    def test_pr_uses_base_and_checked_out_merge(self) -> None:
        self.assertEqual(
            selection_args("pull_request", {"pull_request": {"base": {"sha": "base"}}}),
            ["--from-ref", "base", "--to-ref", "HEAD"],
        )

    def test_merge_group_uses_its_parent_and_checked_out_head(self) -> None:
        self.assertEqual(
            selection_args("merge_group", {"merge_group": {"base_sha": "parent"}}),
            ["--from-ref", "parent", "--to-ref", "HEAD"],
        )

    def test_dispatch_checks_all(self) -> None:
        self.assertEqual(selection_args("workflow_dispatch", {}), ["--all"])
        with self.assertRaises(ValueError):
            selection_args("unrecognized", {})


if __name__ == "__main__":
    unittest.main()

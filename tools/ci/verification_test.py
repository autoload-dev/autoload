"""Regression tests for fail-closed CI selection and the assignment of tasks to lanes."""

import unittest

from tools.ci.verification import (
    LANES,
    WORKFLOW_JOBS,
    lane_plan,
    runs_apple,
    selection_args,
    verify_results,
)


def selection_outputs(workflow: str, **selected: str) -> dict[str, str]:
    """Use a workflow's output names, including its source_engine mapping."""
    outputs = {lane.replace("-", "_"): "[]" for lane in WORKFLOW_JOBS[workflow]}
    if workflow == "ci":
        outputs["apple"] = "false"
    return {**outputs, **selected}


def needs_of(workflow: str, **selected: str) -> dict:
    """A workflow's jobs after a successful selection."""
    return {
        "selection": {
            "result": "success",
            "outputs": selection_outputs(workflow, **selected),
        }
    }


class VerificationTest(unittest.TestCase):
    def test_every_lane_has_a_job_and_only_the_host_lane_runs_in_both_workflows(
        self,
    ) -> None:
        ci, apple = set(WORKFLOW_JOBS["ci"]), set(WORKFLOW_JOBS["apple"])
        self.assertEqual(ci | apple, set(LANES))
        self.assertEqual(ci & apple, {"host"})

    def test_selected_lane_cannot_be_satisfied_by_api_docs_success(self) -> None:
        needs = needs_of("ci", android='["android"]') | {
            "api-docs": {"result": "success"},
            "android": {"result": "skipped"},
        }
        with self.assertRaisesRegex(ValueError, "android.*skipped"):
            verify_results("ci", needs)
        needs["android"]["result"] = "success"
        verify_results("ci", needs)

    def test_pull_request_run_leaves_out_the_apple_workflow(self) -> None:
        lanes = {lane: [lane] for lane in LANES}
        self.assertFalse(runs_apple(lanes, "pull_request"))
        for event in ("merge_group", "push", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertTrue(runs_apple(lanes, event))

    def test_run_without_a_selected_apple_lane_does_not_call_the_apple_workflow(
        self,
    ) -> None:
        lanes = {lane: [] for lane in LANES} | {
            "quality": ["lint"],
            "android": ["android"],
        }
        self.assertFalse(runs_apple(lanes, "merge_group"))
        self.assertTrue(runs_apple(lanes | {"host": ["test:bazel"]}, "merge_group"))

    def test_ci_requires_the_apple_workflow_it_called(self) -> None:
        needs = needs_of("ci", apple="true") | {"apple": {"result": "skipped"}}
        with self.assertRaisesRegex(ValueError, "apple.*skipped"):
            verify_results("ci", needs)
        needs["apple"]["result"] = "success"
        verify_results("ci", needs)
        verify_results("ci", needs_of("ci") | {"apple": {"result": "skipped"}})

    def test_host_tasks_require_the_host_job_of_their_workflow(self) -> None:
        for workflow, job in (("ci", "tests-linux"), ("apple", "tests-macos")):
            with self.subTest(workflow=workflow):
                needs = needs_of(workflow, host='["test:bazel"]') | {
                    job: {"result": "skipped"}
                }
                with self.assertRaisesRegex(ValueError, f"{job}.*skipped"):
                    verify_results(workflow, needs)
                needs[job]["result"] = "success"
                verify_results(workflow, needs)

    def test_source_engine_workflow_output_requires_its_workflow_job(self) -> None:
        needs = needs_of("apple", source_engine='["source-engine"]') | {
            "source-engine": {"result": "skipped"}
        }
        with self.assertRaisesRegex(ValueError, "source-engine.*skipped"):
            verify_results("apple", needs)

    def test_missing_selection_output_is_not_an_empty_task_list(self) -> None:
        empty = {"selection": {"result": "success", "outputs": {}}}
        with self.assertRaisesRegex(ValueError, "missing.*quality"):
            verify_results("ci", empty)
        with self.assertRaisesRegex(ValueError, "missing.*host"):
            verify_results("apple", empty)
        outputs = selection_outputs("ci")
        del outputs["apple"]
        with self.assertRaisesRegex(ValueError, "missing.*apple"):
            verify_results("ci", {"selection": {"result": "success", "outputs": outputs}})

    def test_missing_selection_and_cancelled_jobs_fail_verification(self) -> None:
        with self.assertRaisesRegex(ValueError, "selection"):
            verify_results("ci", {})
        with self.assertRaisesRegex(ValueError, "cancelled"):
            verify_results(
                "ci", needs_of("ci") | {"tests-linux": {"result": "cancelled"}}
            )
        with self.assertRaisesRegex(ValueError, "failure"):
            verify_results("apple", needs_of("apple") | {"ios": {"result": "failure"}})

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
            {"name": "ios", "status": "error"},
        ):
            with self.subTest(step=step), self.assertRaises(ValueError):
                lane_plan({"steps": [step]})

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

    def test_push_and_dispatch_boundaries(self) -> None:
        self.assertEqual(
            selection_args("push", {"before": "old"}),
            ["--from-ref", "old", "--to-ref", "HEAD"],
        )
        self.assertEqual(selection_args("push", {"before": "0" * 40}), ["--all"])
        self.assertEqual(selection_args("workflow_dispatch", {}), ["--all"])
        with self.assertRaises(ValueError):
            selection_args("unrecognized", {})


if __name__ == "__main__":
    unittest.main()

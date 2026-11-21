"""Regression tests for fail-closed CI selection and the assignment of tasks to lanes."""

import unittest

from tools.ci.verification import (
    LANES,
    WORKFLOW_JOBS,
    job_plan,
    lane_plan,
    selection_args,
    verify_results,
)


def selection_outputs(**selected: str) -> dict[str, str]:
    """Use the workflow's output names, including its source_engine mapping."""
    return {**{output.replace("-", "_"): "[]" for output in WORKFLOW_JOBS}, **selected}


def selected_everywhere() -> dict[str, list[str]]:
    """A selection with one task in every lane."""
    return {lane: [lane] for lane in LANES}


class VerificationTest(unittest.TestCase):
    def test_selected_lane_cannot_be_satisfied_by_api_docs_success(self) -> None:
        needs = {
            "selection": {
                "result": "success",
                "outputs": selection_outputs(android='["android"]'),
            },
            "api-docs": {"result": "success"},
            "android": {"result": "skipped"},
        }
        with self.assertRaisesRegex(ValueError, "android.*skipped"):
            verify_results(needs)
        needs["android"]["result"] = "success"
        verify_results(needs)

    def test_pull_request_run_leaves_out_the_apple_jobs(self) -> None:
        jobs = job_plan(selected_everywhere(), "pull_request", apple_only=False)
        self.assertEqual(
            {output for output, tasks in jobs.items() if tasks},
            {"quality", "docs", "host", "android"},
        )

    def test_macos_preview_runs_only_the_apple_jobs(self) -> None:
        jobs = job_plan(selected_everywhere(), "pull_request", apple_only=True)
        self.assertEqual(
            {output: tasks for output, tasks in jobs.items() if tasks},
            {"host-macos": ["host"], "source-engine": ["source-engine"], "ios": ["ios"]},
        )

    def test_merge_queue_main_and_dispatch_run_every_selected_job(self) -> None:
        for event in ("merge_group", "push", "workflow_dispatch"):
            with self.subTest(event=event):
                jobs = job_plan(selected_everywhere(), event, apple_only=False)
                self.assertEqual(set(jobs), set(WORKFLOW_JOBS))
                self.assertTrue(all(jobs.values()))
                self.assertEqual(jobs["host-macos"], jobs["host"])

    def test_unselected_lane_stays_empty_in_every_run(self) -> None:
        lanes = selected_everywhere() | {"host": [], "ios": []}
        jobs = job_plan(lanes, "merge_group", apple_only=False)
        self.assertEqual((jobs["host"], jobs["host-macos"], jobs["ios"]), ([], [], []))

    def test_host_tasks_require_the_job_of_each_host_that_runs_them(self) -> None:
        needs = {
            "selection": {
                "result": "success",
                "outputs": selection_outputs(
                    host='["test:bazel"]', host_macos='["test:bazel"]'
                ),
            },
            "tests-linux": {"result": "success"},
            "tests-macos": {"result": "skipped"},
        }
        with self.assertRaisesRegex(ValueError, "tests-macos.*skipped"):
            verify_results(needs)
        needs["selection"]["outputs"]["host_macos"] = "[]"
        verify_results(needs)
        needs["tests-macos"]["result"] = "failure"
        with self.assertRaisesRegex(ValueError, "tests-macos.*failure"):
            verify_results(needs)

    def test_source_engine_workflow_output_requires_its_workflow_job(self) -> None:
        needs = {
            "selection": {
                "result": "success",
                "outputs": selection_outputs(source_engine='["source-engine"]'),
            },
            "source-engine": {"result": "skipped"},
        }
        with self.assertRaisesRegex(ValueError, "source-engine.*skipped"):
            verify_results(needs)

    def test_missing_selection_output_is_not_an_empty_task_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing.*quality"):
            verify_results({"selection": {"result": "success", "outputs": {}}})

    def test_missing_selection_and_cancelled_jobs_fail_verification(self) -> None:
        with self.assertRaisesRegex(ValueError, "selection"):
            verify_results({})
        with self.assertRaisesRegex(ValueError, "cancelled"):
            verify_results(
                {
                    "selection": {"result": "success", "outputs": {}},
                    "tests-linux": {"result": "cancelled"},
                },
            )

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

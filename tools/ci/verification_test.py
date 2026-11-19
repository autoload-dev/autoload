"""Regression tests for fail-closed CI selection and the assignment of tasks to lanes."""

import unittest

from tools.ci.verification import LANES, lane_plan, selection_args, verify_results


def selection_outputs(**selected: str) -> dict[str, str]:
    """Use the workflow's output names, including its source_engine mapping."""
    return {**{lane.replace("-", "_"): "[]" for lane in LANES}, **selected}


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
            verify_results(needs, apple_required=False)
        needs["android"]["result"] = "success"
        verify_results(needs, apple_required=False)

    def test_apple_jobs_are_required_only_when_requested(
        self,
    ) -> None:
        needs = {
            "selection": {
                "result": "success",
                "outputs": selection_outputs(ios='["ios"]'),
            },
            "ios": {"result": "skipped"},
        }
        verify_results(needs, apple_required=False)
        with self.assertRaisesRegex(ValueError, "ios.*skipped"):
            verify_results(needs, apple_required=True)
        needs["ios"]["result"] = "failure"
        with self.assertRaisesRegex(ValueError, "ios.*failure"):
            verify_results(needs, apple_required=False)

    def test_source_engine_workflow_output_requires_its_workflow_job(self) -> None:
        needs = {
            "selection": {
                "result": "success",
                "outputs": selection_outputs(source_engine='["source-engine"]'),
            },
            "source-engine": {"result": "skipped"},
        }
        with self.assertRaisesRegex(ValueError, "source-engine.*skipped"):
            verify_results(needs, apple_required=True)

    def test_missing_selection_output_is_not_an_empty_task_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing.*quality"):
            verify_results(
                {"selection": {"result": "success", "outputs": {}}}, apple_required=False
            )

    def test_missing_selection_and_cancelled_jobs_fail_verification(self) -> None:
        with self.assertRaisesRegex(ValueError, "selection"):
            verify_results({}, apple_required=False)
        with self.assertRaisesRegex(ValueError, "cancelled"):
            verify_results(
                {
                    "selection": {"result": "success", "outputs": {}},
                    "tests-linux": {"result": "cancelled"},
                },
                apple_required=False,
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

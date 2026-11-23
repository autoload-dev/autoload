"""Regression tests for CI's plan of every lane and the assignment of tasks to jobs."""

import unittest
from pathlib import Path
from unittest import mock

from tools.ci.verification import (
    JOBS,
    SCHEDULED_LANES,
    excluded_hosts,
    for_host,
    output_name,
    plan_outputs,
    run_tasks,
    verify_results,
    without_scheduled_lanes,
)
from tools.ci.work import LANES, Work

ROOT = Path(__file__).resolve().parents[2]

# Work as the plan sees it: one Android piece, add-on lanes limited to Linux or macOS.
KNOWN = {
    "test:bazel": Work("test:bazel", "host", ".", ("true",), android=True),
    "host:addon:gadget": Work(
        "host:addon:gadget", "host", ".", ("true",), hosts=("macos",)
    ),
    "host:addon:widget": Work(
        "host:addon:widget", "host", ".", ("true",), hosts=("linux",)
    ),
    "ios:addon:widget": Work("ios:addon:widget", "ios", ".", ("true",)),
    "ios": Work("ios", "ios", ".", ("true",)),
}


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
        with mock.patch("tools.ci.work.run") as run:
            run_tasks(["source-engine:full"])
        run.assert_called_once_with(["source-engine:full"])

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

    def test_a_host_lane_limited_to_macos_runs_on_macos_only(self) -> None:
        names = ["test:bazel", "host:addon:gadget"]
        self.assertEqual(for_host(names, "linux", KNOWN), ["test:bazel"])
        self.assertEqual(for_host(names, "macos", KNOWN), names)
        lanes = {lane: [] for lane in LANES} | {"host": names}
        outputs = plan_outputs(lanes, known=KNOWN)
        self.assertEqual(outputs["tests_linux"], ["test:bazel"])
        self.assertEqual(outputs["tests_macos"], names)

    def test_the_plan_says_which_host_jobs_need_the_android_sdk(self) -> None:
        lanes = {lane: [] for lane in LANES} | {"host": ["host:addon:gadget"]}
        self.assertFalse(plan_outputs(lanes, known=KNOWN)["tests_macos_android"])
        lanes["host"].append("test:bazel")
        self.assertTrue(plan_outputs(lanes, known=KNOWN)["tests_linux_android"])
        self.assertTrue(plan_outputs(lanes, known=KNOWN)["tests_macos_android"])

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
        outputs = plan_outputs(lanes, frozenset({"macos"}), KNOWN)
        self.assertEqual(outputs["tests_linux"], ["test:bazel"])
        self.assertEqual(outputs["tests_macos"], [])
        self.assertEqual(outputs["ios"], [])

    def test_the_plan_assigns_each_job_its_lane_on_its_host(self) -> None:
        lanes = {lane: [] for lane in LANES} | {
            "host": ["test:bazel", "host:addon:widget"],
            "ios": ["ios:addon:widget"],
        }
        self.assertEqual(
            plan_outputs(lanes, known=KNOWN),
            {
                "formatting": [],
                "api_docs": [],
                "tests_linux": ["test:bazel", "host:addon:widget"],
                "tests_linux_android": True,
                "tests_macos": ["test:bazel"],
                "tests_macos_android": True,
                "android": [],
                "ios": ["ios:addon:widget"],
            },
        )


if __name__ == "__main__":
    unittest.main()

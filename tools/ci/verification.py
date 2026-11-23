"""
Plan CI's jobs: every lane's work (tools/ci/work.py) on every run, as Bazel's caches make
unchanged work cheap, each job running its lane on its host; then require the planned jobs
to succeed.
"""

import argparse
import json
import os
from pathlib import Path

from tools.ci import work

# CI's jobs, each with the lane whose tasks it runs and the host it runs them on: Linux
# runners or the macos-ci runners. The host lane runs on both hosts. CI's plan job has
# an output for each job, named like it with underscores.
JOBS = {
    "formatting": ("quality", "linux"),
    "api-docs": ("docs", "linux"),
    "tests-linux": ("host", "linux"),
    "tests-macos": ("host", "macos"),
    "android": ("android", "linux"),
    "ios": ("ios", "macos"),
}
# The host jobs, which say in <output>_android whether their tasks need the Android SDK.
HOST_JOBS = tuple(job for job, (lane, _) in JOBS.items() if lane == "host")
# The host of the self-hosted runners. They keep caches and the BuildBuddy executor's key,
# so they run no code from a fork's pull request; the merge queue runs its lanes there.
SELF_HOSTED = "macos"


# Lanes that CI leaves to the Source engine workflow, which runs them on a schedule and on
# its own dispatch: building engines from source is the most expensive work and the least
# likely to change with a commit.
SCHEDULED_LANES = ("source-engine",)


def without_scheduled_lanes(lanes: dict[str, list[str]]) -> dict[str, list[str]]:
    """Leave out the tasks of the lanes that only the Source engine workflow runs."""
    return {
        lane: [] if lane in SCHEDULED_LANES else tasks for lane, tasks in lanes.items()
    }


def output_name(job: str) -> str:
    """The plan output of a job."""
    return job.replace("-", "_")


def planned_tasks(outputs: dict, job: str) -> list[str]:
    """Read one plan output; a missing or malformed one is not an empty plan."""
    name = output_name(job)
    if name not in outputs:
        raise ValueError(f"missing plan output: {name}")
    tasks = json.loads(outputs[name])
    if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
        raise ValueError(f"{job}: invalid planned task list")
    return tasks


def required_jobs(outputs: dict) -> list[str]:
    """Name the jobs the plan requires: those with tasks."""
    return [job for job in JOBS if planned_tasks(outputs, job)]


def failed_jobs(needs: dict) -> list[str]:
    """Name the jobs that neither succeeded nor were skipped, with their results."""
    return [
        f"{workflow_job}: {result.get('result', 'missing')}"
        for workflow_job, result in needs.items()
        if result.get("result") not in {"success", "skipped"}
    ]


def verify_results(needs: dict) -> None:
    """Require every job that CI's plan requires to succeed."""
    plan = needs.get("plan", {})
    if plan.get("result") != "success":
        raise ValueError("the plan did not succeed")
    if failures := failed_jobs(needs):
        raise ValueError(f"{failures[0]} verification result")
    for workflow_job in required_jobs(plan.get("outputs", {})):
        result = needs.get(workflow_job, {}).get("result", "missing")
        if result != "success":
            raise ValueError(
                f"{workflow_job}: {result}; planned verification must succeed"
            )


def for_host(names: list[str], host: str, known: dict[str, work.Work]) -> list[str]:
    """The work a host runs of a lane: all but the add-on lanes limited to other hosts."""
    return [name for name in names if work.runs_on(known[name], host)]


def run_tasks(tasks: object) -> None:
    """Run the work of one plan output in order."""
    if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
        raise ValueError("Expected a JSON array of work names")
    work.run(tasks)


def excluded_hosts(event_name: str, event: dict) -> frozenset[str]:
    """The hosts that may not run this event's code: a fork's pull request stays off the
    self-hosted runners."""
    if event_name != "pull_request":
        return frozenset()
    head_repo = event["pull_request"]["head"].get("repo") or {}
    if head_repo.get("full_name") == event["repository"]["full_name"]:
        return frozenset()
    return frozenset({SELF_HOSTED})


def plan_outputs(
    lanes: dict[str, list[str]],
    excluded: frozenset[str] = frozenset(),
    known: dict[str, work.Work] | None = None,
) -> dict[str, object]:
    """
    CI's plan outputs: each job's work, that of its lane on its host, none on an excluded
    host, and whether a host job needs the Android SDK.
    """
    known = known or work.all_work()
    outputs: dict[str, object] = {}
    for job, (lane, host) in JOBS.items():
        names = [] if host in excluded else for_host(lanes[lane], host, known)
        outputs[output_name(job)] = names
        if job in HOST_JOBS:
            outputs[f"{output_name(job)}_android"] = any(
                known[name].android for name in names
            )
    return outputs


def write_plan() -> None:
    """Write CI's plan for this run to GITHUB_OUTPUT."""
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    lanes = without_scheduled_lanes(work.lanes())
    outputs = plan_outputs(lanes, excluded_hosts(event_name, event))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.writelines(
            f"{name}={json.dumps(value)}\n" for name, value in outputs.items()
        )
    print(json.dumps(outputs, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="Write CI's planned tasks to GITHUB_OUTPUT")
    commands.add_parser("verify", help="Require CI's planned jobs to succeed")
    run = commands.add_parser("run", help="Run one planned JSON task array")
    run.add_argument("tasks")
    args = parser.parse_args()
    if args.command == "verify":
        verify_results(json.loads(os.environ["VERIFICATION_NEEDS"]))
    elif args.command == "run":
        run_tasks(json.loads(args.tasks))
    else:
        write_plan()


if __name__ == "__main__":
    main()

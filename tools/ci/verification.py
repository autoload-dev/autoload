"""Select CI work from hk's plan; path policy remains in hk.pkl."""

import argparse
import json
import os
import subprocess
from pathlib import Path

# Every lane; the profile lanes are opt-in through the hk profile of the same name.
LANES = ("quality", "docs", "host", "source-engine", "android", "ios")
PROFILE_LANES = ("host", "source-engine", "android", "ios")

# The workflow job that runs each lane's tasks, by workflow: CI runs the lanes that Linux
# runners can run, the Apple workflow those that need a macOS runner. The host lane runs on
# both hosts. A workflow's selection job has an output for each of its lanes.
WORKFLOW_JOBS = {
    "ci": {
        "quality": "formatting",
        "docs": "api-docs",
        "host": "tests-linux",
        "android": "android",
    },
    "apple": {
        "host": "tests-macos",
        "source-engine": "source-engine",
        "ios": "ios",
    },
}
# The job with which CI calls the Apple workflow, and CI's selection output that says
# whether this run calls it.
APPLE_JOB = "apple"


def runs_apple(lanes: dict[str, list[str]], event_name: str) -> bool:
    """Say whether a CI run calls the Apple workflow.

    A pull request's run leaves it out: the merge queue runs it, and the ci:macos label
    starts it for a pull request. Every other event calls it when an Apple lane is selected.
    """
    return event_name != "pull_request" and any(
        lanes[lane] for lane in WORKFLOW_JOBS["apple"]
    )


def selected_tasks(outputs: dict, lane: str) -> list[str]:
    """Read one selection output; a missing or malformed one is not an empty selection."""
    output_name = lane.replace("-", "_")
    if output_name not in outputs:
        raise ValueError(f"missing selection output: {output_name}")
    tasks = json.loads(outputs[output_name])
    if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
        raise ValueError(f"{lane}: invalid selected task list")
    return tasks


def required_jobs(workflow: str, outputs: dict) -> list[str]:
    """Name the jobs a workflow's selection requires: those of its lanes with tasks."""
    jobs = [
        workflow_job
        for lane, workflow_job in WORKFLOW_JOBS[workflow].items()
        if selected_tasks(outputs, lane)
    ]
    if workflow == "ci":
        if outputs.get(APPLE_JOB) not in {"true", "false"}:
            raise ValueError(f"missing selection output: {APPLE_JOB}")
        if outputs[APPLE_JOB] == "true":
            jobs.append(APPLE_JOB)
    return jobs


def failed_jobs(needs: dict) -> list[str]:
    """Name the jobs that neither succeeded nor were skipped, with their results."""
    return [
        f"{workflow_job}: {result.get('result', 'missing')}"
        for workflow_job, result in needs.items()
        if result.get("result") not in {"success", "skipped"}
    ]


def verify_results(workflow: str, needs: dict) -> None:
    """Require every job that a workflow's selection requires to succeed."""
    selection = needs.get("selection", {})
    if selection.get("result") != "success":
        raise ValueError("selection did not succeed")
    if failures := failed_jobs(needs):
        raise ValueError(f"{failures[0]} verification result")
    for workflow_job in required_jobs(workflow, selection.get("outputs", {})):
        result = needs.get(workflow_job, {}).get("result", "missing")
        if result != "success":
            raise ValueError(
                f"{workflow_job}: {result}; selected verification must succeed"
            )


# Examples whose suites need a lane other than host, as hk.pkl's exampleProfiles says:
# Petri's editor and runtime are built from the engine sources.
EXAMPLE_LANES = {"petri": "source-engine"}


def lane_for(task: str) -> str:
    """Assign a selected mise task to its lane."""
    if task in {
        "lint",
        "lint:ci",
        "conventions:code",
        "conventions:docs",
        "test:selection",
        "test:setup",
    }:
        return "quality"
    if task in {"docs", "source-engine", "android", "ios"}:
        return task
    if task.startswith("contracts:") and task.removeprefix("contracts:") in PROFILE_LANES:
        return task.removeprefix("contracts:")
    # The add-on modules' tasks: test:addon:<module>, android:addon:<module> and
    # ios:addon:<module>.
    if ":addon:" in task:
        lane = task.partition(":addon:")[0]
        return "host" if lane == "test" else lane
    if task.startswith("test:example:"):
        return EXAMPLE_LANES.get(task.removeprefix("test:example:"), "host")
    if task in {
        "test:bazel",
        "test:regressions",
        "test:gdextension",
    }:
        return "host"
    raise ValueError(f"No lane for selected task: {task}")


def lane_plan(plan: dict) -> dict[str, list[str]]:
    """Retain hk's order and fail closed on unfamiliar plan statuses or steps."""
    lanes: dict[str, list[str]] = {name: [] for name in LANES}
    for step in plan["steps"]:
        status = step["status"]
        if status == "skipped":
            continue
        if status != "included":
            raise ValueError(f"Unexpected hk plan status: {status}")
        task = step["name"]
        lanes[lane_for(task)].append(task)
    return lanes


def selection_args(event_name: str, event: dict) -> list[str]:
    """Compare PR merge contents, a merge group or pushed changes; dispatch checks all."""
    if event_name == "workflow_dispatch":
        return ["--all"]
    if event_name == "pull_request":
        return ["--from-ref", event["pull_request"]["base"]["sha"], "--to-ref", "HEAD"]
    if event_name == "merge_group":
        # The group's parent: the base branch, or the group queued before this one.
        return ["--from-ref", event["merge_group"]["base_sha"], "--to-ref", "HEAD"]
    if event_name == "push":
        before = event["before"]
        if before and set(before) != {"0"}:
            return ["--from-ref", before, "--to-ref", "HEAD"]
        return ["--all"]
    raise ValueError(f"Unsupported verification event: {event_name}")


def run_tasks(tasks: object) -> None:
    """Run the mise tasks of one selection output in order."""
    if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
        raise ValueError("Expected a JSON array of mise task names")
    for task in tasks:
        lane_for(task)
    for task in tasks:
        subprocess.run(["mise", "run", task], check=True)


def write_plan(workflow: str) -> None:
    """Write the tasks of each of a workflow's lanes for this run to GITHUB_OUTPUT."""
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    command = ["hk"]
    for lane in PROFILE_LANES:
        command.extend(["--profile", lane])
    command.extend(["check", "--plan", "--json"])
    command.extend(selection_args(event_name, event))
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
    lanes = lane_plan(json.loads(result.stdout))
    outputs: dict[str, object] = {lane: lanes[lane] for lane in WORKFLOW_JOBS[workflow]}
    if workflow == "ci":
        outputs[APPLE_JOB] = runs_apple(lanes, event_name)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.writelines(
            f"{name}={json.dumps(value)}\n" for name, value in outputs.items()
        )
    print(json.dumps(outputs, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser(
        "plan", help="Write the selected tasks of a workflow's lanes to GITHUB_OUTPUT"
    )
    verify = commands.add_parser(
        "verify", help="Require a workflow's selected jobs to succeed"
    )
    for command in (plan, verify):
        command.add_argument("workflow", choices=sorted(WORKFLOW_JOBS))
    run = commands.add_parser("run", help="Run one selected JSON task array")
    run.add_argument("tasks")
    args = parser.parse_args()
    if args.command == "verify":
        verify_results(args.workflow, json.loads(os.environ["VERIFICATION_NEEDS"]))
    elif args.command == "run":
        run_tasks(json.loads(args.tasks))
    else:
        write_plan(args.workflow)


if __name__ == "__main__":
    main()

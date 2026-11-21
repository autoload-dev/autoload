"""Select CI work from hk's plan; path policy remains in hk.pkl."""

import argparse
import json
import os
import subprocess
from pathlib import Path

# Every lane; the profile lanes are opt-in through the hk profile of the same name.
LANES = ("quality", "docs", "host", "source-engine", "android", "ios")
PROFILE_LANES = ("host", "source-engine", "android", "ios")

# The workflow job that runs each selection output's tasks. An output carries its lane's
# tasks; the host lane runs on both hosts and has an output for each.
WORKFLOW_JOBS = {
    "quality": "formatting",
    "docs": "api-docs",
    "host": "tests-linux",
    "host-macos": "tests-macos",
    "source-engine": "source-engine",
    "android": "android",
    "ios": "ios",
}
# The outputs whose jobs need a macOS runner.
APPLE_OUTPUTS = ("host-macos", "source-engine", "ios")


def job_plan(
    lanes: dict[str, list[str]], event_name: str, *, apple_only: bool
) -> dict[str, list[str]]:
    """Give each selection output the tasks its job runs in this run.

    A pull request's run leaves out the Apple jobs, which the merge queue runs; the pull
    request's macOS preview runs only them. Every other event runs all selected jobs.
    """

    def runs(output: str) -> bool:
        if apple_only:
            return output in APPLE_OUTPUTS
        return event_name != "pull_request" or output not in APPLE_OUTPUTS

    return {
        output: lanes["host" if output == "host-macos" else output]
        if runs(output)
        else []
        for output in WORKFLOW_JOBS
    }


def selected_tasks(outputs: dict, output: str) -> list[str]:
    """Read one selection output; a missing or malformed one is not an empty selection."""
    output_name = output.replace("-", "_")
    if output_name not in outputs:
        raise ValueError(f"missing selection output: {output_name}")
    tasks = json.loads(outputs[output_name])
    if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
        raise ValueError(f"{output}: invalid selected task list")
    return tasks


def failed_jobs(needs: dict) -> list[str]:
    """Name the jobs that neither succeeded nor were skipped, with their results."""
    return [
        f"{workflow_job}: {result.get('result', 'missing')}"
        for workflow_job, result in needs.items()
        if result.get("result") not in {"success", "skipped"}
    ]


def unsatisfied_jobs(needs: dict, outputs: dict) -> list[str]:
    """Name the jobs of selection outputs with tasks that did not succeed, with their results."""
    return [
        f"{workflow_job}: {result}"
        for output, workflow_job in WORKFLOW_JOBS.items()
        for result in [needs.get(workflow_job, {}).get("result", "missing")]
        if selected_tasks(outputs, output) and result != "success"
    ]


def verify_results(needs: dict) -> None:
    """Require the job of every selection output with tasks to succeed."""
    selection = needs.get("selection", {})
    if selection.get("result") != "success":
        raise ValueError("selection did not succeed")
    if failures := failed_jobs(needs):
        raise ValueError(f"{failures[0]} verification result")
    if failures := unsatisfied_jobs(needs, selection.get("outputs", {})):
        raise ValueError(f"{failures[0]}; selected verification must succeed")


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


def write_plan() -> None:
    """Write each job's tasks for this workflow run to GITHUB_OUTPUT."""
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    command = ["hk"]
    for lane in PROFILE_LANES:
        command.extend(["--profile", lane])
    command.extend(["check", "--plan", "--json"])
    command.extend(selection_args(event_name, event))
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
    jobs = job_plan(
        lane_plan(json.loads(result.stdout)),
        event_name,
        apple_only=os.environ.get("VERIFICATION_APPLE_ONLY") == "true",
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.writelines(f"{name}={json.dumps(tasks)}\n" for name, tasks in jobs.items())
    print(json.dumps(jobs, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="Write each job's selected tasks to GITHUB_OUTPUT")
    commands.add_parser("verify", help="Require selected workflow jobs to succeed")
    run = commands.add_parser("run", help="Run one selected JSON task array")
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

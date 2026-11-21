"""Select CI work from hk's plan; path policy remains in hk.pkl."""

import argparse
import json
import os
import subprocess
from pathlib import Path

# Every lane; the profile lanes are opt-in through the hk profile of the same name.
LANES = ("quality", "docs", "host", "source-engine", "android", "ios")
PROFILE_LANES = ("host", "source-engine", "android", "ios")


def verify_results(needs: dict, *, apple_required: bool) -> None:
    """Require selected lanes; Apple lanes only when the event runs them."""
    selection = needs.get("selection", {})
    if selection.get("result") != "success":
        raise ValueError("selection did not succeed")
    for workflow_job, result in needs.items():
        if result.get("result") not in {"success", "skipped"}:
            raise ValueError(
                f"{workflow_job}: {result.get('result', 'missing')} verification result"
            )
    # The workflow jobs that run each lane.
    workflow_jobs = {
        "quality": ("formatting",),
        "docs": ("api-docs",),
        "host": ("tests-linux", "tests-macos") if apple_required else ("tests-linux",),
        "source-engine": ("source-engine",) if apple_required else (),
        "android": ("android",),
        "ios": ("ios",) if apple_required else (),
    }
    for lane, required in workflow_jobs.items():
        output_name = lane.replace("-", "_")
        outputs = selection.get("outputs", {})
        if output_name not in outputs:
            raise ValueError(f"missing selection output: {output_name}")
        tasks = json.loads(outputs[output_name])
        if not isinstance(tasks, list) or not all(
            isinstance(task, str) for task in tasks
        ):
            raise ValueError(f"{lane}: invalid selected task list")
        if not tasks:
            continue
        for workflow_job in required:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="Write each lane's selected tasks to GITHUB_OUTPUT")
    verify = commands.add_parser(
        "verify", help="Require selected workflow jobs to succeed"
    )
    verify.add_argument("--apple-required", action="store_true")
    run = commands.add_parser("run", help="Run one selected JSON task array")
    run.add_argument("tasks")
    args = parser.parse_args()
    if args.command == "verify":
        verify_results(
            json.loads(os.environ["VERIFICATION_NEEDS"]),
            apple_required=args.apple_required,
        )
        return
    if args.command == "run":
        tasks = json.loads(args.tasks)
        if not isinstance(tasks, list) or not all(
            isinstance(task, str) for task in tasks
        ):
            raise ValueError("Expected a JSON array of mise task names")
        for task in tasks:
            lane_for(task)
        for task in tasks:
            subprocess.run(["mise", "run", task], check=True)
        return

    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    command = ["hk"]
    for lane in PROFILE_LANES:
        command.extend(["--profile", lane])
    command.extend(["check", "--plan", "--json"])
    command.extend(selection_args(os.environ["GITHUB_EVENT_NAME"], event))
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
    lanes = lane_plan(json.loads(result.stdout))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        for lane, tasks in lanes.items():
            output.write(f"{lane}={json.dumps(tasks)}\n")
    print(json.dumps(lanes, indent=2))


if __name__ == "__main__":
    main()

"""
Plan CI's work: every task of every lane, on every run, as Bazel's caches make unchanged
work cheap. The lanes come from mise.toml's tasks and the add-on modules' manifests
(addon.pkl).
"""

import argparse
import json
import os
import subprocess
import tomllib
from pathlib import Path

from tools.addons.modules import HOSTS as ADDON_HOSTS
from tools.addons.modules import LANES as ADDON_LANES
from tools.addons.modules import all_modules

ROOT = Path(__file__).resolve().parents[2]

LANES = ("quality", "docs", "host", "source-engine", "android", "ios")
# The lanes that need a machine of their own, each with API contract cases: contracts:<lane>.
CONTRACT_LANES = ("host", "source-engine", "android", "ios")
# The target of the add-on generator's self-test in a task name: <lane>:addon-template.
TEMPLATE = "-template"

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


# Examples whose suites need a lane other than host: Petri's editor and runtime are built
# from the engine sources.
EXAMPLE_LANES = {"petri": "source-engine"}


# Tasks named for themselves, by lane.
TASK_LANES = {
    **dict.fromkeys(
        (
            "lint",
            "lint:ci",
            "conventions",
            "test:setup",
            "test:tools",
        ),
        "quality",
    ),
    **{lane: lane for lane in ("docs", "source-engine", "android", "ios")},
    # Every source-engine case, the only source-engine task CI runs, in the Source engine
    # workflow.
    "source-engine:full": "source-engine",
    **dict.fromkeys(("test:bazel", "test:regressions", "test:gdextension"), "host"),
}


# mise.toml's tasks that no lane plans: setup and tools, the parts and aggregates of lane
# tasks, the generic add-on tasks that the add-on modules' lane tasks run, and inspections
# of artifacts a lane already built. Every other task needs a lane, so a new one cannot
# silently stay out of CI.
OTHER_TASKS = frozenset(
    {
        "bootstrap",
        "setup",
        "format",
        "code-health",
        "android:setup",
        "addon:new",
        "test:examples",
        "test:full",
        "ios:apps",
        "ios:examples",
        "android:apps",
        "android:examples",
        "inspect:mobile",
        "addon:host",
        "addon:android",
        "addon:ios",
        "addon:template",
    }
)


def _family_lane(task: str) -> str | None:
    """The lane of a task of a family: contracts, examples and add-on modules."""
    if (
        task.startswith("contracts:")
        and task.removeprefix("contracts:") in CONTRACT_LANES
    ):
        return task.removeprefix("contracts:")
    if task.startswith("test:example:"):
        return EXAMPLE_LANES.get(task.removeprefix("test:example:"), "host")
    # The add-on modules' tasks are named <lane>:addon:<module>, and the generator's self-test
    # <lane>:addon-template.
    if (addon := addon_task(task)) is not None:
        return addon[0]
    return None


def addon_task(task: str) -> tuple[str, str | None, tuple[str, ...]] | None:
    """
    Split an add-on task into its lane, its module and the hosts it is limited to, which
    its name ends in: `host:addon:<module>@macos`. The self-test, `<lane>:addon-template`,
    has no module.
    """
    lane, separator, rest = task.partition(":addon")
    if not separator or lane not in ADDON_LANES:
        return None
    target, _, listed = rest.partition("@")
    hosts = tuple(listed.split(",")) if listed else ()
    if target == TEMPLATE:
        return lane, None, hosts
    if not target.startswith(":") or not target[1:]:
        return None
    return lane, target[1:], hosts


def task_command(task: str) -> list[str]:
    """The command of a planned task."""
    addon = addon_task(task)
    if addon is None:
        return ["mise", "run", task]
    lane, module, _ = addon
    if module is None:
        return ["mise", "run", "addon:template", lane]
    return ["mise", "run", f"addon:{lane}", module]


def for_host(tasks: list[str], host: str) -> list[str]:
    """The tasks but the add-on tasks whose host lane excludes this host."""

    def runs_here(task: str) -> bool:
        addon = addon_task(task)
        return addon is None or not addon[2] or host in addon[2]

    return [task for task in tasks if runs_here(task)]


def lane_for(task: str) -> str:
    """Assign a planned mise task to its lane."""
    lane = TASK_LANES.get(task) or _family_lane(task)
    if lane is None:
        raise ValueError(f"No lane for task: {task}")
    return lane


def addon_task_name(lane: str, module: str | None, hosts: tuple[str, ...]) -> str:
    """
    The task of an add-on module's lane, `<lane>:addon:<module>`, or of the generator's
    self-test, `<lane>:addon-template`. A host lane limited to some hosts names them, so that
    the plan leaves it out of other hosts' runners.
    """
    target = f":{module}" if module else TEMPLATE
    limited = lane == "host" and set(hosts) != set(ADDON_HOSTS)
    return f"{lane}:addon{target}" + (f"@{','.join(hosts)}" if limited else "")


def addon_tasks(root: Path = ROOT) -> list[str]:
    """
    Each add-on module's lanes, as its addon.pkl names them, and the generator's self-test
    in every lane. The self-test's desktop build does the same on every host, so its host
    lane runs on Linux only.
    """
    tasks = [
        addon_task_name(lane, module.directory, module.hosts)
        for module in all_modules(root)
        for lane in module.lanes
    ]
    return tasks + [
        addon_task_name(lane, None, ("linux",) if lane == "host" else ADDON_HOSTS)
        for lane in ADDON_LANES
    ]


def all_lanes(root: Path = ROOT) -> dict[str, list[str]]:
    """
    Every task CI runs, by lane: mise.toml's tasks but OTHER_TASKS, and the add-on modules'
    lanes. A task with no lane fails the plan.
    """
    tasks = mise_tasks(root)
    lanes: dict[str, list[str]] = {name: [] for name in LANES}
    for task in [
        *(name for name in tasks if name not in OTHER_TASKS),
        *addon_tasks(root),
    ]:
        lanes[lane_for(task)].append(task)
    return lanes


def run_tasks(tasks: object) -> None:
    """Run the mise tasks of one plan output in order."""
    if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
        raise ValueError("Expected a JSON array of mise task names")
    for task in tasks:
        lane_for(task)
    for task in tasks:
        subprocess.run(task_command(task), check=True)


def mise_tasks(root: Path = ROOT) -> dict[str, dict]:
    """mise.toml's tasks, by name."""
    return tomllib.loads((root / "mise.toml").read_text())["tasks"]


def android_tasks(root: Path = ROOT) -> frozenset[str]:
    """The mise tasks that provision the Android SDK first: those of mise.toml's android template."""
    tasks = mise_tasks(root)
    return frozenset(
        name
        for name, task in tasks.items()
        if task.get("extends") == "android" or "android:setup" in task.get("depends", [])
    )


def needs_android(tasks: list[str], android: frozenset[str]) -> bool:
    """Whether a job's tasks need the Android SDK, so that its setup restores it."""
    return any(task_command(task)[2] in android for task in tasks)


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
    lanes: dict[str, list[str]], excluded: frozenset[str] = frozenset()
) -> dict[str, object]:
    """
    CI's plan outputs: each job's tasks, those of its lane on its host, none on an
    excluded host, and whether a host job needs the Android SDK.
    """
    android = android_tasks()
    outputs: dict[str, object] = {}
    for job, (lane, host) in JOBS.items():
        tasks = [] if host in excluded else for_host(lanes[lane], host)
        outputs[output_name(job)] = tasks
        if job in HOST_JOBS:
            outputs[f"{output_name(job)}_android"] = needs_android(tasks, android)
    return outputs


def write_plan() -> None:
    """Write CI's plan for this run to GITHUB_OUTPUT."""
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    lanes = without_scheduled_lanes(all_lanes())
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

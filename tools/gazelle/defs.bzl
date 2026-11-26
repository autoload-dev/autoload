"""The Gazelle targets of the repository's modules."""

load("@gazelle//:def.bzl", "gazelle")
load("@rules_multirun//:defs.bzl", "multirun")

def module_gazelle(name, directory, languages):
    """
    Gazelle for the module in directory.

    `name` updates its BUILD files, `<name>_check` fails with the diff where one differs from
    what Gazelle generates. Each language runs on its own, with its own arguments, since Gazelle's exclusions apply to
    every language of a run; a module with several languages runs them one after another.

    Args:
      name: The update target's name; the check's is `<name>_check`.
      directory: The module's directory, relative to the repository's root.
      languages: The Gazelle languages to run, each with its extra arguments, such as
        exclusions.
    """
    for mode, suffix in (("fix", ""), ("diff", "_check")):
        runs = []
        for language, extra in languages.items():
            run = name + suffix if len(languages) == 1 else "%s.%s%s" % (name, language, suffix)
            gazelle(
                name = run,
                args = ["-repo_root=" + directory, "-lang=" + language] + extra + [directory],
                gazelle = Label(":gazelle_binary"),
                mode = mode,
            )
            runs.append(run)
        if len(languages) > 1:
            multirun(name = name + suffix, commands = runs)

def addon_gazelles(name, repositories):
    """
    Gazelle for each add-on module, which declares the lint check's filegroups.

    It runs as `<name>.<directory>` and `<name>.<directory>_check`, and for all add-on modules
    as `<name>` and `<name>_check`.

    Args:
      name: The prefix of the targets.
      repositories: The add-on modules' repositories, such as `@autoload_sqlite`, whose
        directories are `addons/<directory>`.
    """
    directories = [repository.removeprefix("@autoload_") for repository in repositories]
    for directory in directories:
        module_gazelle(
            name = "%s.%s" % (name, directory),
            directory = "addons/" + directory,
            languages = {"lint": []},
        )
    for suffix in ("", "_check"):
        multirun(
            name = name + suffix,
            commands = ["%s.%s%s" % (name, directory, suffix) for directory in directories],
        )

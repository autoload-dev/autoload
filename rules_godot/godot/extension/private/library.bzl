"""
The extension library of one configuration: which library the target's providers supply,
whether the configuration's operating system can load it, and where its runtime files lie
beside it.

Sections: Library classification, Library placement, Configuration.
"""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load("@rules_apple//apple:providers.bzl", "AppleDynamicFrameworkInfo", "AppleFrameworkImportInfo")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot/private:paths.bzl", "resource_path")
load("//godot/private:symbols.bzl", "linked_dsym")
load("//godot/private:variant.bzl", "variant")
load("//godot/private/config:settings.bzl", "CPU_TABLE", "OPERATING_SYSTEM_CONSTRAINTS", "target_platform")

visibility("private")

# ==== Library classification ==================================================

_SHARED = "a shared library (cc_shared_library, cc_import(shared_library), cc_binary(linkshared), one .%s)"

_FRAMEWORK = "a dynamic framework (apple_dynamic_xcframework_import, apple_dynamic_framework_import)"

# What each operating system's runtime loads: the link kinds, the file suffixes of its
# shared libraries, and the accepted forms for diagnostics.
_LOADABLE = {
    "linux": struct(kinds = ["dynamic"], suffixes = ["so"], versioned = True, accepted = _SHARED % "so"),
    # The package manager extracts only lib/<abi>/*.so.
    "android": struct(kinds = ["dynamic"], suffixes = ["so"], versioned = False, accepted = _SHARED % "so"),
    "macos": struct(
        kinds = ["dynamic", "framework"],
        suffixes = ["dylib", "so"],
        versioned = True,
        accepted = _SHARED % "dylib" + " or " + _FRAMEWORK,
    ),
    "ios": struct(
        kinds = ["static", "framework"],
        suffixes = [],
        versioned = False,
        accepted = "a static library (cc_library, cc_import(static_library), apple_static_xcframework_import) or " + _FRAMEWORK,
    ),
}

def _context_name(context):
    return " ".join([part for part in [
        context.operating_system,
        context.cpu,
        context.environment,
        "tool configuration" if context.tool else "",
    ] if part])

def _dynamic_file(library):
    """The shared library a library to link loads, under its own name."""
    return library.resolved_symlink_dynamic_library or library.dynamic_library

def _is_shared_library(file, suffixes = ["so", "dylib"], versioned = True):
    return file.extension in suffixes or (versioned and "so" in suffixes and ".so." in file.basename)

def _framework_binary(directory, files):
    """The framework's binary, named after it at its root, or None."""
    path = directory + "/" + directory.rsplit("/", 1)[-1].removesuffix(".framework")
    binaries = [file for file in files if file.path == path]
    return binaries[0] if binaries else None

def _framework_binaries(frameworks):
    """The binaries of the frameworks, which _framework_files groups."""
    return [
        binary
        for directory, files in frameworks.items()
        for binary in [_framework_binary(directory, files)]
        if binary
    ]

def _linked_libraries(target):
    """Return the libraries of the target's own CcInfo linker input, and those of other owners."""
    linker_inputs = target[CcInfo].linking_context.linker_inputs.to_list() if CcInfo in target else []
    return struct(
        own = [library for linker_input in linker_inputs if linker_input.owner == target.label for library in linker_input.libraries],
        others = [linker_input for linker_input in linker_inputs if linker_input.owner != target.label],
    )

def _framework_library(ctx, target, linked, frameworks):
    """
    Return the dynamic framework of an Apple import, or None.

    Its binary is the one the import links or, with bundle_only, which links nothing,
    the binary of the one framework among frameworks.
    """
    binaries = [_dynamic_file(library) for library in linked.own if library.dynamic_library] or _framework_binaries(frameworks)
    if len(binaries) > 1 and not linked.own:
        fail((
            "%s: %s bundles the frameworks %s and links none, so the extension cannot " +
            "tell its library from their dependencies; import each dependency on its own " +
            "and list it in the extension's platform_deps"
        ) % (ctx.label, target.label, sorted([binary.basename + ".framework" for binary in binaries])))
    if len(binaries) != 1:
        return None
    return struct(link_kind = "framework", file = binaries[0], cc_info = target[CcInfo], linker_inputs = linked.others)

def _linked_library(target, linked):
    """Return the static or dynamic library the target's CcInfo links as its own, or None."""
    if len(linked.own) != 1:
        return None
    library = linked.own[0]
    if library.dynamic_library:
        return struct(link_kind = "dynamic", file = _dynamic_file(library), cc_info = None, linker_inputs = linked.others)
    archive = library.static_library or library.pic_static_library
    if archive:
        return struct(link_kind = "static", file = archive, cc_info = target[CcInfo], linker_inputs = linked.others)
    return None

def _shared_file_library(target):
    """Return the one shared library among the target's files, as cc_binary(linkshared) has it, or None."""
    files = [file for file in target[DefaultInfo].files.to_list() if _is_shared_library(file)]
    if len(files) != 1:
        return None
    return struct(link_kind = "dynamic", file = files[0], cc_info = None, linker_inputs = None)

def _provided_library(ctx, target, frameworks):
    """Return the link kind and file of the library the target's providers supply, or None."""
    linked = _linked_libraries(target)
    if AppleDynamicFrameworkInfo in target:
        return _framework_library(ctx, target, linked, frameworks)
    return _linked_library(target, linked) or _shared_file_library(target)

def _require_loadable(ctx, target, context, classified):
    """Fail unless the operating system of the context can load the classified library."""
    loadable = _LOADABLE[context.operating_system]
    if classified.link_kind not in loadable.kinds:
        fail("%s: %s is a %s library, which %s cannot load; expected %s" % (
            ctx.label,
            target.label,
            classified.link_kind,
            _context_name(context),
            loadable.accepted,
        ))
    if classified.link_kind == "dynamic" and not _is_shared_library(classified.file, loadable.suffixes, loadable.versioned):
        fail("%s: %s supplies %s, which %s cannot load; expected %s" % (
            ctx.label,
            target.label,
            classified.file.basename,
            _context_name(context),
            loadable.accepted,
        ))

def _classify(ctx, target, context, frameworks):
    """
    Return the link kind and file of the configured library, from its providers.

    The library is one the context's operating system can load, as _LOADABLE lists them.
    frameworks is the import's _framework_files.
    """
    classified = _provided_library(ctx, target, frameworks)
    if not classified:
        fail("%s: %s supplies no extension library for %s; expected %s, got %s" % (
            ctx.label,
            target.label,
            _context_name(context),
            _LOADABLE[context.operating_system].accepted,
            [file.basename for file in target[DefaultInfo].files.to_list()],
        ))
    _require_loadable(ctx, target, context, classified)
    return classified

def _own_framework(ctx, target, binary, frameworks):
    """
    Return the directory of the framework whose binary the extension loads.

    Args:
        ctx: Rule context of the extension.
        target: The Apple import.
        binary: The framework binary of the configured library.
        frameworks: The import's _framework_files.

    Returns:
        The directory among frameworks whose binary is binary.
    """
    own = [
        directory
        for directory, files in frameworks.items()
        if _framework_binary(directory, files) == binary
    ]
    if len(own) != 1:
        fail("%s: %s bundles no framework %s.framework with its binary" % (ctx.label, target.label, binary.basename))
    return own[0]

def _dependency_libraries(target, classified):
    """The shared libraries a dynamic library needs at run time, its own excluded."""
    if classified.link_kind != "dynamic":
        return []
    if classified.linker_inputs != None:
        # The shared libraries the library's CcInfo links, as cc_import's deps.
        return [
            _dynamic_file(library)
            for linker_input in classified.linker_inputs
            for library in linker_input.libraries
            if library.dynamic_library
        ]

    # A shared library a rule linked, as cc_binary(linkshared) or cc_shared_library,
    # carries the shared libraries of its deps in its runfiles. A file of the library's
    # own name is the library itself: cc_shared_library holds a second copy under _solib.
    return [
        file
        for file in target[DefaultInfo].default_runfiles.files.to_list()
        if _is_shared_library(file) and file.basename != classified.file.basename
    ]

# ==== Library placement =======================================================

def _framework_directory(file):
    """The path of the .framework directory that contains file, or None."""
    parts = file.path.split("/")
    for index in range(len(parts) - 1, -1, -1):
        if parts[index].endswith(".framework"):
            return "/".join(parts[:index + 1])
    return None

def _framework_files(target):
    """The files of each framework an Apple import bundles, by framework directory."""
    files = {}
    if AppleFrameworkImportInfo in target:
        for file in target[AppleFrameworkImportInfo].framework_imports.to_list():
            directory = _framework_directory(file)
            if directory:
                files.setdefault(directory, []).append(file)
    return files

def _placement(ctx, context, prefix):
    """Where the runtime files of one configured extension library go, beside the library."""
    return struct(
        label = ctx.label,
        context = _context_name(context),
        directory = prefix + "bin/" + context.tags + "/",
        resource_paths = {},
    )

def _place_at(placement, path, file):
    """Place file at the resource path path and return it."""
    if path in placement.resource_paths:
        fail("%s: two runtime files of %s lie at res://%s" % (placement.label, placement.context, path))
    placement.resource_paths[path] = file
    return path

def _place(placement, name, file):
    """Place file under name beside the extension library and return its resource path."""
    if placement.directory + name in placement.resource_paths:
        fail("%s: two runtime files of %s are named %s; extension libraries load their dependencies by name from beside them" % (
            placement.label,
            placement.context,
            name,
        ))
    return _place_at(placement, placement.directory + name, file)

def _place_framework(placement, frameworks, own):
    """Place the files of every framework; return the resource paths of those but own."""
    dependency_paths = []
    for framework, files in frameworks.items():
        name = framework.rsplit("/", 1)[-1]
        for file in files:
            _place(placement, name + file.path[len(framework):], file)
        if framework != own:
            dependency_paths.append(placement.directory + name)
    return dependency_paths

def _archive_file(ctx, context, classified):
    """Return the classified library's file, a static library as an archive named .a."""
    file = classified.file
    if classified.link_kind != "static" or file.extension == "a":
        return file

    # rules_cc names alwayslink archives .lo, and a static framework's binary has no
    # suffix. Godot resolves an iOS entry symbol in the executable only for a descriptor
    # path ending in .a; linking keeps the original CcInfo.
    stem = file.basename.removesuffix("." + file.extension) if file.extension else file.basename
    archive = ctx.actions.declare_file(ctx.label.name + "/" + context.tags + "/" + stem + ".a")
    ctx.actions.symlink(output = archive, target_file = file)
    return archive

def _is_android_library(file):
    """Whether Android's package manager extracts file: only lib/<abi>/lib*.so."""
    return file.basename.startswith("lib") and _is_shared_library(file, ["so"], versioned = False)

def _is_data_library(ctx, context, file):
    """Whether a file of data is a shared library the configuration loads; Android takes only those."""
    if context.operating_system == "android" and not _is_android_library(file):
        fail("%s: Android applications deliver only shared libraries named lib*.so beside an extension library; %s is not one" % (
            ctx.label,
            file.short_path,
        ))
    loadable = _LOADABLE[context.operating_system]
    return _is_shared_library(file, loadable.suffixes, loadable.versioned)

def _place_data(ctx, context, placement, prefix):
    """
    Place the files of data as Godot's [dependencies] and return their resource paths.

    Shared libraries lie beside the library, which loads them by name. Other files, such
    as a crash handler executable, lie at their path below the descriptor's directory,
    relative to the package of the target that lists them, as a vendor's add-on lays them
    out: code that finds them through res:// finds them there in runs and the editor.
    Desktop applications place those beside the executable, as Godot's export does.

    Returns:
        A struct of paths (all resource paths) and beside_executable (those of the files
        that are not shared libraries).
    """
    if context.operating_system == "ios" and ctx.files.data:
        fail((
            "%s: iOS applications deliver no files beside an extension library, so %s in " +
            "data would be lost; declare them with a platform library in platform_deps, such " +
            "as in an objc_library's data, or a framework the library loads as a " +
            "bundle_only import there"
        ) % (ctx.label, sorted([file.short_path for file in ctx.files.data])))
    paths = []
    beside_executable = []
    for target in ctx.attr.data:
        for file in target[DefaultInfo].files.to_list():
            if _is_data_library(ctx, context, file):
                paths.append(_place(placement, file.basename, file))
                continue
            path = _place_at(placement, resource_path(file, target.label, "", prefix), file)
            paths.append(path)
            beside_executable.append(path)
    return struct(paths = paths, beside_executable = beside_executable)

def configured_library(ctx, target, prefix, context):
    """
    Return the configured extension library and the resource paths of its files.

    Args:
        ctx: Rule context of the extension.
        target: The library target of this configuration.
        prefix: The descriptor's directory with a trailing slash, or empty.
        context: The configured context.

    Returns:
        A struct of library (the configured extension library), resource_paths (dict of
        resource paths to Files) and dependency_paths (the resource paths the
        descriptor lists as the library's dependencies).
    """
    frameworks = _framework_files(target)
    classified = _classify(ctx, target, context, frameworks)
    placement = _placement(ctx, context, prefix)
    if classified.link_kind == "framework":
        own = _own_framework(ctx, target, classified.file, frameworks)
        library_file = classified.file
        library_path = placement.directory + own.rsplit("/", 1)[-1]
        dependency_paths = _place_framework(placement, frameworks, own)
    else:
        library_file = _archive_file(ctx, context, classified)
        library_path = _place(placement, library_file.basename, library_file)
        dependency_paths = [_place(placement, file.basename, file) for file in _dependency_libraries(target, classified)]
    data = _place_data(ctx, context, placement, prefix)
    dependency_paths += data.paths
    return struct(
        library = struct(
            tags = context.tags,
            operating_system = context.operating_system,
            cpu = context.cpu,
            environment = context.environment,
            link_kind = classified.link_kind,
            file = library_file,
            resource_path = library_path,
            cc_info = classified.cc_info,
            runtime_dependencies = {
                path: file
                for path, file in placement.resource_paths.items()
                if path != library_path and not path.startswith(library_path + "/")
            },
            beside_executable = data.beside_executable,
            debug_symbols = linked_dsym(target),
        ),
        resource_paths = placement.resource_paths,
        dependency_paths = sorted(dependency_paths),
    )

# ==== Configuration ===========================================================

def library_context(ctx):
    """
    Return what the configuration fixes for an extension library, and its feature tags.

    The tags are the operating system, Godot's CPU tag, simulator in the iOS Simulator,
    and the variant.

    Args:
        ctx: Rule context of the extension.

    Returns:
        A struct of operating_system, cpu, environment, tool (whether the configuration
        is the tool configuration) and tags (the feature tags, joined with dots).
    """
    platform = target_platform(ctx)
    if not platform.operating_system or not platform.cpu:
        fail((
            "%s: an extension library needs a target platform with one of the operating " +
            "systems %s and one of the CPUs %s"
        ) % (
            ctx.label,
            ", ".join(OPERATING_SYSTEM_CONSTRAINTS),
            ", ".join([str(row.constraint) for row in CPU_TABLE.values()]),
        ))
    tool = ctx.attr._tool[BuildSettingInfo].value
    selected = variant(ctx)
    tags = [platform.operating_system, platform.cpu]
    if platform.environment == "simulator":
        tags.append("simulator")
    return struct(
        operating_system = platform.operating_system,
        cpu = platform.cpu,
        environment = platform.environment,
        tool = tool,
        tags = ".".join(tags + [selected]),
    )

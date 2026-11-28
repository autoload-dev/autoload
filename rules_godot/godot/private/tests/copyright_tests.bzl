"""The libraries a Godot COPYRIGHT.txt lists, with their licenses as SPDX expressions."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:copyright.bzl", "bundled_libraries", "spdx_license")
load(":copyright_excerpt.bzl", "COPYRIGHT_EXCERPT")

visibility("private")

def _by_name(text):
    return {library.name: library for library in bundled_libraries(text)}

# Every Files paragraph but Godot's own names a library, in the file's order; paragraphs of
# one Comment form one library, and one without a Comment is named by its first file.
def _test_every_paragraph_but_godots_names_a_library(env):
    env.expect.that_collection([library.name for library in bundled_libraries(COPYRIGHT_EXCERPT)]).contains_exactly([
        "Bullet Continuous Collision Detection and Physics Library",
        "servers/audio/effects/audio_effect_pitch_shift.cpp",
        "SMOL-V",
        "zlib",
    ]).in_order()

def _test_licenses_become_spdx_expressions(env):
    libraries = _by_name(COPYRIGHT_EXCERPT)
    expected = {
        "Bullet Continuous Collision Detection and Physics Library": ("Expat and Zlib", "MIT AND Zlib"),
        # The Wide Open License is on no SPDX list.
        "servers/audio/effects/audio_effect_pitch_shift.cpp": ("Expat and WOL", "LicenseRef-Expat-and-WOL"),
        "SMOL-V": ("Unlicense or Expat", "Unlicense OR MIT"),
        "zlib": ("Zlib", "Zlib"),
    }
    for name, (license, spdx) in expected.items():
        env.expect.where(library = name).that_str(libraries[name].license).equals(license)
        env.expect.where(library = name).that_str(libraries[name].spdx).equals(spdx)

# A library's text is its paragraphs and the texts of its licenses, as the file has them.
def _test_the_text_holds_the_paragraphs_and_license_texts(env):
    bullet = _by_name(COPYRIGHT_EXCERPT)["Bullet Continuous Collision Detection and Physics Library"]
    env.expect.that_str(bullet.text).contains("Copyright: 2011, Ole Kniemeyer, MAXON, www.maxon.net")
    env.expect.that_str(bullet.text).contains("Copyright: 2003-2008, Erwin Coumans")
    env.expect.that_str(bullet.text).contains("License: Expat\n Permission is hereby granted, free of charge")
    env.expect.that_str(bullet.text).contains("License: Zlib\n This software is provided 'as-is'")
    env.expect.that_bool("License: Unlicense\n" in bullet.text).equals(False)
    zlib = _by_name(COPYRIGHT_EXCERPT)["zlib"]
    env.expect.that_bool("License: Expat\n" in zlib.text).equals(False)

# Paragraphs of one library under different licenses join them with AND.
def _test_one_library_under_several_licenses(env):
    library = bundled_libraries("""\
Files: modules/jolt_physics/*
Comment: Jolt Physics
License: Expat

Files: thirdparty/jolt_physics/*
Comment: Jolt Physics
License: Apache-2.0 or Expat
""")[0]
    env.expect.that_str(library.license).equals("Expat and (Apache-2.0 or Expat)")
    env.expect.that_str(library.spdx).equals("MIT AND (Apache-2.0 OR MIT)")

# Godot's short names that differ from SPDX's, each mapped by the text Godot gives for it.
def _test_short_names_map_to_spdx(env):
    for short_name, spdx in {
        "Expat": "MIT",
        "BSD-3-clause": "BSD-3-Clause",
        "HarfBuzz": "MIT-Modern-Variant",
        "Unicode": "Unicode-DFS-2016",
        "X11": "HPND-sell-variant",
        "glslang": "LicenseRef-glslang",
        "OFL-1.1": "OFL-1.1",
    }.items():
        env.expect.where(short_name = short_name).that_str(spdx_license(short_name)).equals(spdx)

def copyright_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_every_paragraph_but_godots_names_a_library,
            _test_licenses_become_spdx_expressions,
            _test_the_text_holds_the_paragraphs_and_license_texts,
            _test_one_library_under_several_licenses,
            _test_short_names_map_to_spdx,
        ],
    )

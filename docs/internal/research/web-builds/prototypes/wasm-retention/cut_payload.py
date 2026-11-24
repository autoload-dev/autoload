"""
Cut the code and data that `retention.py` found kept alive in the web template without
being used by a game like Lichtpost. Each cut is a source edit to a Godot 4.8 tree that
removes the reference keeping a payload, guarded so only the web build changes; the
build itself adds `brotli=no` (Brotli and WOFF2, which also drops the built-in default
font) and the build profile disables `LineEdit` and `Expression`.

Usage: python3 cut_payload.py <godot source tree> [--skip PAYLOAD]

`--skip` leaves out the cuts whose payload starts with PAYLOAD, to measure one cut.
"""

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Cut:
    payload: str
    path: str
    old: str
    new: str


def _web_only(old: str, web: str) -> str:
    return f"#ifdef WEB_ENABLED\n{web}\n#else\n{old}\n#endif"


_LOGGER = "\t\tOS::get_singleton()->add_logger(memnew(RotatedFileLogger(base_path, max_files)));"
_PARTICLES = (
    "\tSceneTree::add_idle_callback(ParticleProcessMaterial::flush_changes);\n"
    "\tParticleProcessMaterial::init_shaders();"
)
_PARTICLES_END = "\tParticleProcessMaterial::finish_shaders();"
_FONT_MODULES = (
    "FT_USE_MODULE( FT_Driver_ClassRec, t1_driver_class )",
    "FT_USE_MODULE( FT_Driver_ClassRec, cff_driver_class )",
    "FT_USE_MODULE( FT_Driver_ClassRec, t1cid_driver_class )",
    "FT_USE_MODULE( FT_Driver_ClassRec, pfr_driver_class )",
    "FT_USE_MODULE( FT_Driver_ClassRec, t42_driver_class )",
    "FT_USE_MODULE( FT_Driver_ClassRec, winfnt_driver_class )",
    "FT_USE_MODULE( FT_Driver_ClassRec, pcf_driver_class )",
    "FT_USE_MODULE( FT_Driver_ClassRec, bdf_driver_class )",
    "FT_USE_MODULE( FT_Module_Class, psaux_module_class )",
    "FT_USE_MODULE( FT_Module_Class, psnames_module_class )",
    "FT_USE_MODULE( FT_Module_Class, pshinter_module_class )",
    "FT_USE_MODULE( FT_Renderer_Class, ft_sdf_renderer_class )",
    "FT_USE_MODULE( FT_Renderer_Class, ft_bitmap_sdf_renderer_class )",
    "FT_USE_MODULE( FT_Renderer_Class, ft_svg_renderer_class )",
)


_GDEXTENSION = "\tGDExtension::initialize_gdextensions();"
# SCons does not see ftinit.c include the module list through a macro: change ftinit.c too,
# so it is rebuilt.
_FONT_INIT = "#include <freetype/ftmodapi.h>"


def _iconv(kind: str, empty: str) -> Cut:
    line = f'\tERR_FAIL_COND_V_MSG(!_iconv_ok, {empty}(), "Conversion failed: Unable to load libiconv");'
    web = f'\tERR_FAIL_V_MSG({empty}(), "Conversion failed: no iconv on the web.");'
    return Cut(f"iconv ({kind})", "drivers/unix/os_unix.cpp", line, _web_only(line, web))


def _lut(n: int) -> Cut:
    line = f"\t\t\t\tmemcpy(lut{n}_data.ptrw(), LTC_LUT{n}, lut{n}_size);"
    web = f"\t\t\t\tmemset(lut{n}_data.ptrw(), 0, lut{n}_size); // No area lights."
    return Cut(
        f"LTC table {n}",
        "drivers/gles3/rasterizer_scene_gles3.cpp",
        line,
        _web_only(line, web),
    )


CUTS = [
    Cut(
        "RegEx and PCRE2 (file logging)", "main/main.cpp", _LOGGER, _web_only(_LOGGER, "")
    ),
    _iconv("decode", "String"),
    _iconv("encode", "PackedByteArray"),
    Cut(
        "ZSTD compressor (writing compressed files)",
        "core/io/file_access_compressed.cpp",
        "\tif (p_mode_flags & WRITE) {\n\t\tbuffer.clear();",
        "#ifdef WEB_ENABLED\n\tERR_FAIL_COND_V(p_mode_flags & WRITE, ERR_UNAVAILABLE);\n#endif\n"
        "\tif (p_mode_flags & WRITE) {\n\t\tbuffer.clear();",
    ),
    Cut(
        "ZSTD compressor (writing compressed files)",
        "core/io/file_access_compressed.cpp",
        "\tif (writing) {\n\t\t//save block table and all compressed blocks",
        _web_only("\tif (writing) {", "\tif (false) {")
        + "\n\t\t//save block table and all compressed blocks",
    ),
    Cut(
        "ParticleProcessMaterial shaders",
        "scene/register_scene_types.cpp",
        _PARTICLES,
        f"\tif constexpr (is_class_enabled<ParticleProcessMaterial>::value) {{\n{_PARTICLES}\n\t}}",
    ),
    Cut(
        "ParticleProcessMaterial shaders",
        "scene/register_scene_types.cpp",
        _PARTICLES_END,
        f"\tif constexpr (is_class_enabled<ParticleProcessMaterial>::value) {{\n{_PARTICLES_END}\n\t}}",
    ),
    _lut(1),
    _lut(2),
    Cut(
        "GDExtension interface (no dynamic linking)",
        "core/register_core_types.cpp",
        _GDEXTENSION,
        f"#if !defined(WEB_ENABLED) || defined(WEB_DLINK_ENABLED)\n{_GDEXTENSION}\n#endif",
    ),
    Cut(
        "FreeType modules other than TrueType",
        "thirdparty/freetype/src/base/ftinit.c",
        _FONT_INIT,
        f"{_FONT_INIT} /* Built-in modules: see cut_payload.py. */",
    ),
    *(
        Cut(
            "FreeType modules other than TrueType",
            "thirdparty/freetype/include/freetype/config/ftmodule.h",
            m,
            f"/* {m} */",
        )
        for m in _FONT_MODULES
    ),
]


def apply(root: Path, cut: Cut) -> None:
    path = root / cut.path
    text = path.read_text()
    if text.count(cut.old) != 1:
        raise SystemExit(f"{cut.path}: expected one match for the cut of {cut.payload}")
    path.write_text(text.replace(cut.old, cut.new))


def main() -> None:
    root = Path(sys.argv[1])
    skip = sys.argv[sys.argv.index("--skip") + 1] if "--skip" in sys.argv else None
    cuts = [c for c in CUTS if not (skip and c.payload.startswith(skip))]
    for cut in cuts:
        apply(root, cut)
    print(f"{len(cuts)} cuts applied")


if __name__ == "__main__":
    main()

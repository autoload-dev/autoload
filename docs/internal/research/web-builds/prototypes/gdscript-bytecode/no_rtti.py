"""Make Godot's sources build with -fno-rtti (prototype: dynamic_cast becomes static_cast
where the web runtime never sees a wrong type; the type names in leak reports go)."""

import sys
from pathlib import Path

root = Path(sys.argv[1])
for name in ("core/templates/paged_allocator.h", "core/templates/rid_owner.h"):
    p = root / name
    p.write_text(p.read_text().replace("typeid(T).name()", '"(no RTTI)"'))
# Runtime packing of bound callables, editor undo and GDExtension placeholders only.
for name in (
    "scene/resources/packed_scene.cpp",
    "core/object/undo_redo.cpp",
    "core/extension/gdextension_interface.cpp",
):
    p = root / name
    p.write_text(p.read_text().replace("dynamic_cast<", "static_cast<"))
p = root / "drivers/gles3/storage/material_storage.cpp"
text = p.read_text()
old = """		SceneShaderData *data = dynamic_cast<SceneShaderData *>(material->shader->data);
		if (data) {"""
new = """		if (material->shader->mode == RSE::SHADER_SPATIAL) {
			SceneShaderData *data = static_cast<SceneShaderData *>(material->shader->data);"""
assert old in text
p.write_text(text.replace(old, new))

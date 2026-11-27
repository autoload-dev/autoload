# A fresh tree

Two Godot projects without BUILD declarations: the language declares each project, groups
their resources into import units and resolves what the units' files reference, across
packages, through a global class, an extension's resource path and a resolve directive, while
a project never reaches another's resources.

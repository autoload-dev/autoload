extends Resource
## Shared material references are never mutated by component instances.

@export var ivory: StandardMaterial3D
@export var moss: StandardMaterial3D
@export var orange: StandardMaterial3D
@export var coral: StandardMaterial3D
@export var night: StandardMaterial3D
@export var teal: StandardMaterial3D
@export var earth: StandardMaterial3D
@export var rock: StandardMaterial3D


func material(color: Color) -> StandardMaterial3D:
	match color.to_html(false):
		"fff1d2": return ivory
		"83b493": return moss
		"ef9b52": return orange
		"d76866": return coral
		"192c46": return night
		"3f7979": return teal
		"805b51": return earth
		"6c514d": return rock
	return ivory

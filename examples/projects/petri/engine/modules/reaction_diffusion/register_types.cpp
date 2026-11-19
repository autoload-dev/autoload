#include "register_types.h"

#include "core/object/class_db.h"
#include "gray_scott_field.h"

void initialize_reaction_diffusion_module(ModuleInitializationLevel p_level) {
	if (p_level == MODULE_INITIALIZATION_LEVEL_SCENE) {
		GDREGISTER_CLASS(GrayScottField);
	}
}

void uninitialize_reaction_diffusion_module(ModuleInitializationLevel p_level) {}

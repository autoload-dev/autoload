// The script instance of a Godot object whose script is a Dart script: the Dart object
// that Godot's calls reach.

#pragma once

#include <godot_cpp/classes/object.hpp>
#include <godot_cpp/classes/ref.hpp>

#include "include/dart_api.h"

namespace dart_godot {

class DartScript;

struct Instance {
	godot::Object *owner = nullptr;
	godot::Ref<DartScript> script;
	Dart_PersistentHandle object = nullptr;
};

// Creates the Godot script instance for an Instance, which it then owns.
void *create_script_instance(Instance *p_instance);

// The Instance of p_object when its script instance is a Dart one, else null.
Instance *find_instance(godot::Object *p_object);

} // namespace dart_godot

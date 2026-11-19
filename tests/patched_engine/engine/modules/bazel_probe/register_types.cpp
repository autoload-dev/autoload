#include "register_types.h"

#include "core/object/class_db.h"
#include "core/object/ref_counted.h"
#include "core/version.h"

class BazelProbe : public RefCounted {
	GDCLASS(BazelProbe, RefCounted);

protected:
	static void _bind_methods() {
		ClassDB::bind_method(D_METHOD("answer"), &BazelProbe::answer);
		ClassDB::bind_method(D_METHOD("engine_name"), &BazelProbe::engine_name);
	}

public:
	int answer() const { return 42; }
	String engine_name() const { return VERSION_NAME; }
};

void initialize_bazel_probe_module(ModuleInitializationLevel p_level) {
	if (p_level == MODULE_INITIALIZATION_LEVEL_SCENE) {
		ClassDB::register_class<BazelProbe>();
	}
}

void uninitialize_bazel_probe_module(ModuleInitializationLevel p_level) {}

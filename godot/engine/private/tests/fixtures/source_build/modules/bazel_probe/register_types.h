#ifndef BAZEL_PROBE_REGISTER_TYPES_H
#define BAZEL_PROBE_REGISTER_TYPES_H

#include "modules/register_module_types.h"

void initialize_bazel_probe_module(ModuleInitializationLevel p_level);
void uninitialize_bazel_probe_module(ModuleInitializationLevel p_level);

#endif

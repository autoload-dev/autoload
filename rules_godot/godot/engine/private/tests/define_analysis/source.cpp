#include "godot/engine/private/tests/define_analysis/probe.h"

// COMMENT_ONLY_ENABLED is only mentioned in this comment.
#define PASTE(a, b) a##b

#if PASTE(PASTED, _DISABLED)
int pasted = 1;
#endif

#ifdef INACTIVE_ENABLED
#ifdef INSIDE_INACTIVE_ENABLED
int inside = 1;
#endif
#endif

#ifndef GODOT_DECLARES_BUILD_PROFILE
#error "The build profile define is missing."
#endif

const char *probe_value = PROBE_VALUE;

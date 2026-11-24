// The backend of operating systems without a login SDK: the add-on loads, and every login
// ends with UNSUPPORTED before any backend work.
#include "examples/addons/app_auth/native/backend.h"

namespace app_auth {
bool app_auth_backend_is_supported() { return false; }
std::string app_auth_backend_default_scheme() { return ""; }
std::string app_auth_backend_default_scheme_source() { return "the operating system"; }
bool app_auth_backend_start(const BackendRequest &) { return false; }
} // namespace app_auth

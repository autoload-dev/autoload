#pragma once

#include <optional>
#include <string>
#include <vector>

namespace app_auth {
// The rules of the login configuration. Each returns the failure message naming the field,
// or nothing when the configuration is valid.
std::optional<std::string> validate_configuration(const std::string &issuer,
                                                  const std::string &client_id,
                                                  const std::vector<std::string> &scopes,
                                                  const std::string &redirect_uri);

// A default redirect scheme: lowercase and valid per RFC 3986. The message names `source`,
// where the scheme came from, such as a manifest value or the bundle identifier.
std::optional<std::string> validate_redirect_scheme(const std::string &scheme,
                                                    const std::string &source);
} // namespace app_auth

#pragma once

#include <optional>
#include <string>

namespace app_auth {
// The decoded payload segment of a JWT: three dot-separated segments, the payload base64url
// without padding. The signature is not checked; the SDK validated the token during the
// token exchange.
std::optional<std::string> id_token_payload(const std::string &token);
} // namespace app_auth

#include "validation.h"

namespace app_auth {
namespace {
bool is_alpha(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
bool is_digit(char c) { return c >= '0' && c <= '9'; }
bool is_scheme_mark(char c) { return c == '+' || c == '-' || c == '.'; }

bool has_whitespace(const std::string &value) {
  for (char c : value) {
    if (c == ' ' || (c >= '\t' && c <= '\r')) return true;
  }
  return false;
}

// RFC 3986: scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )
bool valid_scheme(const std::string &scheme, bool lowercase_only) {
  if (scheme.empty()) return false;
  for (size_t i = 0; i < scheme.size(); ++i) {
    const char c = scheme[i];
    const bool alpha = lowercase_only ? (c >= 'a' && c <= 'z') : is_alpha(c);
    if (i == 0 ? !alpha : !(alpha || is_digit(c) || is_scheme_mark(c))) return false;
  }
  return true;
}
} // namespace

std::optional<std::string> validate_configuration(const std::string &issuer,
                                                  const std::string &client_id,
                                                  const std::vector<std::string> &scopes,
                                                  const std::string &redirect_uri) {
  const std::string prefix = "https://";
  if (issuer.compare(0, prefix.size(), prefix) != 0 || has_whitespace(issuer)) {
    return "issuer must be an absolute https URL";
  }
  const size_t host_end = issuer.find('/', prefix.size());
  const std::string host = issuer.substr(prefix.size(), host_end == std::string::npos
                                                            ? std::string::npos
                                                            : host_end - prefix.size());
  if (host.empty()) return "issuer must name a host";
  if (issuer.find('?') != std::string::npos || issuer.find('#') != std::string::npos) {
    return "issuer must not have a query or fragment";
  }
  if (client_id.empty() || has_whitespace(client_id)) {
    return "client_id must be nonempty without whitespace";
  }
  bool openid = false;
  for (const std::string &scope : scopes) {
    if (scope.empty() || has_whitespace(scope)) {
      return "scopes must be nonempty without whitespace";
    }
    openid = openid || scope == "openid";
  }
  if (!openid) return "scopes must contain openid";
  if (!redirect_uri.empty()) {
    const size_t colon = redirect_uri.find(':');
    if (colon == std::string::npos || has_whitespace(redirect_uri) ||
        !valid_scheme(redirect_uri.substr(0, colon), false)) {
      return "redirect_uri must be empty or an absolute URI with an RFC 3986 scheme";
    }
  }
  return std::nullopt;
}

std::optional<std::string> validate_redirect_scheme(const std::string &scheme,
                                                    const std::string &source) {
  if (valid_scheme(scheme, true)) return std::nullopt;
  if (scheme.empty()) return "The default redirect scheme from " + source + " is empty";
  return "The default redirect scheme from " + source + " is not a lowercase RFC 3986 scheme: '" +
         scheme + "'; pass an explicit redirect_uri";
}
} // namespace app_auth

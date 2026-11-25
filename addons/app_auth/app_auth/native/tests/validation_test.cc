// Every rule of the login configuration, each failure naming its field.
#include "app_auth/native/validation.h"
#include <iostream>
#include <string>
#include <vector>

namespace {
using app_auth::validate_configuration;
using app_auth::validate_redirect_scheme;

int failures = 0;

void require(bool ok, const std::string &message) {
  if (!ok) {
    std::cerr << "FAIL: " << message << "\n";
    ++failures;
  }
}

const std::vector<std::string> kScopes = {"openid", "profile"};

void require_valid(const std::string &issuer, const std::string &client_id,
                   const std::vector<std::string> &scopes, const std::string &redirect_uri,
                   const std::string &label) {
  auto error = validate_configuration(issuer, client_id, scopes, redirect_uri);
  require(!error.has_value(), label + ": expected valid, got '" + error.value_or("") + "'");
}

void require_invalid(const std::string &issuer, const std::string &client_id,
                     const std::vector<std::string> &scopes, const std::string &redirect_uri,
                     const std::string &field, const std::string &label) {
  auto error = validate_configuration(issuer, client_id, scopes, redirect_uri);
  require(error.has_value(), label + ": expected a failure");
  if (error) {
    require(error->find(field) != std::string::npos,
            label + ": message '" + *error + "' does not name " + field);
  }
}
} // namespace

int main() {
  require_valid("https://demo.duendesoftware.com", "interactive.public", kScopes, "", "demo");
  require_valid("https://issuer.example/realms/one", "client", {"openid"},
                "org.example.appauth:/oauth2redirect", "explicit redirect");
  require_valid("https://issuer.example", "client", {"openid"}, "com.example+app-1.0:/cb",
                "scheme with RFC 3986 characters");

  // issuer: absolute https URL without query or fragment.
  require_invalid("", "client", kScopes, "", "issuer", "empty issuer");
  require_invalid("http://issuer.example", "client", kScopes, "", "issuer", "http issuer");
  require_invalid("https://", "client", kScopes, "", "issuer", "issuer without host");
  require_invalid("issuer.example", "client", kScopes, "", "issuer", "relative issuer");
  require_invalid("https://issuer.example/?x=1", "client", kScopes, "", "issuer",
                  "issuer with query");
  require_invalid("https://issuer.example/#top", "client", kScopes, "", "issuer",
                  "issuer with fragment");
  require_invalid("https://issuer example", "client", kScopes, "", "issuer",
                  "issuer with whitespace");

  // client_id: nonempty, no whitespace.
  require_invalid("https://issuer.example", "", kScopes, "", "client_id", "empty client_id");
  require_invalid("https://issuer.example", "my client", kScopes, "", "client_id",
                  "client_id with whitespace");
  require_invalid("https://issuer.example", "client\t", kScopes, "", "client_id",
                  "client_id with tab");

  // scopes: contains openid; each nonempty, no whitespace.
  require_invalid("https://issuer.example", "client", {}, "", "scopes", "no scopes");
  require_invalid("https://issuer.example", "client", {"profile"}, "", "scopes",
                  "scopes without openid");
  require_invalid("https://issuer.example", "client", {"openid", ""}, "", "scopes",
                  "empty scope");
  require_invalid("https://issuer.example", "client", {"openid", "pro file"}, "", "scopes",
                  "scope with whitespace");

  // redirect_uri: empty, or an absolute URI with a valid RFC 3986 scheme.
  require_invalid("https://issuer.example", "client", kScopes, "/oauth2redirect",
                  "redirect_uri", "relative redirect_uri");
  require_invalid("https://issuer.example", "client", kScopes, "1app:/cb", "redirect_uri",
                  "scheme starting with a digit");
  require_invalid("https://issuer.example", "client", kScopes, "my_app:/cb", "redirect_uri",
                  "scheme with underscore");
  require_invalid("https://issuer.example", "client", kScopes, "noscheme", "redirect_uri",
                  "redirect_uri without scheme");
  require_invalid("https://issuer.example", "client", kScopes, "org.example:/cb back",
                  "redirect_uri", "redirect_uri with whitespace");

  // Default scheme: lowercase and valid per RFC 3986, the message naming its source.
  require(!validate_redirect_scheme("org.example.appauth", "the bundle identifier").has_value(),
          "lowercase scheme accepted");
  require(!validate_redirect_scheme("com.example+app-1.0", "the bundle identifier").has_value(),
          "lowercase scheme with digits and marks accepted");
  for (const std::string &scheme : {"", "Org.Example", "1org", "org_example", "org example"}) {
    auto error = validate_redirect_scheme(scheme, "the appAuthRedirectScheme manifest value");
    require(error.has_value(), "scheme '" + scheme + "' rejected");
    if (error) {
      require(error->find("appAuthRedirectScheme") != std::string::npos,
              "scheme '" + scheme + "': message '" + *error + "' does not name its source");
    }
  }

  if (failures) {
    std::cerr << failures << " validation checks failed\n";
    return 1;
  }
  std::cout << "VALIDATION_OK\n";
  return 0;
}

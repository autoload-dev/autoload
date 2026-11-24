// ID-token payload extraction: base64url without padding, no signature validation.
#include "examples/addons/app_auth/native/id_token.h"
#include <iostream>
#include <string>

namespace {
using app_auth::id_token_payload;

int failures = 0;

void require(bool ok, const std::string &message) {
  if (!ok) {
    std::cerr << "FAIL: " << message << "\n";
    ++failures;
  }
}

// {"alg":"RS256"} and {"sub":"1","name":"Alice"} as base64url without padding.
const std::string kHeader = "eyJhbGciOiJSUzI1NiJ9";
const std::string kPayload = "eyJzdWIiOiIxIiwibmFtZSI6IkFsaWNlIn0";
const std::string kSignature = "c2lnbmF0dXJl";
} // namespace

int main() {
  auto payload = id_token_payload(kHeader + "." + kPayload + "." + kSignature);
  require(payload.has_value(), "valid token decodes");
  require(payload.value_or("") == R"({"sub":"1","name":"Alice"})",
          "payload text, got '" + payload.value_or("") + "'");

  // Payload lengths that need every remainder of the base64url alphabet.
  require(id_token_payload("h.eA.s").value_or("") == "x", "two-character group");
  require(id_token_payload("h.eHk.s").value_or("") == "xy", "three-character group");
  require(id_token_payload("h.eHl6.s").value_or("") == "xyz", "four-character group");
  require(id_token_payload("h.-_8.s").value_or("") == std::string("\xfb\xff", 2),
          "url-safe alphabet characters");

  // Not three dot-separated segments.
  require(!id_token_payload("").has_value(), "empty token");
  require(!id_token_payload(kPayload).has_value(), "one segment");
  require(!id_token_payload(kHeader + "." + kPayload).has_value(), "two segments");
  require(!id_token_payload(kHeader + "." + kPayload + "." + kSignature + ".x").has_value(),
          "four segments");
  require(!id_token_payload(kHeader + ".." + kSignature).has_value(), "missing payload");

  // Padding, invalid characters and impossible lengths.
  require(!id_token_payload("h.eA==.s").has_value(), "padded payload");
  require(!id_token_payload("h.eHk=.s").has_value(), "single padding character");
  require(!id_token_payload("h.eHl6=.s").has_value(), "padding after a full group");
  require(!id_token_payload("h.eHl6+.s").has_value(), "standard base64 plus");
  require(!id_token_payload("h.eHl6/.s").has_value(), "standard base64 slash");
  require(!id_token_payload("h.e Hk.s").has_value(), "whitespace inside");
  require(!id_token_payload("h.e.s").has_value(), "one leftover character");

  if (failures) {
    std::cerr << failures << " ID-token checks failed\n";
    return 1;
  }
  std::cout << "ID_TOKEN_OK\n";
  return 0;
}

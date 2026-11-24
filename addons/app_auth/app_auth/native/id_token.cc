#include "id_token.h"

namespace app_auth {
namespace {
int base64url_value(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '-') return 62;
  if (c == '_') return 63;
  return -1;
}

std::optional<std::string> decode_base64url(const std::string &text) {
  if (text.empty() || text.size() % 4 == 1) return std::nullopt;
  std::string out;
  out.reserve(text.size() * 3 / 4);
  unsigned buffer = 0;
  int bits = 0;
  for (char c : text) {
    const int value = base64url_value(c);
    if (value < 0) return std::nullopt;
    buffer = (buffer << 6) | static_cast<unsigned>(value);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push_back(static_cast<char>((buffer >> bits) & 0xff));
    }
  }
  return out;
}
} // namespace

std::optional<std::string> id_token_payload(const std::string &token) {
  const size_t first = token.find('.');
  if (first == std::string::npos) return std::nullopt;
  const size_t second = token.find('.', first + 1);
  if (second == std::string::npos || token.find('.', second + 1) != std::string::npos) {
    return std::nullopt;
  }
  return decode_base64url(token.substr(first + 1, second - first - 1));
}
} // namespace app_auth

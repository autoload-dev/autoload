#include "xdg_directories.h"
#include <sstream>

namespace platform_paths {
static bool absolute(const std::string &value) {
  return !value.empty() && value[0] == '/' && value.find('\0') == std::string::npos;
}
static std::string join(const std::string &base, const std::string &suffix) {
  return base + (base.back() == '/' ? "" : "/") + suffix;
}
BackendResult xdg_base(const std::string &override_path, const std::string &home, const std::string &suffix) {
  if (absolute(override_path)) return success(override_path, Scope::APPLICATION);
  if (!absolute(home)) return failure(Status::ERROR, "An absolute HOME is required for the XDG default");
  return success(join(home, suffix), Scope::APPLICATION);
}

BackendResult user_directory(const std::string &contents, const std::string &key, const std::string &home) {
  BackendResult result = failure(Status::UNAVAILABLE, "No configured XDG " + key + " directory");
  const std::string name = "XDG_" + key + "_DIR";
  std::istringstream lines(contents);
  std::string line;
  while (std::getline(lines, line)) {
    size_t pos = line.find_first_not_of(" \t\r");
    if (pos == std::string::npos || line.compare(pos, name.size(), name) != 0) continue;
    pos += name.size();
    if (pos < line.size() && line[pos] != '=' && line[pos] != ' ' && line[pos] != '\t' && line[pos] != '\r') continue;
    result = failure(Status::ERROR, "Malformed XDG " + key + " assignment");
    pos = line.find_first_not_of(" \t", pos);
    if (pos == std::string::npos || line[pos++] != '=') continue;
    pos = line.find_first_not_of(" \t", pos);
    if (pos == std::string::npos || line[pos++] != '"') continue;
    std::string path;
    bool valid = true, closed = false;
    if (line.compare(pos, 5, "$HOME") == 0 && pos + 5 < line.size() &&
        (line[pos + 5] == '/' || line[pos + 5] == '"')) {
      valid = absolute(home);
      path = home;
      pos += 5;
    }
    for (; pos < line.size(); ++pos) {
      char c = line[pos];
      if (c == '"') { closed = true; ++pos; break; }
      if (c == '\\') {
        if (++pos == line.size()) { valid = false; break; }
        c = line[pos];
        if (c != '\\' && c != '"' && c != '$' && c != '`') path += '\\';
      } else if (c == '$' || c == '`') {
        valid = false;
      }
      path += c;
    }
    pos = line.find_first_not_of(" \t\r", pos);
    if (valid && closed && absolute(path) &&
        (pos == std::string::npos || line[pos] == '#')) {
      result = success(path, Scope::USER_DOMAIN);
    }
  }
  return result;
}
} // namespace platform_paths

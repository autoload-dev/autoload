#include "xdg_directories.h"
#include <cerrno>
#include <cstdio>
#include <cstdlib>

namespace platform_paths {
static std::string environment(const char *name) {
  const char *value = std::getenv(name);
  return value ? value : "";
}
bool requires_identity(int64_t category) {
  return category == APPLICATION_SUPPORT || category == APPLICATION_CACHE;
}
BackendResult resolve(int64_t category, const std::string &id) {
  const std::string home = environment("HOME");
  if (category == TEMPORARY) {
    std::string path = environment("TMPDIR");
    if (path.empty() || path[0] != '/') path = "/tmp";
    return success(path, Scope::TEMPORARY);
  }
  if (category == APPLICATION_SUPPORT || category == APPLICATION_CACHE) {
    BackendResult base = xdg_base(environment(category == APPLICATION_SUPPORT ? "XDG_DATA_HOME" : "XDG_CACHE_HOME"), home,
                                  category == APPLICATION_SUPPORT ? ".local/share" : ".cache");
    if (base.status == Status::OK) base.path += (base.path.back() == '/' ? "" : "/") + id;
    return base;
  }
  if (category != DOCUMENTS && category != DOWNLOADS) return failure(Status::ERROR, "Unknown directory category");
  BackendResult config = xdg_base(environment("XDG_CONFIG_HOME"), home, ".config");
  if (config.status != Status::OK) return config;
  errno = 0;
  FILE *input = std::fopen((config.path + "/user-dirs.dirs").c_str(), "rb");
  if (!input) {
    return failure(errno == ENOENT ? Status::UNAVAILABLE : Status::ERROR,
                   errno == ENOENT ? "No user-dirs.dirs configuration" : "Cannot open user-dirs.dirs");
  }
  std::string contents;
  char buffer[4096];
  size_t count;
  while ((count = std::fread(buffer, 1, sizeof(buffer), input)) != 0) {
    contents.append(buffer, count);
  }
  const bool read_failed = std::ferror(input) != 0;
  std::fclose(input);
  if (read_failed) {
    return failure(Status::ERROR, "Cannot read user-dirs.dirs");
  }
  return user_directory(contents, category == DOCUMENTS ? "DOCUMENTS" : "DOWNLOAD", home);
}
} // namespace platform_paths

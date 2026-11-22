#include "addons/platform_paths/native/backends/linux/xdg_directories.h"
#include <cstdlib>
#include <iostream>
using namespace platform_paths;
static void require(bool ok, const char *message) {
  if (!ok) { std::cerr << message << "\n"; std::exit(1); }
}
int main() {
  require(xdg_base("/custom", "/home/me", ".cache").path == "/custom", "absolute override");
  require(xdg_base("relative", "/home/me", ".cache").path == "/home/me/.cache", "relative override ignored");
  require(xdg_base("", "/home/me", ".local/share").path == "/home/me/.local/share", "data default");
  require(xdg_base("", "relative", ".cache").status == Status::ERROR, "invalid home");
  require(user_directory("XDG_DOCUMENTS_DIR=\"$HOME/Documents ü\"\n", "DOCUMENTS", "/home/me").path == "/home/me/Documents ü", "HOME Unicode");
  require(user_directory("XDG_DOCUMENTS_DIR=\"$HOME\"", "DOCUMENTS", "/home/me").path == "/home/me", "configured HOME preserved");
  require(user_directory("XDG_DOCUMENTS_DIR=\"/a\\\"b\" # comment", "DOCUMENTS", "").path == "/a\"b", "quoted escape");
  require(user_directory("XDG_DOCUMENTS_DIR=\"/first\"\nXDG_DOCUMENTS_DIR=\"/last\"", "DOCUMENTS", "").path == "/last", "last assignment wins");
  const std::string long_path = "/" + std::string(2000, 'a');
  require(user_directory("XDG_DOWNLOAD_DIR=\"" + long_path + "\"", "DOWNLOAD", "").path == long_path, "unbounded path");
  require(user_directory("# empty", "DOCUMENTS", "").status == Status::UNAVAILABLE, "missing key");
  require(user_directory("XDG_DOCUMENTS_DIR=relative", "DOCUMENTS", "").status == Status::ERROR, "malformed assignment");
  require(user_directory("XDG_DOCUMENTS_DIR=\"/bad/$OTHER\"", "DOCUMENTS", "").status == Status::ERROR, "no shell expansion");
  require(user_directory("XDG_DOCUMENTS_DIR=broken\nXDG_DOWNLOAD_DIR=\"/ok\"", "DOWNLOAD", "").path == "/ok", "category isolation");
  std::cout << "XDG_POLICY_OK\n";
}

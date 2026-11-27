// Runs an AOT snapshot that rules_dart compiled on the runtime built from the SDK sources:
// the snapshot's version and features must match the runtime's, and Dart functions must be
// callable through dart_api.h.

#include <cstdio>
#include <cstdlib>

#include "include/dart_api.h"
#include "include/dart_engine.h"

namespace {

void check(const char *error, const char *step) {
  if (error != nullptr) {
    std::fprintf(stderr, "%s: %s\n", step, error);
    std::exit(1);
  }
}

Dart_Handle check(Dart_Handle handle, const char *step) {
  if (Dart_IsError(handle)) {
    std::fprintf(stderr, "%s: %s\n", step, Dart_GetError(handle));
    std::exit(1);
  }
  return handle;
}

} // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::fprintf(stderr, "usage: %s <snapshot>\n", argv[0]);
    return 2;
  }
  char *error = nullptr;
  DartEngine_SnapshotData snapshot = DartEngine_AotSnapshotFromFile(argv[1], &error);
  check(error, "loading the snapshot");
  Dart_Isolate isolate = DartEngine_CreateIsolate(snapshot, &error);
  check(error, "starting an isolate");

  DartEngine_AcquireIsolate(isolate);
  Dart_EnterScope();
  Dart_Handle library = Dart_RootLibrary();
  check(Dart_Invoke(library, Dart_NewStringFromCString("main"), 0, nullptr), "calling main");
  Dart_Handle arguments[] = {Dart_NewInteger(40), Dart_NewInteger(2)};
  Dart_Handle sum = check(Dart_Invoke(library, Dart_NewStringFromCString("add"), 2, arguments),
                          "calling add");
  int64_t value = 0;
  check(Dart_IntegerToInt64(sum, &value), "reading the sum");
  Dart_ExitScope();
  DartEngine_ReleaseIsolate();
  DartEngine_Shutdown();

  if (value != 42) {
    std::fprintf(stderr, "add(40, 2) returned %lld\n", static_cast<long long>(value));
    return 1;
  }
  return 0;
}

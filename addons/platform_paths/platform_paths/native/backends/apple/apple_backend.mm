#include "platform_paths/native/backend.h"
#import <Foundation/Foundation.h>
#import <TargetConditionals.h>

namespace platform_paths {
bool requires_identity(int64_t category) {
  return !TARGET_OS_IPHONE && (category == APPLICATION_SUPPORT || category == APPLICATION_CACHE);
}

BackendResult resolve(int64_t category, const std::string &application_id) {
  @autoreleasepool {
    @try {
      NSString *path = nil;
      if (category == TEMPORARY) {
        path = NSTemporaryDirectory();
      } else {
        NSSearchPathDirectory directory;
        switch (category) {
        case APPLICATION_SUPPORT:
          directory = NSApplicationSupportDirectory;
          break;
        case APPLICATION_CACHE:
          directory = NSCachesDirectory;
          break;
        case DOCUMENTS:
          directory = NSDocumentDirectory;
          break;
        case DOWNLOADS:
          directory = NSDownloadsDirectory;
          break;
        default:
          return failure(Status::ERROR, "Unknown directory category");
        }
        NSArray<NSURL *> *urls = [[NSFileManager defaultManager] URLsForDirectory:directory inDomains:NSUserDomainMask];
        path = [[urls firstObject] path];
        if (path && requires_identity(category)) {
          path = [path stringByAppendingPathComponent:[NSString stringWithUTF8String:application_id.c_str()]];
        }
      }
      if (!path.length) return failure(Status::UNAVAILABLE, "Foundation returned no directory");
      if (![path isAbsolutePath]) return failure(Status::ERROR, "Foundation returned a relative directory");
      Scope scope = category == TEMPORARY ? Scope::TEMPORARY : (TARGET_OS_IPHONE || category < DOCUMENTS ? Scope::APPLICATION : Scope::USER_DOMAIN);
      return success([path UTF8String], scope);
    } @catch (NSException *exception) {
      return failure(Status::ERROR, std::string("Foundation lookup failed: ") + [[exception name] UTF8String]);
    }
  }
}
} // namespace platform_paths

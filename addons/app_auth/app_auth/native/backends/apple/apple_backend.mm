// The iOS and macOS backend: AppAuth for iOS and macOS, built from its release's sources, presenting
// the system authentication session from Godot's window.
#include "app_auth/native/backend.h"
#import <Foundation/Foundation.h>
#import <TargetConditionals.h>
#if TARGET_OS_IPHONE
#import <UIKit/UIKit.h>
#else
#import <AppKit/AppKit.h>
#endif
#import "AppAuth.h"

namespace app_auth {
namespace {
// The presented flow; AppAuth requires it to stay alive until its callback. The shared layer
// starts at most one login at a time.
id<OIDExternalUserAgentSession> current_flow = nil;

std::string utf8(NSString *text) { return text ? std::string([text UTF8String]) : std::string(); }

void report_on_main(int64_t request_id, BackendResult result) {
  if (NSThread.isMainThread) {
    app_auth_report(request_id, std::move(result));
    return;
  }
  __block BackendResult moved = std::move(result);
  dispatch_async(dispatch_get_main_queue(), ^{
    app_auth_report(request_id, std::move(moved));
  });
}

bool is_network_error(NSError *error) {
  if ([error.domain isEqualToString:NSURLErrorDomain]) return true;
  if ([error.domain isEqualToString:OIDGeneralErrorDomain] &&
      (error.code == OIDErrorCodeNetworkError || error.code == OIDErrorCodeServerError)) {
    return true;
  }
  NSError *underlying = error.userInfo[NSUnderlyingErrorKey];
  return underlying && [underlying.domain isEqualToString:NSURLErrorDomain];
}

BackendResult failure_from_error(NSError *error) {
  if (!error) return failure(Status::ERROR, "AppAuth returned no result");
  if ([error.domain isEqualToString:OIDGeneralErrorDomain] &&
      (error.code == OIDErrorCodeUserCanceledAuthorizationFlow ||
       error.code == OIDErrorCodeProgramCanceledAuthorizationFlow)) {
    return failure(Status::CANCELLED, "The login was cancelled");
  }
  if ([error.domain isEqualToString:OIDOAuthAuthorizationErrorDomain] ||
      [error.domain isEqualToString:OIDOAuthTokenErrorDomain]) {
    NSDictionary *response = error.userInfo[OIDOAuthErrorResponseErrorKey];
    NSString *code = response[OIDOAuthErrorFieldError];
    NSString *description = response[OIDOAuthErrorFieldErrorDescription];
    BackendResult result = failure(Status::PROVIDER_ERROR, description.length
                                                               ? utf8(description)
                                                               : utf8(error.localizedDescription));
    result.provider_error = utf8(code);
    return result;
  }
  if (is_network_error(error)) {
    return failure(Status::NETWORK_ERROR,
                   "The identity provider could not be reached: " + utf8(error.localizedDescription));
  }
  return failure(Status::ERROR, utf8(error.localizedDescription));
}

id<OIDExternalUserAgent> external_user_agent() {
#if TARGET_OS_IPHONE
  UIViewController *presenting = nil;
  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:[UIWindowScene class]]) continue;
    UIWindowScene *window_scene = (UIWindowScene *)scene;
    UIWindow *window = nil;
    for (UIWindow *candidate in window_scene.windows) {
      if (candidate.isKeyWindow) window = candidate;
    }
    if (!window) window = window_scene.windows.firstObject;
    presenting = window.rootViewController;
    if (presenting && scene.activationState == UISceneActivationStateForegroundActive) break;
  }
  if (!presenting) return nil;
  while (presenting.presentedViewController) presenting = presenting.presentedViewController;
  return [[OIDExternalUserAgentIOS alloc] initWithPresentingViewController:presenting];
#else
  NSWindow *window = NSApp.keyWindow ?: NSApp.windows.firstObject;
  if (!window) return nil;
  return [[OIDExternalUserAgentMac alloc] initWithPresentingWindow:window];
#endif
}

void finish(int64_t request_id, BackendResult result) {
  current_flow = nil;
  report_on_main(request_id, std::move(result));
}

BackendResult result_from_token(OIDTokenResponse *token) {
  BackendResult result;
  result.status = Status::OK;
  result.access_token = utf8(token.accessToken);
  result.id_token = utf8(token.idToken);
  for (NSString *scope in [token.scope componentsSeparatedByString:@" "]) {
    if (scope.length) result.scopes.push_back(utf8(scope));
  }
  NSDate *expiry = token.accessTokenExpirationDate;
  result.expires_at = expiry ? (int64_t)expiry.timeIntervalSince1970 : 0;
  result.has_refresh_token = token.refreshToken != nil;
  return result;
}

void present(int64_t request_id, OIDAuthorizationRequest *authorization) {
  id<OIDExternalUserAgent> agent = external_user_agent();
  if (!agent) {
    finish(request_id, failure(Status::ERROR, "No window can present the login"));
    return;
  }
  current_flow = [OIDAuthState
      authStateByPresentingAuthorizationRequest:authorization
                              externalUserAgent:agent
                                       callback:^(OIDAuthState *state, NSError *error) {
                                         finish(request_id,
                                                state ? result_from_token(state.lastTokenResponse)
                                                      : failure_from_error(error));
                                       }];
}
} // namespace

bool app_auth_backend_is_supported() { return true; }

std::string app_auth_backend_default_scheme() {
  return utf8(NSBundle.mainBundle.bundleIdentifier);
}

std::string app_auth_backend_default_scheme_source() { return "the bundle identifier"; }

bool app_auth_backend_start(const BackendRequest &request) {
  NSURL *issuer = [NSURL URLWithString:@(request.issuer.c_str())];
  NSURL *redirect = [NSURL URLWithString:@(request.redirect_uri.c_str())];
  if (!issuer || !redirect) return false;
  NSString *client_id = @(request.client_id.c_str());
  NSMutableArray<NSString *> *scopes = [NSMutableArray array];
  for (const std::string &scope : request.scopes) [scopes addObject:@(scope.c_str())];
  const int64_t request_id = request.request_id;
  [OIDAuthorizationService
      discoverServiceConfigurationForIssuer:issuer
                                 completion:^(OIDServiceConfiguration *configuration, NSError *error) {
                                   if (!configuration) {
                                     finish(request_id, failure_from_error(error));
                                     return;
                                   }
                                   present(request_id, [[OIDAuthorizationRequest alloc]
                                                           initWithConfiguration:configuration
                                                                        clientId:client_id
                                                                          scopes:scopes
                                                                     redirectURL:redirect
                                                                    responseType:OIDResponseTypeCode
                                                            additionalParameters:nil]);
                                 }];
  return true;
}
} // namespace app_auth

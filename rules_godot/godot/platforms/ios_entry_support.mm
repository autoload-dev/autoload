// Symbols Godot's iOS entry point needs beside the engine library.
#import <UIKit/UIKit.h>

// Godot 4.7's vendored SDL references these helpers but does not include SDL's
// UIKit video backend that normally defines them. Query UIKit directly, just as
// that backend does. Weak definitions let a corrected/custom engine override us.
extern "C" __attribute__((weak)) bool SDL_IsIPad(void) {
  return [UIDevice currentDevice].userInterfaceIdiom == UIUserInterfaceIdiomPad;
}

extern "C" __attribute__((weak)) bool SDL_IsAppleTV(void) {
  return [UIDevice currentDevice].userInterfaceIdiom == UIUserInterfaceIdiomTV;
}

// Godot's entry point calls the embedded plugin hooks; rules_godot imports no plugins.
void godot_apple_embedded_plugins_initialize() {}

void godot_apple_embedded_plugins_deinitialize() {}

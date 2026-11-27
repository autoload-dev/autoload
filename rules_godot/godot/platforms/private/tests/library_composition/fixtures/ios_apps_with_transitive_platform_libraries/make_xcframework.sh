#!/usr/bin/env bash
# Assemble an XCFramework the way a vendor ships one: Info.plist plus one library per
# slice. Each example copies one library into both slices.
#
#   make_xcframework.sh static <root> <archives...>
#     A static XCFramework of the .a among the archives, as libhello_prebuilt.a.
#   make_xcframework.sh dynamic <root> <name> <library> [<framework>=<linked name>...]
#     A dynamic XCFramework of <name>.framework, whose binary identifies itself by its path
#     in an application's Frameworks directory and loads the named frameworks, which it
#     linked under their own shared library names.
set -euo pipefail

slices=(ios-arm64 ios-arm64_x86_64-simulator)
kind="$1"
root="$2"
shift 2

case "$kind" in
    static)
        archive=""
        for candidate in "$@"; do
            case "$candidate" in
                *.pic.a) ;;
                *.a) archive="$candidate" ;;
            esac
        done
        library_path="libhello_prebuilt.a"
        binary_path="$library_path"
        for slice in "${slices[@]}"; do
            mkdir -p "$root/$slice"
            cp "$archive" "$root/$slice/$library_path"
        done
        ;;
    dynamic)
        name="$1"
        library="$2"
        shift 2
        library_path="$name.framework"
        binary_path="$name.framework/$name"
        for slice in "${slices[@]}"; do
            framework="$root/$slice/$name.framework"
            mkdir -p "$framework"
            cp "$library" "$framework/$name"
            chmod u+w "$framework/$name"
            xcrun install_name_tool -id "@rpath/$binary_path" "$framework/$name"
            for dependency in "$@"; do
                xcrun install_name_tool -change "@rpath/${dependency#*=}" \
                    "@rpath/${dependency%%=*}.framework/${dependency%%=*}" "$framework/$name"
            done
            cat >"$framework/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>$name</string>
  <key>CFBundleIdentifier</key><string>org.example.rulesgodot.${name//[^A-Za-z0-9.]/-}</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>$name</string>
  <key>CFBundlePackageType</key><string>FMWK</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>MinimumOSVersion</key><string>15.0</string>
</dict>
</plist>
PLIST
        done
        ;;
    *)
        echo "unknown XCFramework kind: $kind" >&2
        exit 1
        ;;
esac

cat >"$root/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>AvailableLibraries</key>
  <array>
    <dict>
      <key>BinaryPath</key><string>$binary_path</string>
      <key>LibraryIdentifier</key><string>ios-arm64</string>
      <key>LibraryPath</key><string>$library_path</string>
      <key>SupportedArchitectures</key><array><string>arm64</string></array>
      <key>SupportedPlatform</key><string>ios</string>
    </dict>
    <dict>
      <key>BinaryPath</key><string>$binary_path</string>
      <key>LibraryIdentifier</key><string>ios-arm64_x86_64-simulator</string>
      <key>LibraryPath</key><string>$library_path</string>
      <key>SupportedArchitectures</key><array><string>arm64</string><string>x86_64</string></array>
      <key>SupportedPlatform</key><string>ios</string>
      <key>SupportedPlatformVariant</key><string>simulator</string>
    </dict>
  </array>
  <key>CFBundlePackageType</key><string>XFWK</string>
  <key>XCFrameworkFormatVersion</key><string>1.0</string>
</dict>
</plist>
PLIST

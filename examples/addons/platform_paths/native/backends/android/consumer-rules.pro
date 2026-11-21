-keepattributes RuntimeVisibleAnnotations,RuntimeInvisibleAnnotations
-keep class org.example.platformpaths.PlatformPathsAndroidPlugin { public <init>(org.godotengine.godot.Godot); }
-keepclassmembers class org.example.platformpaths.PlatformPathsAndroidPlugin {
    @org.godotengine.godot.plugin.UsedByGodot <methods>;
}

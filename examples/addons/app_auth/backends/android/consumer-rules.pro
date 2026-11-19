-keepattributes RuntimeVisibleAnnotations,RuntimeInvisibleAnnotations
-keep class org.example.appauth.AppAuthAndroidPlugin { public <init>(org.godotengine.godot.Godot); }
-keepclassmembers class org.example.appauth.AppAuthAndroidPlugin {
    @org.godotengine.godot.plugin.UsedByGodot <methods>;
}

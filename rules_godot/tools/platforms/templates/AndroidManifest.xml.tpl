<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.godot.game"
    android:installLocation="auto"
    android:versionCode="{VERSION_CODE}"
    android:versionName="{VERSION_NAME}">

    <uses-sdk
        android:minSdkVersion="{MIN_SDK_VERSION}"
        android:targetSdkVersion="{TARGET_SDK_VERSION}" />

{PERMISSIONS}
    <supports-screens
        android:largeScreens="{LARGE_SCREENS}"
        android:normalScreens="{NORMAL_SCREENS}"
        android:smallScreens="{SMALL_SCREENS}"
        android:xlargeScreens="{XLARGE_SCREENS}" />

    <uses-feature
        android:glEsVersion="0x00030000"
        android:required="true" />

{VULKAN_FEATURES}
    <application
        android:label="{APP_NAME}"
        android:icon="@mipmap/icon"
        android:allowBackup="{ALLOW_BACKUP}"
{APP_CATEGORY}
        android:extractNativeLibs="{EXTRACT_NATIVE_LIBS}"
        android:hasCode="true"
        android:hasFragileUserData="{HAS_FRAGILE_USER_DATA}"
        android:isGame="{IS_GAME}"
        android:requestLegacyExternalStorage="{REQUEST_LEGACY_EXTERNAL_STORAGE}">

        <profileable
            android:enabled="true"
            android:shell="true" />

        <meta-data
            android:name="org.godotengine.editor.version"
            android:value="{EDITOR_VERSION}" />

        <meta-data
            android:name="org.godotengine.rendering.method"
            android:value="{RENDERING_METHOD}" />
{LAUNCH_ARGUMENTS_PLUGIN}

        <activity
            android:name="com.godot.game.GodotApp"
            android:configChanges="{CONFIG_CHANGES}"
            android:excludeFromRecents="{EXCLUDE_FROM_RECENTS}"
            android:exported="false"
            android:launchMode="singleInstancePerTask"
            android:resizeableActivity="{RESIZEABLE}"
            android:screenOrientation="{ORIENTATION}"
            android:supportsPictureInPicture="true"
            android:theme="@style/GodotAppSplashTheme"
            android:windowSoftInputMode="adjustResize" />

        <activity-alias
            android:name="com.godot.game.GodotAppLauncher"
            android:exported="true"
            android:targetActivity="com.godot.game.GodotApp">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.DEFAULT" />
{LAUNCHER_CATEGORIES}
            </intent-filter>
        </activity-alias>
    </application>
</manifest>

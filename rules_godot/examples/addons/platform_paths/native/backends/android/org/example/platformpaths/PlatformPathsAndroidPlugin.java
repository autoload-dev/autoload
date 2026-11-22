package org.example.platformpaths;

import android.app.Activity;
import android.content.Context;
import android.os.Environment;
import java.io.File;
import org.godotengine.godot.Godot;
import org.godotengine.godot.plugin.GodotPlugin;
import org.godotengine.godot.plugin.UsedByGodot;

/** The platform backend; consuming scripts use PlatformPaths through GDExtension. */
public final class PlatformPathsAndroidPlugin extends GodotPlugin {
    public PlatformPathsAndroidPlugin(Godot godot) {
        super(godot);
    }

    @Override
    public String getPluginName() {
        return "PlatformPathsAndroid";
    }

    @UsedByGodot
    public String[] resolve(int category) {
        Activity activity = getActivity();
        if (activity == null || activity.getApplicationContext() == null) {
            return new String[] {"integration_unavailable", "", "Android application context is unavailable"};
        }
        Context context = activity.getApplicationContext();
        try {
            File directory;
            switch (category) {
                case 0:
                case 2:
                    directory = context.getCacheDir();
                    break;
                case 1:
                    directory = context.getFilesDir();
                    break;
                case 3:
                    directory = context.getDir("documents", Context.MODE_PRIVATE);
                    break;
                case 4:
                    directory = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                    break;
                default:
                    return new String[] {"error", "", "Unknown directory category"};
            }
            if (directory == null) {
                return new String[] {"unavailable", "", "Android storage location is unavailable"};
            }
            return new String[] {"ok", directory.getAbsolutePath(), ""};
        } catch (RuntimeException exception) {
            return new String[] {"error", "", "Android storage lookup failed: " + exception.getClass().getSimpleName()};
        }
    }
}

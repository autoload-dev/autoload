package com.godot.game;

import android.app.Activity;
import android.content.pm.ApplicationInfo;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.godotengine.godot.Godot;
import org.godotengine.godot.plugin.GodotPlugin;

/**
 * Passes the Godot arguments of `bazel run` to the engine of a debuggable application.
 *
 * <p>Godot's own command_line_params extra does not serve: GodotActivity drops it from
 * intents that target an exported activity, such as the launcher alias, and adb may not
 * start the activity Godot reads it from, which is not exported. Any application could
 * send an intent extra, so the launcher of tools/platforms/launch writes the arguments
 * with adb's run-as into this application's private files instead, which no other
 * application can write; this plugin reads them once and deletes them. Godot appends a
 * plugin's parameters after those of the exported assets/_cl_ file, so an option given
 * to both takes the launcher's value. Release builds (-c opt) leave this plugin out.
 */
public final class LaunchArgumentsPlugin extends GodotPlugin {
	/** The file below getFilesDir() that holds the arguments, separated by NUL. */
	public static final String FILE = "rules_godot_launch_arguments";

	public LaunchArgumentsPlugin(Godot godot) {
		super(godot);
	}

	@Override
	public String getPluginName() {
		return "RulesGodotLaunchArguments";
	}

	@Override
	public List<String> getCommandLineParams(List<String> original) {
		Activity activity = getActivity();
		if (activity == null || (activity.getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) == 0) {
			return Collections.emptyList();
		}
		File file = new File(activity.getFilesDir(), FILE);
		if (!file.isFile()) {
			return Collections.emptyList();
		}
		String text;
		try (InputStream input = new FileInputStream(file)) {
			ByteArrayOutputStream bytes = new ByteArrayOutputStream();
			byte[] buffer = new byte[4096];
			for (int count; (count = input.read(buffer)) != -1; ) {
				bytes.write(buffer, 0, count);
			}
			text = new String(bytes.toByteArray(), StandardCharsets.UTF_8);
		} catch (IOException e) {
			return Collections.emptyList();
		} finally {
			// One launch takes them; a later start from the launcher icon does not.
			file.delete();
		}
		List<String> arguments = new ArrayList<>();
		for (String argument : text.split("\0")) {
			if (!argument.isEmpty()) {
				arguments.add(argument);
			}
		}
		return arguments;
	}
}

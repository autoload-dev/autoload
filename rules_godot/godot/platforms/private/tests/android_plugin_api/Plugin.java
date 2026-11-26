package org.example.plugin;

import org.godotengine.godot.Godot;
import org.godotengine.godot.plugin.GodotPlugin;

/** An Android plugin that compiles against Godot's classes. */
public class Plugin extends GodotPlugin {
    public Plugin(Godot godot) {
        super(godot);
    }

    @Override
    public String getPluginName() {
        return "Plugin";
    }
}

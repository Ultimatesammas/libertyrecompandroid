package com.libertyrecomp;

import java.io.File;

/** Driver/resources/log setup is shared; the game receives EFLC-specific paths. */
public final class EflcGameActivity extends LibertyActivity {
    @Override protected String[] getArguments() {
        File base = getExternalFilesDir(null);
        if (base == null) base = getFilesDir();
        File root = new File(base, "EFLC");
        return new String[] {
            "--gpu_plugin=xenos", "--game_data_root=" + new File(root, "game"),
            "--user_data_root=" + new File(root, "saves"),
            "--saved_game_root=" + new File(root, "saves"),
            "--cache_root=" + new File(root, "shader_cache"),
            "--metadata_root=" + new File(root, "metadata"),
            "--log_level=info", "--diagnostics=true", "--diagnostics_categories=logging"
        };
    }
    @Override public void loadLibraries() {
        try { android.system.Os.unsetenv("TU_DEBUG"); } catch (Exception ignored) {}
        super.loadLibraries();
    }
}

# Thor test APK — installation and acceptance

This is an experimental controller correction, not a certified 60 FPS build.

## Install using only the Thor

Download the APK artifact ZIP from this fork's Actions run, extract it, and install
`LibertyRecomp-Thor-test.apk`. It appears as **Liberty Recomp Thor Test**.

The package ID is `com.libertyrecomp.thor`. It installs beside the official app;
do not uninstall the official app. Its existing game files and saves remain in
the official app's separate data directory. The test app needs its own game
installation through the launcher's existing game/update installer. Existing
saves are not automatically imported across the Android app boundary.

Baseline and test APKs in ONE artifact have the same signing key and package ID.
Install one over the other to compare without uninstalling or clearing data.
Separate workflow runs may have different debug keys; do not uninstall a test
app with wanted saves just to resolve a signature mismatch.

## Changes and limits

- The quality controller now follows 30/40/60/120 FPS limits, resets history on
  limit changes, and restores its published factor on disable.
- A 1080p-output/FSR1 Quality/60 FPS test profile is used for a new installation.
  At 16:9 and a selected 1080p output this means 720p scene rendering, not native
  1080p detail. Existing per-app settings still take precedence after first use.
- The official 0.5.9 game, save runtime, installer and driver libraries are retained
  byte-for-byte. Only the native renderer is rebuilt. Checks compare those bytes.
- This rebuild lacks the author's unpublished renderer PGO profile. A logical
  correction is demonstrated; overall FPS might improve or regress and needs A/B.
- The inherited skipped-light-shader workaround and known crashes are not repaired
  by this controller patch. The normal offline/local save path is retained.
- No Microsoft account is required by that local save implementation. A game's
  login prompt is still a failure to investigate, not permission to bypass checks.

## Required acceptance on the real Thor

Before playing for progress you want to keep:

1. Start a new game and complete enough of the intro to reach the safehouse.
2. Create a manual save in a free slot and confirm that the game reports success.
3. Exit the app normally. Close it from Android, reopen it and load that save.
4. Confirm mission/progress/location, then test an autosave and reload it too.
5. Report any login prompt, failure or crash with **Play (Debug Log)** and the
   launcher's saved crash report. Do not declare saving reliable until these pass.

For performance, use the same save/scene/settings on the baseline and test APK.
Test daylight shadows, night/bridge views, water, dense driving, collisions and
cutscenes, both cold and warm shader caches. Test after 30 minutes for thermal
slowdown. Average FPS alone does not establish smooth 60 FPS.

## Validation boundaries

The cloud job runs the actual controller method bodies with fake cvars/clocks
and tests existing quicksave eligibility. It compiles the Android renderer,
packages the APKs, verifies APK signatures/package identity and compares retained
native binaries against the hash-pinned official APK. These checks do not execute
the game or prove device-side saving, loading, correctness or frame rate.

The reference APK is pinned to release 0.5.9 and SHA-256
`7788cd4b55cdaa66aaeba66b5bd465242fbd7c3c00b57382bfd8ff2f02a4e4f6`.

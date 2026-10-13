#!/bin/bash
# Renderer-only rebuild. Preserve the official 0.5.9 PGO game/save runtime.
set -euo pipefail
export JAVA_HOME="$(cygpath -u "$JAVA_HOME")"
export ANDROID_HOME="$(cygpath -u "$ANDROID_HOME")"
export ANDROID_NDK="$ANDROID_HOME/ndk/29.0.14206865"
. "$(dirname "$0")/env.sh"
python "$REPO/tools/stage_thor_baseline.py"
python "$APP_DIR/scripts/materialize_symlinks.py"
"$APP_DIR/scripts/setup_host_tools.sh"

# The reference APK has the same namespace/classes but a distinct application ID.
# Baseline and patched APK are signed in the same job for reversible A/B updates.
mkdir -p "$REPO/out/thor-apks"
bash "$APP_DIR/scripts/build_apk.sh" debug
cp "$APP_DIR/app/build/outputs/apk/debug/app-debug.apk" "$REPO/out/thor-apks/Thor-baseline.apk"
python "$REPO/tools/verify_thor_apk.py" "$REPO/out/thor-apks/Thor-baseline.apk"

cmake -S "$REPO" -B "$BUILD_DIR" -G Ninja \
  -DCMAKE_C_FLAGS="-march=armv8.2-a -fno-emulated-tls" \
  -DCMAKE_CXX_FLAGS="-march=armv8.2-a -fno-emulated-tls" \
  -DCMAKE_TOOLCHAIN_FILE="$REPO/toolchains/android.cmake" \
  -DANDROID_NDK="$ANDROID_NDK" -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-28 -DANDROID_STL=c++_shared \
  -DLIBERTY_RECOMP_TARGET_PLATFORM=android \
  -DLIBERTY_RECOMP_ANDROID_RUNTIME_ASSETS=ON \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DREXGLUE_ENABLE_TRACY=OFF -DLIBERTY_ANDROID_RENDERER_THINLTO_JOBS=2 \
  -DGTA4_NATIVE_SPIRV_VAL="$(cygpath -m "$ANDROID_NDK/shader-tools/windows-x86_64/spirv-val.exe")" \
  -DGTA4_NATIVE_GLSLANG_VALIDATOR="$(cygpath -m "$REPO/out/host-tools/glslang/bin/glslangValidator.exe")" \
  -DGTA4_NATIVE_DXC_LIBRARY_PATH="$(cygpath -m "$REPO/out/host-tools/dxc/bin/x64")"
cmake --build "$BUILD_DIR" --target rexgpu-gta4-native --parallel 2
"$NDK_BIN/llvm-strip" --strip-unneeded \
  -o "$JNILIBS/librexgpu-gta4-native.so" "$REX_OUT_DIR/librexgpu-gta4-native.so"

# Do not copy the newly built runtime: saving/game code must remain byte-identical.
rm -f "$APP_DIR/app/build/outputs/apk/debug/app-debug.apk"
bash "$APP_DIR/scripts/build_apk.sh" debug
cp "$APP_DIR/app/build/outputs/apk/debug/app-debug.apk" "$REPO/out/thor-apks/LibertyRecomp-Thor-test.apk"
python "$REPO/tools/verify_thor_apk.py" --modified "$REPO/out/thor-apks/LibertyRecomp-Thor-test.apk"

APKSIGNER="$ANDROID_HOME/build-tools/35.0.0/apksigner.bat"
AAPT="$ANDROID_HOME/build-tools/35.0.0/aapt.exe"
for apk in "$REPO/out/thor-apks/"*.apk; do
  "$APKSIGNER" verify --verbose --print-certs "$(cygpath -m "$apk")" > "$apk.signing.txt"
  cat "$apk.signing.txt"
  "$AAPT" dump badging "$(cygpath -m "$apk")" > "$apk.badging.txt"
  grep -q "name='com.libertyrecomp.thor'" "$apk.badging.txt"
  grep -q "launchable-activity: name='com.libertyrecomp.LauncherActivity'" "$apk.badging.txt"
done
python - <<'PY'
import hashlib,json,os,pathlib
root=pathlib.Path.cwd()
apks=root/'out/thor-apks'
data={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in apks.glob('*.apk')}
certificates=[]
for p in apks.glob('*.apk.signing.txt'):
    certificates.extend(line.strip() for line in p.read_text().splitlines()
                        if 'certificate SHA-256 digest:' in line)
assert len(certificates)==2 and len(set(certificates))==1, 'A/B signing certificates differ'
data['commit']=os.environ.get('GITHUB_SHA','local')
data['validation']='Build and packaging only; no device FPS or save/load acceptance yet.'
(apks/'build-validation.json').write_text(json.dumps(data,indent=2))
PY
cp "$REPO/docs/android/THOR-TEST.md" "$REPO/out/thor-apks/READ-ME.md"

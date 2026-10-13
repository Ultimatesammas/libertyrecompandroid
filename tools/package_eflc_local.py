#!/usr/bin/env python3
"""Package a private EFLC start-test APK with the official Android build tools.

Uses aapt2, javac, D8, zipalign and apksigner directly. No Gradle repository
access or generated game-source publication is needed.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE_SHA = "7788cd4b55cdaa66aaeba66b5bd465242fbd7c3c00b57382bfd8ff2f02a4e4f6"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk", "jdk", "sdl-java", "baseline", "native", "out"):
        p.add_argument("--" + name, type=pathlib.Path, required=True)
    a = p.parse_args()
    tools = a.sdk / "build-tools/35.0.0"
    android = a.sdk / "platforms/android-35/android.jar"
    env = dict(os.environ)
    env["JAVA_HOME"] = str(a.jdk)
    env["PATH"] = str(a.jdk / "bin") + os.pathsep + env.get("PATH", "")
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    def run(command):
        subprocess.run(list(map(str, command)), check=True, env=env)
    if hashlib.sha256(a.baseline.read_bytes()).hexdigest() != BASELINE_SHA:
        raise ValueError("Official baseline APK checksum mismatch")
    app = ROOT / "os/android/app/src"
    manifest = ET.parse(app / "eflc/AndroidManifest.xml")
    manifest.getroot().set("package", "com.libertyrecomp")
    ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
    manifest_path = out / "AndroidManifest.xml"
    manifest.write(manifest_path, encoding="utf-8", xml_declaration=True)
    resources = out / "resources.zip"
    run([tools / "aapt2", "compile", "--dir", app / "main/res", "-o", resources])
    rjava = out / "r-java"
    run([tools / "aapt2", "link", "--manifest", manifest_path, "-I", android,
         "--java", rjava, "--custom-package", "com.libertyrecomp",
         "--rename-manifest-package", "com.libertyrecomp.eflctest",
         "--min-sdk-version", "29", "--target-sdk-version", "35",
         "--version-code", "20001", "--version-name", "0.5.9-eflc-start-test.1",
         "-o", out / "resource-apk.apk", resources])
    classes = out / "classes"
    classes.mkdir(exist_ok=True)
    sources = sorted((app / "main/java").rglob("*.java")) + sorted((app / "eflc/java").rglob("*.java"))
    sources += sorted(a.sdl_java.rglob("*.java")) + sorted(rjava.rglob("*.java"))
    response = out / "javac-sources.txt"
    response.write_text("\n".join('"' + str(path) + '"' for path in sources) + "\n")
    run([a.jdk / "bin/javac", "-encoding", "UTF-8", "-source", "17", "-target", "17",
         "-classpath", android, "-d", classes, "@" + str(response)])
    jar = out / "classes.jar"
    with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(classes.rglob("*.class")):
            z.write(path, str(path.relative_to(classes)))
    dex = out / "dex"
    dex.mkdir(exist_ok=True)
    run([a.jdk / "bin/java", "-cp", tools / "lib/d8.jar", "com.android.tools.r8.D8",
         "--min-api", "29", "--lib", android, "--output", dex, jar])
    unsigned = out / "unsigned.apk"
    native = a.native.read_bytes()
    libraries = {}
    with zipfile.ZipFile(out / "resource-apk.apk") as resource_zip, zipfile.ZipFile(a.baseline) as base, zipfile.ZipFile(unsigned, "w", zipfile.ZIP_DEFLATED) as z:
        for name in resource_zip.namelist():
            z.writestr(name, resource_zip.read(name))
        for path in sorted(dex.glob("*.dex")):
            z.write(path, path.name)
        for name in base.namelist():
            if name.startswith("lib/arm64-v8a/"):
                data = native if name.endswith("/libmain.so") else base.read(name)
                z.writestr(name, data)
                libraries[name] = hashlib.sha256(data).hexdigest()
            elif name.startswith("assets/"):
                z.writestr(name, base.read(name))
    aligned = out / "aligned.apk"
    run([tools / "zipalign", "-f", "4", unsigned, aligned])
    key = out / "eflc-debug.keystore"
    if not key.exists():
        run([a.jdk / "bin/keytool", "-genkeypair", "-keystore", key, "-storepass", "android",
             "-keypass", "android", "-alias", "androiddebugkey", "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10000", "-dname", "CN=Android Debug,O=Android,C=US"])
    target = out / "LibertyRecomp-EFLC-start-test.apk"
    run([tools / "apksigner", "sign", "--ks", key, "--ks-key-alias", "androiddebugkey",
         "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", target, aligned])
    with (out / "signing-validation.txt").open("w") as log:
        subprocess.run([str(tools / "apksigner"), "verify", "--verbose", "--print-certs", str(target)],
                       check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
    with (out / "badging.txt").open("w") as log:
        subprocess.run([str(tools / "aapt"), "dump", "badging", str(target)], check=True,
                       env=env, stdout=log, stderr=subprocess.STDOUT)
    badging = (out / "badging.txt").read_text()
    if "name='com.libertyrecomp.eflctest'" not in badging or "launchable-activity: name='com.libertyrecomp.EflcLauncherActivity'" not in badging:
        raise ValueError("Wrong package or launcher")
    (out / "apk-validation.json").write_text(json.dumps({
        "apk":target.name, "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
        "native_libraries":libraries, "game_assets_included":False,
        "device_gameplay_save_load_fps_verified":False,
        "kind":"Private EFLC start test, not the completed Thor performance port"
    },indent=2))
    print("Signed start-test APK:", target)


if __name__ == "__main__":
    main()

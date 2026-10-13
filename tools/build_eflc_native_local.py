#!/usr/bin/env python3
"""Compile private EFLC generated code locally, retaining the official runtime.

No upload or public source export occurs. This is a start-test build, not a
validated performance port. SDK headers must match the pinned source checkout.
"""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ndk", type=pathlib.Path, required=True)
    p.add_argument("--generated", type=pathlib.Path, required=True)
    p.add_argument("--public-sdk", type=pathlib.Path, required=True)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--jobs", type=int, default=4)
    a = p.parse_args()
    sdk = ROOT / "glue/rexglue-sdk-main"
    toolchain = a.ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    compiler = toolchain / "aarch64-linux-android28-clang++"
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    generated = a.generated.resolve()
    header = (generated / "eflc_init.h").read_text()
    if "REX_CODE_SIZE 0x945F5C" not in header or "REX_IMAGE_BASE 0x82000000" not in header:
        raise ValueError("Generated image does not match the inspected EFLC executable")
    libraries = ROOT / "os/android/app/src/main/jniLibs/arm64-v8a"
    includes = [sdk / "include", a.public_sdk / "include", generated,
                sdk / "thirdparty/imgui", sdk / "thirdparty/inja/third_party/include",
                sdk / "src"]
    flags = ["-std=c++23", "-O2", "-g0", "-fPIC", "-fno-strict-aliasing",
             "-ffp-contract=off", "-march=armv8.2-a", "-fno-emulated-tls",
             "-DNDEBUG", "-DFMT_HEADER_ONLY=1", "-DSPDLOG_FMT_EXTERNAL=1",
             '-DREXGLUE_BUILD_CONFIG="Release"']
    for include in includes:
        flags += ["-I", str(include)]
    sources = sorted(generated.glob("*.cpp")) + [
        ROOT / "os/android/eflc-native/eflc_main.cpp",
        sdk / "src/ui/rex_app.cpp", sdk / "src/ui/windowed_app_main_sdl.cpp"]
    def compile_source(item):
        index, source = item
        obj = out / f"{index:03d}-{source.stem}.o"
        command = [str(compiler), *flags, "-c", str(source), "-o", str(obj)]
        log = out / f"{index:03d}.log"
        with log.open("w") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"Compilation failed: {source.name}\n{log.read_text()[-12000:]}")
        return obj
    objects = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        futures = {pool.submit(compile_source, item):item[1] for item in enumerate(sources)}
        for future in concurrent.futures.as_completed(futures):
            objects.append(future.result())
            print(f"Compiled {len(objects)}/{len(sources)}: {futures[future].name}", flush=True)
    target = out / "libmain.so"
    command = [str(compiler), "-shared", "-o", str(target), *map(str, objects),
               "-L", str(libraries), "-lrexruntime", "-lSDL3", "-landroid", "-llog", "-ldl",
               "-Wl,--no-undefined", "-Wl,-soname,libmain.so", "-Wl,-z,max-page-size=16384",
               "-Wl,-Bsymbolic-functions", "-Wl,--export-dynamic-symbol=SDL_main"]
    subprocess.run(command, check=True)
    subprocess.run([str(toolchain / "llvm-strip"), "--strip-unneeded", str(target)], check=True)
    (out / "native-build.json").write_text(json.dumps({
        "kind":"EFLC start test", "compiler":subprocess.check_output([str(compiler),"--version"],text=True),
        "sources":len(sources), "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
        "gpu":"xenos", "device_acceptance":False,
        "note":"No claim of working gameplay, save/load or 60 FPS until tested on Thor."
    },indent=2))
    print("Built", target, flush=True)


if __name__ == "__main__":
    main()

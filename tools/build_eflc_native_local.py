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
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def split_registration(source, batch_size=256):
    """Split a huge straight-line registrar without changing any call/order."""
    if batch_size < 1:
        raise ValueError("Invalid registration batch size")
    signature = "void eflc_RegisterFunctions(rex::runtime::IModuleRegistrar* registrar)"
    at = source.index(signature)
    prefix = source[:at]
    body = source[at + len(signature):].strip()
    if not body.startswith("{") or not body.endswith("}"):
        raise ValueError("Unexpected generated registrar structure")
    body = body[1:-1]
    pattern = r"registrar->SetFunction\(0x[0-9A-Fa-f]+, [A-Za-z_][A-Za-z_0-9]*\);"
    calls = re.findall(pattern, body)
    if not calls or re.sub(pattern, "", body).strip():
        raise ValueError("Registrar contains unsupported statements")
    chunks = []
    names = []
    for index, offset in enumerate(range(0, len(calls), batch_size)):
        name = f"eflc_generated_registration_chunk_{index}"
        names.append(name)
        chunks.append(f"static void {name}(rex::runtime::IModuleRegistrar* registrar) {{\n"
                      + "\n".join(calls[offset:offset + batch_size]) + "\n}\n")
    result = prefix + "\n".join(chunks) + signature + " {\n"
    result += "\n".join(f"  {name}(registrar);" for name in names) + "\n}\n"
    if re.findall(pattern, result) != calls:
        raise ValueError("Registration sequence changed")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ndk", type=pathlib.Path, required=True)
    p.add_argument("--generated", type=pathlib.Path, required=True)
    p.add_argument("--public-sdk", type=pathlib.Path, required=True)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--previous-generated", type=pathlib.Path)
    p.add_argument("--reuse-objects", type=pathlib.Path)
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
    reusable = {}
    if bool(a.previous_generated) != bool(a.reuse_objects):
        raise ValueError("Object reuse requires both previous-generated and reuse-objects")
    if a.previous_generated:
        # For this same-checkout rebuild, only new forward declarations may
        # differ. Never reuse objects across an image/macro/SDK-header change.
        prior_header = (a.previous_generated / "eflc_init.h").read_text()
        normalize = lambda text: re.sub(r"^DECLARE_REX_FUNC\([^\n]*\);\n", "", text, flags=re.M)
        if normalize(prior_header) != normalize(header):
            raise ValueError("Generated header changed beyond function declarations")
        prior = json.loads((a.reuse_objects / "native-build.json").read_text())
        compiler_version = subprocess.check_output([str(compiler), "--version"], text=True)
        if prior["compiler"] != compiler_version:
            raise ValueError("Compiler differs from previous successful build")
        old_sources = sorted(a.previous_generated.glob("*.cpp"))
        for index, old_source in enumerate(old_sources):
            obj = a.reuse_objects / f"{index:03d}-{old_source.stem}.o"
            reusable[old_source.name] = (old_source, obj)
    def compile_source(item):
        index, source = item
        obj = out / f"{index:03d}-{source.stem}.o"
        if source.parent == generated and source.name in reusable:
            old_source, old_obj = reusable[source.name]
            if old_obj.is_file() and old_source.read_bytes() == source.read_bytes():
                print(f"Reused unchanged generated unit: {source.name}", flush=True)
                return old_obj
        compile_flags = list(flags)
        if source.name == "eflc_register.cpp":
            # Tens of thousands of straight-line registration calls run only
            # at module load. O0 avoids expensive, unnecessary bulk optimization.
            compile_flags[compile_flags.index("-O2")] = "-O0"
            # Avoid quadratic compiler work on a single tens-of-thousands-call
            # basic block. Preserve the exact calls and order in small blocks.
            batched = out / "eflc_registration_batched.cpp"
            batched.write_text(split_registration(source.read_text()))
            source = batched
        command = [str(compiler), *compile_flags, "-c", str(source), "-o", str(obj)]
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

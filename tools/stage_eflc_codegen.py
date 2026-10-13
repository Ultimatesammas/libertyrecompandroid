#!/usr/bin/env python3
"""Stage private EFLC inputs and run strict analysis using ReXGlue SDK 0.9.0.

The output contains game-derived code and the original user-supplied XEX.
Choose an output directory outside the public repository. This does not build
an Android APK or migrate title hooks.
"""
import argparse
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED = "590accf1a74b70ff3b4181090367fe702aa6a7a12059a04414d55c8ca514a140"


def check_input(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Executable exceeds inspection limit")
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError("Configuration does not match this executable SHA256")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xex", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--rexglue", type=pathlib.Path, required=True)
    args = parser.parse_args()
    check_input(args.xex)
    out = args.out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError("Use a private output directory outside the repository")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory must be empty")
    version = subprocess.run([str(args.rexglue), "--version"], check=True,
                             text=True, capture_output=True).stdout
    if version.strip() != "0.9.0":
        raise ValueError("This configuration was checked with SDK 0.9.0 only")
    (out / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.xex, out / "assets/default.xex")
    shutil.copyfile(ROOT / "tools/eflc_codegen/eflc_config.toml", out / "eflc_config.toml")
    (out / "eflc_manifest.toml").write_text('''[project]
name = "eflc"
sdk_version = "0.9.0"
game_root = "assets"

[entrypoint]
file_path = "assets/default.xex"
out_directory_path = "generated/default"
includes = ["eflc_config.toml"]
''')
    # No --force: unresolved analysis errors must fail rather than emit a
    # superficially successful but invalid code generation result.
    subprocess.run([str(args.rexglue), "--log-file", str(out / "codegen.log"),
                    "codegen", "eflc_manifest.toml"], cwd=out, check=True)
    if "[error]" in (out / "codegen.log").read_text():
        raise RuntimeError("Code generation reported errors")
    print("Strict EFLC code generation passed; hooks, assets and Android build remain unverified.")


if __name__ == "__main__":
    main()

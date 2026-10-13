#!/usr/bin/env python3
"""Stage only the native libraries/resources from the hash-pinned release APK.

The official optimized game, runtime, installer and driver binaries are retained.
No game payload or save files are included in that release APK.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = ('https://github.com/vaduur/LibertyRecompAndroid/releases/download/'
       'v0.5.9/LibertyRecompAndroid-v0.5.9.apk')
SHA256 = '7788cd4b55cdaa66aaeba66b5bd465242fbd7c3c00b57382bfd8ff2f02a4e4f6'
REQUIRED = {'libmain.so', 'librexruntime.so', 'librexgpu-gta4-native.so',
            'libliberty_install.so', 'libSDL3.so', 'libc++_shared.so', 'libvulkan.so'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apk', type=Path, default=ROOT / 'out/upstream-v0.5.9.apk')
    args = parser.parse_args()
    apk = args.apk
    apk.parent.mkdir(parents=True, exist_ok=True)
    if not apk.exists():
        request = urllib.request.Request(URL, headers={'User-Agent':'LibertyRecomp-Thor-build'})
        with urllib.request.urlopen(request, timeout=120) as src, apk.open('wb') as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
    if hashlib.sha256(apk.read_bytes()).hexdigest() != SHA256:
        raise SystemExit('Upstream APK checksum mismatch; refusing to stage binaries.')
    libs = ROOT / 'os/android/app/src/main/jniLibs/arm64-v8a'
    assets = ROOT / 'os/android/app/src/main/assets'
    libs.mkdir(parents=True, exist_ok=True)
    # Fail rather than mix pre-existing binaries from another build.
    if any(libs.glob('*.so')):
        raise SystemExit('Staging directory is not empty; use a clean checkout.')
    hashes = {}
    with zipfile.ZipFile(apk) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts:
                raise SystemExit('Unsafe path in upstream APK.')
            destination = None
            if len(path.parts) == 3 and path.parts[:2] == ('lib','arm64-v8a'):
                if path.suffix == '.so':
                    destination = libs / path.name
            elif len(path.parts) > 2 and path.parts[:2] == ('assets','Resources'):
                destination = assets / Path(*path.parts[1:])
            if destination is None or member.is_dir():
                continue
            data = archive.read(member)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            if destination.parent == libs:
                hashes[destination.name] = hashlib.sha256(data).hexdigest()
    if not REQUIRED <= hashes.keys():
        raise SystemExit(f'Missing baseline libraries: {REQUIRED-hashes.keys()}')
    (ROOT / 'out').mkdir(parents=True, exist_ok=True)
    (ROOT / 'out/thor-baseline-libraries.json').write_text(json.dumps(hashes, indent=2))
    print(f'Hash verified; retained {len(hashes)} official libraries and title resources.')


if __name__ == '__main__':
    main()

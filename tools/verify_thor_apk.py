#!/usr/bin/env python3
"""Check packaged retained binaries and required assets, not gameplay."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path)
    parser.add_argument('--modified', action='store_true')
    args = parser.parse_args()
    hashes = json.loads((ROOT / 'out/thor-baseline-libraries.json').read_text())
    with zipfile.ZipFile(args.apk) as archive:
        assert archive.testzip() is None, 'APK ZIP integrity failure'
        for name, original in hashes.items():
            value = hashlib.sha256(archive.read('lib/arm64-v8a/' + name)).hexdigest()
            if args.modified and name == 'librexgpu-gta4-native.so':
                assert value != original, 'Modified renderer was not packaged'
            else:
                assert value == original, f'Unexpected change to retained library {name}'
        expected_args = (ROOT / 'os/android/app/src/main/assets/default_args.txt').read_bytes()
        assert archive.read('assets/default_args.txt') == expected_args
        assert any(n.startswith('assets/Resources/font_atlases/') for n in archive.namelist())
    print('PASS: APK integrity, retained game/save runtime binaries, resources, profile')
    print('NOTE: saving/loading and sustained FPS still require a real Thor test.')


if __name__ == '__main__':
    main()

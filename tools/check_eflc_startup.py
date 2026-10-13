#!/usr/bin/env python3
"""Require all exact EFLC CRT initializer targets to have native mappings.

The two pointer ranges are verified against sub_82A185B0 in the inspected
executable. This check covers startup-table dispatch, not all indirect calls
or device gameplay. No missing call is replaced with a stub.
"""
import argparse
import hashlib
import pathlib
import re
import struct
from audit_eflc_xex import decode_xex

EXPECTED = "590accf1a74b70ff3b4181090367fe702aa6a7a12059a04414d55c8ca514a140"
RANGES = ((0x82A916B4, 0x82A916C0), (0x82A90010, 0x82A916B0))
CALLBACK_TARGETS = (0x82875EB0,)


def check(image, mappings, *, base=0x82000000, ranges=RANGES,
          code_begin=0x82140000, code_end=0x82A85F5C, required_callbacks=()):
    targets = set()
    for begin, end in ranges:
        if begin % 4 or end % 4 or begin < base or end < begin or end - base > len(image):
            raise ValueError("Initializer pointer range outside decoded image")
        for at in range(begin, end, 4):
            target = struct.unpack_from(">I", image, at - base)[0]
            if target in (0, 0xFFFFFFFF):
                continue
            if target % 4 or not code_begin <= target < code_end:
                raise ValueError(f"Invalid initializer pointer {target:08X}")
            targets.add(target)
    missing = (targets | set(required_callbacks)) - mappings
    if missing:
        raise ValueError("Unregistered startup targets: " + ", ".join(f"{x:08X}" for x in sorted(missing)))
    return len(targets)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xex", type=pathlib.Path)
    parser.add_argument("generated", type=pathlib.Path)
    args = parser.parse_args()
    data = args.xex.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("Not the inspected EFLC executable")
    image, info = decode_xex(data)
    mappings = {int(x, 16) for x in re.findall(r"\{ 0x([0-9A-Fa-f]+),", (args.generated / "eflc_init.cpp").read_text())}
    count = check(image, mappings, required_callbacks=CALLBACK_TARGETS)
    print(f"PASS: all {count} unique CRT initializer targets and {len(CALLBACK_TARGETS)} verified allocator callback are registered; gameplay remains untested")


if __name__ == "__main__":
    main()

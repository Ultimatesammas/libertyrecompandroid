#!/usr/bin/env python3
"""Inspect a user-supplied EFLC XEX; never install it or bypass runtime validation.

Requires cryptography for encrypted images. Keys are read from the existing BSD
SDK loader rather than copied into reports. Basic-compressed XEX only.
"""
import argparse
import hashlib
import json
import pathlib
import re
import struct
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]


def bounded(data, offset, length):
    if offset < 0 or length < 0 or offset > len(data) or length > len(data) - offset:
        raise ValueError("Structure outside file bounds")
    return data[offset:offset + length]


def u32(data, offset, endian=">"):
    return struct.unpack(endian + "I", bounded(data, offset, 4))[0]


def decode_xex(data, sdk=ROOT / "glue/rexglue-sdk-main"):
    if len(data) > 64 * 1024 * 1024 or bounded(data, 0, 4) != b"XEX2":
        raise ValueError("Not a bounded XEX2 file")
    header_size, security, count = u32(data, 8), u32(data, 16), u32(data, 20)
    if header_size < 24 or header_size > len(data) or count > 4096 or 24 + count * 8 > header_size:
        raise ValueError("Invalid optional-header table")
    if security < 24 + count * 8 or security + 0x184 > header_size:
        raise ValueError("Invalid security header")
    headers = {}
    for index in range(count):
        key, value = struct.unpack(">II", bounded(data, 24 + index * 8, 8))
        if key in headers:
            raise ValueError("Duplicate optional header")
        headers[key] = value
    at = headers.get(0x3FF)
    if at is None or at < 24 + count * 8:
        raise ValueError("Missing file format information")
    size, encryption, compression = struct.unpack(">IHH", bounded(data[:header_size], at, 8))
    if size < 8 or (size - 8) % 8 or at + size > header_size:
        raise ValueError("Invalid basic-compression blocks")
    if compression != 1 or encryption not in (0, 1):
        raise ValueError("This audit supports basic-compressed retail XEX only")
    blocks = [struct.unpack(">II", bounded(data, at + 8 + i * 8, 8))
              for i in range((size - 8) // 8)]
    if not blocks or len(blocks) > 4096:
        raise ValueError("Invalid block count")
    total = sum(a + b for a, b in blocks)
    if total > 128 * 1024 * 1024 or total > u32(data, security + 4):
        raise ValueError("Decoded image exceeds security size or audit limit")
    decryptor = None
    if encryption:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        source = (sdk / "src/system/xex_module.cpp").read_text()
        match = re.search(r"xe_xex2_retail_key\[16\]\s*=\s*\{([^}]+)\}", source)
        if not match:
            raise ValueError("SDK retail loader key not found")
        key = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", match[1]))
        if len(key) != 16:
            raise ValueError("Invalid SDK key length")
        d = Cipher(algorithms.AES(key), modes.CBC(bytes(16))).decryptor()
        session = d.update(bounded(data, security + 0x150, 16)) + d.finalize()
        decryptor = Cipher(algorithms.AES(session), modes.CBC(bytes(16))).decryptor()
    image, cursor = bytearray(), header_size
    for length, zeros in blocks:
        raw = bounded(data, cursor, length)
        if encryption and length % 16:
            raise ValueError("Encrypted block is not AES-aligned")
        image.extend(decryptor.update(raw) if decryptor else raw)
        image.extend(bytes(zeros))
        cursor += length
    if decryptor:
        decryptor.finalize()
    if bounded(image, 0, 2) != b"MZ":
        raise ValueError("Decoded image is not PE")
    pe = u32(image, 60, "<")
    if bounded(image, pe, 4) != b"PE\0\0":
        raise ValueError("Invalid PE signature")
    machine, sections = struct.unpack("<HH", bounded(image, pe + 4, 4))
    optional_size = struct.unpack("<H", bounded(image, pe + 20, 2))[0]
    optional = pe + 24
    if machine != 0x1F2 or not 1 <= sections <= 96 or optional_size < 96:
        raise ValueError("Unexpected Xbox 360 PE format")
    bounded(image, optional, optional_size)
    if struct.unpack("<H", bounded(image, optional, 2))[0] != 0x10B:
        raise ValueError("Not PE32")
    base = u32(image, optional + 28, "<")
    if base != u32(data, security + 0x110):
        raise ValueError("PE and XEX image bases disagree")
    info = {"sha256": hashlib.sha256(data).hexdigest(), "xex_bytes": len(data),
            "image_base": f"0x{base:08X}", "image_size": u32(data, security + 4),
            "decoded_size": len(image), "entrypoint": f"0x{base + u32(image, optional + 16, '<'):08X}",
            "region": f"0x{u32(data, security + 0x178):08X}", "sections": []}
    for i in range(sections):
        record = bounded(image, optional + optional_size + i * 40, 40)
        name = record[:8].rstrip(b"\0").decode("ascii")
        length, rva = struct.unpack_from("<II", record, 8)
        flags = struct.unpack_from("<I", record, 36)[0]
        if rva + length > info["image_size"]:
            raise ValueError("Section exceeds declared memory image")
        info["sections"].append({"name": name, "address": f"0x{base + rva:08X}",
                                 "size": length, "executable": bool(flags & 0x20000000)})
    executable = [s for s in info["sections"] if s["executable"]]
    if not executable:
        raise ValueError("No executable sections")
    info["code_base"] = min(int(s["address"], 16) for s in executable)
    info["code_end"] = max(int(s["address"], 16) + s["size"] for s in executable)
    return bytes(image), info


def prefixes(directory, wanted=None, length=24):
    """Read disassembly comments from generated code, bounded per function."""
    result, current = {}, None
    for path in sorted(pathlib.Path(directory).glob("*_recomp.*.cpp")):
        for line in path.open():
            match = re.match(r"DEFINE_REX_FUNC\(sub_([0-9A-Fa-f]+)\)", line)
            if match:
                current = int(match[1], 16)
            if current is not None and (wanted is None or current in wanted) and line.startswith("\t// "):
                comments = result.setdefault(current, [])
                if len(comments) < length:
                    comments.append(line.strip()[3:].strip())
    return result


def normalized(instructions):
    # This masks ALL immediates, including semantic constants. It produces
    # research candidates, never validated replacements for hooks or globals.
    return tuple(re.sub(r"\s+", "", re.sub(
        r"(?<![a-zA-Z_])[-+]?(?:0x[0-9a-fA-F]+|\d+)", "#", s.lower()))
        for s in instructions)


def compare_hooks(original, generated):
    title = original.parent / "src"
    wanted = set()
    for path in title.rglob("*.cpp"):
        wanted.update(int(x, 16) for x in re.findall(
            r'extern "C" void sub_([0-9A-Fa-f]{8})', path.read_text()))
    old, new = prefixes(original, wanted), prefixes(generated)
    shapes = defaultdict(list)
    for address, instructions in new.items():
        if len(instructions) == 24:
            shapes[normalized(instructions)].append(address)
    entries = []
    for address in sorted(wanted):
        instructions = old.get(address, [])
        candidates = shapes.get(normalized(instructions), []) if len(instructions) == 24 else []
        entries.append({"original": f"0x{address:08X}",
                        "prefix_same_at_original_address": bool(instructions and instructions == new.get(address)),
                        "candidates": [f"0x{x:08X}" for x in candidates],
                        "validated": False})
    return {"method": "24-instruction prefix with all immediates masked; candidates only",
            "hook_count": len(wanted), "generated_functions": len(new),
            "unique_candidates": sum(len(x["candidates"]) == 1 for x in entries),
            "ambiguous_candidates": sum(len(x["candidates"]) > 1 for x in entries),
            "no_candidates": sum(not x["candidates"] for x in entries), "hooks": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xex", type=pathlib.Path)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--generated", type=pathlib.Path)
    args = parser.parse_args()
    _, info = decode_xex(args.xex.read_bytes())
    if args.generated:
        info["hook_comparison"] = compare_hooks(ROOT / "glue/rexglue-sdk-main/gta4-recomp/generated", args.generated)
    args.report.write_text(json.dumps({"compatibility": "unverified", **info}, indent=2) + "\n")
    print(f"Report written: {args.report}")


if __name__ == "__main__":
    main()

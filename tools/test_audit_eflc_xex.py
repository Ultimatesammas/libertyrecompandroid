import pathlib
import re
import struct
import unittest

from audit_eflc_xex import ROOT, decode_xex


def fixture(encrypted=False):
    image = bytearray(1024)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 60, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", image, 0x84, 0x1F2, 1)
    struct.pack_into("<H", image, 0x94, 96)
    struct.pack_into("<H", image, 0x98, 0x10B)
    struct.pack_into("<I", image, 0xA8, 0x200)
    struct.pack_into("<I", image, 0xB4, 0x82000000)
    image[0xF8:0xFD] = b".text"
    struct.pack_into("<II", image, 0x100, 128, 0x200)
    struct.pack_into("<I", image, 0x11C, 0x60000020)
    image[512:] = bytes(i % 256 for i in range(512))
    header = bytearray(1024)
    header[:4] = b"XEX2"
    struct.pack_into(">II", header, 8, 1024, 0)
    struct.pack_into(">II", header, 16, 0x40, 1)
    struct.pack_into(">II", header, 24, 0x3FF, 0x300)
    struct.pack_into(">I", header, 0x44, 4096)
    struct.pack_into(">I", header, 0x150, 0x82000000)
    struct.pack_into(">IHHIIII", header, 0x300, 24, int(encrypted), 1, 512, 0, 512, 0)
    if encrypted:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        source = (ROOT / "glue/rexglue-sdk-main/src/system/xex_module.cpp").read_text()
        match = re.search(r"xe_xex2_retail_key\[16\]\s*=\s*\{([^}]+)\}", source)
        key = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", match[1]))
        session = bytes(range(16))
        e = Cipher(algorithms.AES(key), modes.CBC(bytes(16))).encryptor()
        header[0x190:0x1A0] = e.update(session) + e.finalize()
        e = Cipher(algorithms.AES(session), modes.CBC(bytes(16))).encryptor()
        payload = e.update(image) + e.finalize()
    else:
        payload = image
    return bytearray(header + payload), bytes(image)


class DecodeTests(unittest.TestCase):
    def test_plain_and_chained_encrypted_blocks(self):
        for encrypted in (False, True):
            data, expected = fixture(encrypted)
            image, info = decode_xex(data)
            self.assertEqual(image, expected)
            self.assertEqual(info["entrypoint"], "0x82000200")
            self.assertEqual(info["code_base"], 0x82000200)
            self.assertEqual(info["code_end"], 0x82000280)

    def test_truncated_encrypted_payload(self):
        data, _ = fixture(True)
        with self.assertRaisesRegex(ValueError, "bounds"):
            decode_xex(data[:-16])

    def test_security_size_limit(self):
        data, _ = fixture()
        struct.pack_into(">I", data, 0x44, 512)
        with self.assertRaisesRegex(ValueError, "security size"):
            decode_xex(data)

    def test_duplicate_format_header(self):
        data, _ = fixture()
        struct.pack_into(">I", data, 20, 2)
        struct.pack_into(">II", data, 32, 0x3FF, 0x300)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            decode_xex(data)

    def test_wrong_pe_base(self):
        data, _ = fixture()
        struct.pack_into("<I", data, 1024 + 0xB4, 0x83000000)
        with self.assertRaisesRegex(ValueError, "bases disagree"):
            decode_xex(data)

    def test_out_of_bounds_section(self):
        data, _ = fixture()
        struct.pack_into("<I", data, 1024 + 0x100, 10000)
        with self.assertRaisesRegex(ValueError, "Section exceeds"):
            decode_xex(data)

    def test_unsupported_compression(self):
        data, _ = fixture()
        struct.pack_into(">H", data, 0x306, 2)
        with self.assertRaisesRegex(ValueError, "basic-compressed"):
            decode_xex(data)


if __name__ == "__main__":
    unittest.main()

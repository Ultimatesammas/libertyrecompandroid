import struct
import unittest
from check_eflc_startup import check


class StartupChecks(unittest.TestCase):
    def run_check(self, words, mappings):
        image = struct.pack(">" + "I" * len(words), *words)
        return check(image, mappings, base=0, ranges=((0, len(image)),), code_begin=0x100, code_end=0x200)

    def test_null_sentinel_and_duplicate_targets(self):
        self.assertEqual(self.run_check([0, 0x100, 0xFFFFFFFF, 0x100, 0x104], {0x100, 0x104}), 2)

    def test_missing_indirect_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "00000104"):
            self.run_check([0x100, 0x104], {0x100})

    def test_invalid_pointer_and_range_are_rejected(self):
        for target in [0x101, 0x200]:
            with self.assertRaisesRegex(ValueError, "Invalid initializer"):
                self.run_check([target], {target})
        with self.assertRaisesRegex(ValueError, "outside decoded image"):
            check(b"", set(), base=0, ranges=((0, 4),))


if __name__ == "__main__":
    unittest.main()

import re
import unittest
from build_eflc_native_local import split_registration


class RegistrationBuildChecks(unittest.TestCase):
    def test_batching_preserves_every_call_and_order(self):
        calls = [f"registrar->SetFunction(0x{x:08X}, function_{x});" for x in range(1024, 1031)]
        source = '#include "eflc_init.h"\nvoid eflc_RegisterFunctions(rex::runtime::IModuleRegistrar* registrar) {\n' + '\n'.join(calls) + '\n}\n'
        result = split_registration(source, 3)
        self.assertEqual(re.findall(r"registrar->SetFunction\([^;]+;", result), calls)
        self.assertEqual(result.count("static void eflc_generated_registration_chunk_"), 3)
        self.assertIn("eflc_generated_registration_chunk_2(registrar);", result)

    def test_unrecognized_body_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported statements"):
            split_registration("void eflc_RegisterFunctions(rex::runtime::IModuleRegistrar* registrar) { other_action(); }")

    def test_invalid_batch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "batch size"):
            split_registration("", 0)


if __name__ == "__main__":
    unittest.main()

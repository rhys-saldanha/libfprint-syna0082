import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "container_map", ROOT / "tools" / "syna0082_container_map.py"
)
container_map = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = container_map
SPEC.loader.exec_module(container_map)


class FakeReader:
    def __init__(self, data):
        self.data = data

    def read_rva(self, rva, length):
        return self.data[rva:rva + length]


class ContainerMapTests(unittest.TestCase):
    def test_reports_maximal_cross_descriptor_run(self):
        shared = bytes(range(32))
        prefix = b"P" * container_map.PROTECTED_PREFIX_SIZE
        payloads = [
            b"\x02\x00\x00\x01" + prefix + b"A" * 16 + shared + b"B" * 16,
            b"\x02\x00\x00\x01" + prefix + b"C" * 16 + shared + b"D" * 16,
        ]
        result = container_map.summarize_containers(payloads)
        self.assertEqual(result["headers"], {"02000001": 2})
        self.assertEqual(result["observed_layout"]["protected_body_offset"], 260)
        self.assertEqual(result["post_prefix_body_block_count"], 8)
        run = result["cross_descriptor_runs_at_least_two_blocks"][-1]
        self.assertEqual(run["payload_offset"], 276)
        self.assertEqual(run["length"], 32)
        self.assertEqual(run["sha256"], hashlib.sha256(shared).hexdigest())

    def test_classifies_p256_coordinate_slots(self):
        x = bytes(range(1, 33))
        y = bytes(range(33, 65))
        key = x + bytes(36) + y + bytes(156)
        layout, digest = container_map.classify_security_key(key)
        self.assertEqual(layout, "p256_xy_in_68_byte_slots")
        self.assertEqual(digest, hashlib.sha256(x + y).hexdigest())

    def test_parses_hash_only_security_key_record(self):
        key = bytes([1]) * 256
        raw = b"\x06\x14\x01" + key + bytes(container_map.SECURITY_KEY_RECORD_SIZE)
        records = container_map.parse_security_key_catalog(FakeReader(raw), 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["selector"], "061401")
        self.assertEqual(records[0]["layout"], "opaque_256_byte_integer")
        self.assertNotIn("key", records[0])

    def test_recognizes_only_complete_pkcs1_type_1_padding(self):
        valid = b"\x00\x01" + b"\xff" * 8 + b"\x00digest-info"
        self.assertTrue(container_map.has_pkcs1_v1_5_type_1_padding(valid))
        self.assertFalse(container_map.has_pkcs1_v1_5_type_1_padding(
            b"\x00\x01" + b"\xff" * 7 + b"\x00digest-info"
        ))
        self.assertFalse(container_map.has_pkcs1_v1_5_type_1_padding(
            b"\x00\x01" + b"\xff" * 8 + b"digest-info"
        ))

    def test_rsa_prefix_check_reports_no_match_for_synthetic_values(self):
        payload = (b"\x02\x00\x00\x01" + bytes(256) + b"B" * 16)
        result = container_map.rsa_prefix_check([payload], [bytes([0xff]) * 256])
        self.assertEqual(result["interpretation_count"], 12)
        self.assertEqual(result["strict_type_1_padding_matches"], [])


if __name__ == "__main__":
    unittest.main()

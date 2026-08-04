import hashlib
import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "descriptor_catalog", ROOT / "tools" / "syna0082_descriptor_catalog.py"
)
catalog = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = catalog
SPEC.loader.exec_module(catalog)


class FakeReader:
    image_base = 0x180000000

    def __init__(self, values):
        self.values = values

    def read_rva(self, rva, length):
        return self.values[(rva, length)]

    def pointer_to_rva(self, pointer):
        return pointer - self.image_base


class DescriptorCatalogTests(unittest.TestCase):
    def make_record(self, payload_rva=0x3000, payload=b"table"):
        record = bytearray(catalog.DESCRIPTOR_SIZE)
        for position, offset in enumerate(catalog.SELECTOR_OFFSETS):
            struct.pack_into("<I", record, offset, position + 1)
        struct.pack_into("<I", record, catalog.LENGTH_OFFSET, len(payload))
        struct.pack_into("<Q", record, catalog.PAYLOAD_POINTER_OFFSET, 0x180000000 + payload_rva)
        return bytes(record)

    def test_parses_fixed_descriptor_layout(self):
        payload = b"static sensor program"
        record = self.make_record(payload=payload)
        reader = FakeReader({(0x3000, len(payload)): payload})
        result = catalog.parse_descriptor(39, 0x2000, record, reader)
        self.assertEqual(result.index, 39)
        self.assertEqual(result.selectors, tuple(range(1, 14)))
        self.assertEqual(result.payload_length, len(payload))
        self.assertEqual(result.payload_sha256, hashlib.sha256(payload).hexdigest())

    def test_catalog_uses_pointer_entries_until_null(self):
        payload = b"table"
        record = self.make_record(payload=payload)
        reader = FakeReader({
            (0x1000, 8): struct.pack("<Q", 0x180002000),
            (0x1008, 8): bytes(8),
            (0x2000, catalog.DESCRIPTOR_SIZE): record,
            (0x3000, len(payload)): payload,
        })
        results = catalog.parse_catalog(reader, 0x1000)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].rva, 0x2000)

    def test_rejects_nonzero_reserved_prefix(self):
        record = bytearray(self.make_record())
        record[0] = 1
        reader = FakeReader({(0x3000, 5): b"table"})
        with self.assertRaisesRegex(ValueError, "reserved prefix"):
            catalog.parse_descriptor(0, 0x2000, bytes(record), reader)


if __name__ == "__main__":
    unittest.main()

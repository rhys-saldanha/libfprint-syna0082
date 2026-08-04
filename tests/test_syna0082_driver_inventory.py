import importlib.util
import subprocess
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("driver_inventory", ROOT / "tools" / "syna0082_driver_inventory.py")
inventory = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(inventory)


class DriverInventoryTests(unittest.TestCase):
    def test_extracts_ascii_and_utf16_strings(self):
        data = b"xxCalibrationDataxx\x00" + "UpdateFirmwareFailureCount".encode("utf-16le")
        values = inventory.strings(data)
        self.assertIn("xxCalibrationDataxx", values)
        self.assertIn("UpdateFirmwareFailureCount", values)

    def test_capability_patterns_do_not_overmatch(self):
        self.assertIsNotNone(inventory.CATEGORIES["cryptoapi"].match("CryptGenRandom"))
        self.assertIsNone(inventory.CATEGORIES["cryptoapi"].match("CryptMadeUpFunction"))

    @mock.patch.object(inventory.shutil, "which", return_value="llvm-readobj")
    @mock.patch.object(inventory.subprocess, "run")
    def test_parses_llvm_readobj_symbol_with_ordinal(self, run, _which):
        run.return_value = subprocess.CompletedProcess([], 0, "  Symbol: CryptGenRandom (42)\n", "")
        self.assertIn("CryptGenRandom", inventory.imported_symbols(Path("driver.dll")))

    def test_maps_embedded_payload_suffix(self):
        result = inventory.payload_provenance(b"\x06STATIC-TABLE", b"prefixSTATIC-TABLEsuffix")
        self.assertEqual(result["embedded_suffix"], {
            "payload_offset": 1, "binary_offset": 6, "length": 12,
        })

    @mock.patch.object(inventory, "imported_symbols", return_value={"CryptGenRandom"})
    @mock.patch.object(Path, "read_bytes", return_value=b"CalibrationData")
    def test_inventory_returns_hash_only_result(self, _read, _imports):
        result = inventory.inventory(Path("driver.dll"))
        self.assertEqual(result["file"], "driver.dll")
        self.assertIn("CryptGenRandom", result["capabilities"]["cryptoapi"])
        self.assertIn("CalibrationData", result["keyword_evidence"])


if __name__ == "__main__":
    unittest.main()

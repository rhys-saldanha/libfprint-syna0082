import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "syna0082_provision", TOOLS / "syna0082_provision.py"
)
provision = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(provision)


def record(payload: bytes) -> str:
    return json.dumps(
        {"usb.endpoint_address": "0x01", "usb.capdata": payload.hex()}
    ) + "\n"


class FakeCatalogReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read_rva(self, rva: int, length: int) -> bytes:
        if rva != 0x3000 or length != len(self.payload):
            raise AssertionError((rva, length))
        return self.payload


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.capture = self.root / "capture.jsonl"
        self.config = provision.CONFIG_PREFIX + bytes(
            provision.CONFIG_MESSAGE_LENGTH - len(provision.CONFIG_PREFIX)
        )
        matrix = bytearray(provision.MATRIX_LENGTH)
        matrix[: len(provision.MATRIX_PREFIX)] = provision.MATRIX_PREFIX
        matrix[provision.MODE_OFFSET] = provision.ACQUISITION_MODE
        self.matrix = bytes(matrix)
        self.capture.write_text(
            record(self.config) + record(self.matrix), encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_capture_only_provisions_required_files(self):
        output = self.root / "private"
        manifest = provision.provision(self.capture, output)
        self.assertEqual((output / provision.CONFIG_NAME).read_bytes(), self.config)
        self.assertEqual((output / provision.MATRIX_NAME).read_bytes(), self.matrix)
        self.assertEqual(manifest["config_source"]["kind"], "normalized-capture")
        self.assertNotIn(str(self.capture), json.dumps(manifest))
        self.assertEqual(
            {item["name"] for item in manifest["files"]},
            {provision.CONFIG_NAME, provision.MATRIX_NAME},
        )

    def test_refuses_output_inside_git_worktree(self):
        worktree = self.root / "repo"
        (worktree / ".git").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "inside Git worktree"):
            provision.provision(self.capture, worktree / "private")

    def test_refuses_non_acquisition_scan_matrix(self):
        matrix = bytearray(self.matrix)
        matrix[provision.MODE_OFFSET] = 0x23
        self.capture.write_text(record(self.config) + record(matrix), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "scan matrix"):
            provision.provision(self.capture, self.root / "private")

    def test_builds_command_from_expected_descriptor(self):
        payload = bytes.fromhex("02000001") + bytes(
            provision.CONFIG_PAYLOAD_LENGTH - 4
        )
        descriptor = SimpleNamespace(
            payload_length=len(payload),
            container_header="02000001",
            body_multiple_of_16=True,
            payload_rva=0x3000,
        )
        original = provision.catalog.parse_catalog
        provision.catalog.parse_catalog = lambda reader, rva: [None] * 39 + [descriptor]
        try:
            result = provision.config_from_reader(FakeCatalogReader(payload), 0x1000)
        finally:
            provision.catalog.parse_catalog = original
        self.assertEqual(result, b"\x06" + payload)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("syna0082_protocol", ROOT / "tools" / "syna0082_protocol.py")
protocol = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(protocol)


def record(frame, endpoint, payload, transfer="0x03", request=""):
    return {
        "frame.number": str(frame), "frame.time_relative": "0", "usb.endpoint_address": endpoint,
        "usb.transfer_type": transfer, "usb.setup.bRequest": request, "usb.capdata": payload.hex(),
    }


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.capture = Path(self.directory.name) / "capture.jsonl"

    def tearDown(self):
        self.directory.cleanup()

    def write(self, records):
        self.capture.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")

    def test_transaction_pairing_and_decode_redacts_payload(self):
        self.write([record(1, "0x01", b"\x01"), record(2, "0x81", bytes(38)), record(3, "0x83", b"\x03\x42\x04\x00\x40", "0x01")])
        result = protocol.decoded(self.capture)
        command = result["transactions"][0]
        self.assertEqual(command["opcode"], "01")
        self.assertEqual(command["responses"][0]["length"], 38)
        self.assertNotIn("payload", command)

    def test_validation_finds_bad_command_length(self):
        self.write([record(1, "0x01", b"\x51\x00")])
        result = protocol.validate_capture(self.capture, protocol.load_schema())
        self.assertFalse(result["valid"])
        self.assertIn("length 2", result["errors"][0])

    def test_dash_reads_json_lines_from_stdin(self):
        old_stdin = protocol.sys.stdin
        protocol.sys.stdin = StringIO(json.dumps(record(1, "0x01", b"\x01")) + "\n")
        try:
            records = protocol.read_capture(Path("-"))
        finally:
            protocol.sys.stdin = old_stdin
        self.assertEqual(records[0]["payload"], b"\x01")

    def test_diff_reports_scan_mode_offset(self):
        first = bytearray(18869); first[0] = 2; first[1749] = 2
        second = bytearray(first); second[1749] = 0x23
        other = Path(self.directory.name) / "other.jsonl"
        self.write([record(1, "0x01", first)])
        other.write_text(json.dumps(record(1, "0x01", second)) + "\n", encoding="utf-8")
        group = protocol.diff_captures([self.capture, other])["groups"][0]
        self.assertEqual(group["differing_offsets"], [1749])

    def test_generators_have_expected_shape(self):
        self.assertEqual(protocol.generate("51"), bytes.fromhex("5100200000"))
        config = protocol.generate("39")
        self.assertEqual(len(config), 125)
        self.assertEqual(config[:4], bytes.fromhex("3920bf02"))

    def test_opaque_commands_are_not_generated(self):
        with self.assertRaises(ValueError):
            protocol.generate("06")


if __name__ == "__main__":
    unittest.main()

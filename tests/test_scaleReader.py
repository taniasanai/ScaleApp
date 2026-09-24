import json
import socket
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

from scaleReader import LineParser, Reading, ScaleReader, WeighingDetector

DEFAULT_PARSER = LineParser("ST", r"[+-]?\d+(?:\.\d+)?")


class LineParserTest(unittest.TestCase):
    def test_reads_simulator_formats(self):
        self.assertEqual(DEFAULT_PARSER.parse("ST,GS,+00012.50kg"), Reading(12.5, True))
        self.assertEqual(DEFAULT_PARSER.parse("US,GS,+00012.50kg"), Reading(12.5, False))
        self.assertEqual(DEFAULT_PARSER.parse("-3.20 kg ST"), Reading(-3.2, True))

    def test_line_without_weight_is_ignored(self):
        self.assertIsNone(DEFAULT_PARSER.parse("ST,GS,kg"))

    def test_weight_group_is_used_when_present(self):
        parser = LineParser("ST", r"W=(\d+\.\d+)")
        self.assertEqual(parser.parse("ID01 ST W=7.25"), Reading(7.25, True))


class ManualFormatsTest(unittest.TestCase):
    """The parsing in config.json against the example lines in the Weightech manuals."""

    @classmethod
    def setUpClass(cls):
        config = json.loads((Path(__file__).parent.parent / "config.json").read_text())
        scales = {s["name"]: {**config["parsing"], **s.get("parsing", {})}
                  for s in config["scales"]}
        cls.parsers = {name: LineParser(p["stable_pattern"], p["weight_pattern"])
                       for name, p in scales.items()}

    def test_wt1000_full_mode_reads_the_net_weight(self):
        parse = self.parsers["WT1000"].parse
        # Manual section 6.1: gross 10 kg, tare 0.2 kg, net 9.8 kg (flag 1 = unstable).
        self.assertEqual(parse("1,010.000,000.200,009.800"), Reading(9.8, False))
        self.assertEqual(parse("0,010.000,000.200,009.800"), Reading(9.8, True))
        self.assertEqual(parse("0,000.000,000.200,-00.200"), Reading(-0.2, True))

    def test_wt1000_overload_is_ignored(self):
        self.assertIsNone(self.parsers["WT1000"].parse("0,    ol,    ol,    ol"))
        self.assertIsNone(self.parsers["WT1000"].parse("0,-   ol,-   ol,-   ol"))

    def test_wt3000i_full_format(self):
        parse = self.parsers["WT3000i"].parse
        # Manual section 3.2.1.
        self.assertEqual(parse("ST,GS,+0012.345  kg"), Reading(12.345, True))
        self.assertEqual(parse("ST,NT,+0012.345  kg"), Reading(12.345, True))
        self.assertEqual(parse("US,GS,+01234.56  kg"), Reading(1234.56, False))
        self.assertEqual(parse("ST,GS,+123456kg"), Reading(123456.0, True))

    def test_wt3000i_overload_is_ignored(self):
        self.assertIsNone(self.parsers["WT3000i"].parse("OL,GS,+            "))


class WeighingDetectorTest(unittest.TestCase):
    def feed_all(self, readings):
        detector = WeighingDetector(zero_threshold=0.5)
        records = []
        for i, (weight, stable) in enumerate(readings):
            result = detector.feed(Reading(weight, stable), i)
            if result:
                records.append(result)
        return records, detector

    def test_one_record_per_load(self):
        records, _ = self.feed_all([(0, True), (10, False), (12, True), (12, True),
                                    (12, True), (5, False), (0, True), (0, True)])
        self.assertEqual(records, [(12, 2)])

    def test_items_added_on_top_give_the_total(self):
        records, _ = self.feed_all([(12, True), (20, False), (25, True), (0, True)])
        self.assertEqual(records, [(25, 2)])

    def test_items_removed_one_by_one_give_the_total(self):
        records, _ = self.feed_all([(25, True), (12, True), (0.2, True)])
        self.assertEqual(records, [(25, 0)])

    def test_unstable_zero_does_not_end_the_load(self):
        records, detector = self.feed_all([(12, True), (0, False)])
        self.assertEqual(records, [])
        self.assertEqual(detector.flush(), (12, 0))

    def test_negative_reading_ends_the_load(self):
        records, _ = self.feed_all([(12, True), (-0.4, True)])
        self.assertEqual(records, [(12, 0)])


class WeighingDetectorRestartTest(unittest.TestCase):
    PLACED = datetime(2026, 9, 24, 9, 0, 0)
    LATER = datetime(2026, 9, 24, 9, 5, 0)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "state" / "WT1000.json"
        before_restart = WeighingDetector(0.5, self.state_file)
        before_restart.feed(Reading(40.0, True), self.PLACED)
        self.after_restart = WeighingDetector(0.5, self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_still_on_the_scale_is_recorded_once(self):
        self.assertIsNone(self.after_restart.feed(Reading(40.0, True), self.LATER))
        self.assertEqual(self.after_restart.feed(Reading(0.0, True), self.LATER),
                         (40.0, self.PLACED))
        self.assertFalse(self.state_file.exists())

    def test_load_removed_while_closed_is_recorded_with_its_original_time(self):
        self.assertEqual(self.after_restart.feed(Reading(0.0, True), self.LATER),
                         (40.0, self.PLACED))

    def test_unreadable_state_file_is_ignored(self):
        self.state_file.write_text("not json")
        self.assertIsNone(WeighingDetector(0.5, self.state_file).peak)


class ScaleReaderTest(unittest.TestCase):
    def test_handles_split_lines_and_reconnects(self):
        server = socket.create_server(("127.0.0.1", 0))
        port = server.getsockname()[1]
        chunks_per_connection = [
            [b"ST,+0.00\r\nUS,+9.0", b"0\r\nST,+1", b"2.50\r\nST,+12.50\r\n", b"ST,+0.00\r\n"],
            [b"ST,+3.00\r\nST,+0.00\r\n"],
        ]

        def fake_scale():
            for chunks in chunks_per_connection:
                conn, _ = server.accept()
                with conn:
                    for chunk in chunks:
                        conn.sendall(chunk)
                        time.sleep(0.05)
            server.close()

        threading.Thread(target=fake_scale, daemon=True).start()
        records = []
        reader = ScaleReader("Test", "127.0.0.1", port, DEFAULT_PARSER,
                             WeighingDetector(0.5), lambda *r: records.append(r))
        reader.start()
        deadline = time.time() + 10
        while len(records) < 2 and time.time() < deadline:
            time.sleep(0.05)
        reader.stop()
        reader.join(timeout=5)

        self.assertEqual([(name, weight) for name, weight, _ in records],
                         [("Test", 12.5), ("Test", 3.0)])
        self.assertIsInstance(records[0][2], datetime)


if __name__ == "__main__":
    unittest.main()

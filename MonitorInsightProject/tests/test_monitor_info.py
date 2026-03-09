import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monitor_info import (
    collect_monitor_snapshots,
    diagonal_inches_from_mm,
    ensure_application,
    input_source_label,
    orientation_from_size,
    parse_supported_input_source_codes,
    snapshots_payload,
)


class MonitorInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = ensure_application()
        cls.app.setQuitOnLastWindowClosed(False)

    def test_orientation_from_size(self) -> None:
        self.assertEqual(orientation_from_size(1920, 1080), "横向")
        self.assertEqual(orientation_from_size(1080, 1920), "纵向")
        self.assertEqual(orientation_from_size(1200, 1200), "方形")
        self.assertEqual(orientation_from_size(0, 1200), "未知")

    def test_diagonal_inches_from_mm(self) -> None:
        self.assertAlmostEqual(diagonal_inches_from_mm(596.0, 336.0), 26.94, places=2)
        self.assertEqual(diagonal_inches_from_mm(0.0, 300.0), 0.0)

    def test_input_source_helpers(self) -> None:
        caps = "(prot(monitor)type(lcd)vcp(60( 11 12 0F) 62))"
        self.assertEqual(parse_supported_input_source_codes(caps), (0x11, 0x12, 0x0F))
        self.assertEqual(input_source_label(0x11), "HDMI 1")
        self.assertEqual(input_source_label(0x0F), "DisplayPort 1")
        self.assertEqual(input_source_label(0x99), "输入源 0x99")

    def test_collect_monitor_snapshots_returns_structured_data(self) -> None:
        snapshots = collect_monitor_snapshots(self.app)
        self.assertGreaterEqual(len(snapshots), 1)

        first = snapshots[0]
        self.assertGreater(first.desktop_resolution[0], 0)
        self.assertGreater(first.desktop_resolution[1], 0)
        self.assertGreater(first.scale_percent, 0)
        self.assertIsInstance(first.display_title, str)
        self.assertIsInstance(first.current_input_source_label, str)
        self.assertIsInstance(first.supported_input_sources, tuple)

    def test_snapshots_payload_matches_snapshot_count(self) -> None:
        snapshots = collect_monitor_snapshots(self.app)
        payload = snapshots_payload(snapshots)
        self.assertEqual(payload["monitor_count"], len(snapshots))
        self.assertEqual(len(payload["monitors"]), len(snapshots))
        self.assertIn("current_input_source", payload["monitors"][0])
        self.assertIn("supported_input_sources", payload["monitors"][0])
        self.assertIn("input_switch_supported", payload["monitors"][0])


if __name__ == "__main__":
    unittest.main()

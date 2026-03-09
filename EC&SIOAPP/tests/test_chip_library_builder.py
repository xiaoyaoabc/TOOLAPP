import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chip_library_builder import (
    AMD_57396_PDF,
    ASM1061_PDF,
    BQ25720_PDF,
    CT7432_PDF,
    CW2217_PDF,
    IT5570_PDF,
    IT8613_PDF,
    IT8625_PDF,
    IT8728_PDF,
    IT8772_PDF,
    IT8786_PDF,
    MS8510_PDF,
    build_amd_57396_chip,
    build_asm1061_chip,
    build_bq25720_chip,
    build_ct7432_chip,
    build_cw2217_chip,
    build_it5570_chip,
    build_it8613_chip,
    build_it8625_chip,
    build_it8728_chip,
    build_it8772_chip,
    build_it8786_chip,
    build_ms8510_chip,
    parse_it5570_top_view,
    parse_ms8510_top_view,
)


class ChipLibraryBuilderTests(unittest.TestCase):
    def _assert_generic_ite_chip(
        self,
        chip: dict,
        *,
        chip_id: str,
        pin_count: int,
        signal_name: str,
        module_id: str = "gpio",
    ) -> None:
        self.assertEqual(chip["chip_id"], chip_id)
        self.assertEqual(chip["pin_count"], pin_count)
        self.assertEqual(chip["category"], "Super I/O / HWM")
        self.assertTrue(any(module["id"] == module_id for module in chip["modules"]))
        self.assertTrue(any(signal["signal"] == signal_name for signal in chip["signals"]))
        self.assertGreaterEqual(len(chip["features"]), 3)

    def test_parse_top_view_has_128_pins(self) -> None:
        pins = parse_it5570_top_view(IT5570_PDF)
        self.assertEqual(len(pins), 128)
        self.assertEqual(sorted(pin["pin_number"] for pin in pins), list(range(1, 129)))

    def test_top_view_has_32_pins_per_side(self) -> None:
        pins = parse_it5570_top_view(IT5570_PDF)
        side_counts = {}
        for pin in pins:
            side_counts[pin["side"]] = side_counts.get(pin["side"], 0) + 1
        self.assertEqual(side_counts, {"left": 32, "bottom": 32, "right": 32, "top": 32})

    def test_it5570_chip_metadata_is_available(self) -> None:
        chip = build_it5570_chip(IT5570_PDF)
        self.assertEqual(chip["chip_id"], "it5570_c")
        self.assertEqual(chip["category"], "EC / Super I/O")
        self.assertEqual(chip["chip_role"], "Embedded Controller")
        self.assertEqual(chip["pin_count"], 128)
        self.assertGreater(len(chip["signals"]), 200)
        self.assertTrue(any(module["id"] == "gpio" for module in chip["modules"]))
        self.assertGreaterEqual(len(chip["features"]), 3)

    def test_voltage_profile_and_detail_entries_are_enriched(self) -> None:
        chip = build_it5570_chip(IT5570_PDF)

        pin_30 = next(pin for pin in chip["pins"] if pin["pin_number"] == 30)
        self.assertTrue(pin_30["supports_1_8v"])
        self.assertTrue(pin_30["supports_3_3v"])
        self.assertIsNotNone(pin_30["gpio_alt_info"])
        self.assertEqual(pin_30["gpio_alt_info"]["v18"], "Y")
        self.assertGreater(len(pin_30["detail_entries"]), 0)
        self.assertIn("PWM 输出", pin_30["detail_entries"][0]["description_cn"])

        pin_108 = next(pin for pin in chip["pins"] if pin["pin_number"] == 108)
        self.assertFalse(pin_108["supports_1_8v"])
        self.assertTrue(pin_108["supports_3_3v"])
        self.assertEqual(pin_108["gpio_alt_info"]["output"], "(input only)")

        pin_122 = next(pin for pin in chip["pins"] if pin["pin_number"] == 122)
        self.assertTrue(pin_122["supports_1_8v"])
        self.assertTrue(pin_122["supports_3_3v"])
        self.assertEqual(pin_122["gpio_alt_info"]["default_pull"], "Dn")

    def test_amd_chip_metadata_is_available(self) -> None:
        chip = build_amd_57396_chip(AMD_57396_PDF)

        self.assertEqual(chip["chip_id"], "amd_family_19h_model_78h")
        self.assertEqual(chip["category"], "CPU / SoC")
        self.assertEqual(chip["document_type"], "PPR")
        self.assertGreaterEqual(chip["pin_count"], 80)
        self.assertTrue(any(module["id"] == "fan" for module in chip["modules"]))
        self.assertTrue(any(signal["signal"] == "SMBUS1_SCL" for signal in chip["signals"]))
        self.assertGreaterEqual(len(chip["features"]), 3)

    def test_amd_pin_details_are_joined_from_iomux_and_bank_tables(self) -> None:
        chip = build_amd_57396_chip(AMD_57396_PDF)

        fan_pin = next(pin for pin in chip["pins"] if pin.get("pin_ref") == "AGPIO84")
        self.assertIn("FANIN0", fan_pin["aliases"])
        self.assertEqual(fan_pin["generic_info_rows"][0][1], "AGPIO84")
        self.assertIn("Table 153", fan_pin["detail_entries"][0]["table"])

        smbus_pin = next(pin for pin in chip["pins"] if pin.get("pin_ref") == "AGPIO19")
        self.assertIn("SMBUS1_SCL", smbus_pin["aliases"])
        self.assertEqual(smbus_pin["voltage_profile"]["supports_1_8v"], None)

    def test_it8613_chip_metadata_is_available(self) -> None:
        chip = build_it8613_chip(IT8613_PDF)

        self.assertEqual(chip["chip_id"], "it8613_e")
        self.assertEqual(chip["pin_count"], 64)
        self.assertEqual(chip["category"], "Super I/O / HWM")
        self.assertTrue(any(module["id"] == "fan" for module in chip["modules"]))
        self.assertTrue(any(signal["signal"] == "LAD0" for signal in chip["signals"]))

    def test_it8613_pin_details_and_voltage_are_enriched(self) -> None:
        chip = build_it8613_chip(IT8613_PDF)

        serial_pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 63)
        self.assertIn("CTS1#", serial_pin["aliases"])
        self.assertIn("GP31", serial_pin["aliases"])
        self.assertTrue(serial_pin["voltage_profile"]["supports_3_3v"])
        self.assertTrue(serial_pin["voltage_profile"]["supports_5v_tolerant"])
        self.assertGreater(len(serial_pin["detail_entries"]), 0)

        lpc_pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 15)
        self.assertIn("SERIRQ", lpc_pin["aliases"])
        self.assertTrue(lpc_pin["voltage_profile"]["supports_1_8v_input_only"])

        gpio_pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 42)
        self.assertEqual(gpio_pin["generic_info_rows"][0][0], "GPIO 组")
        self.assertTrue(any(row[0].startswith("多功能选择") for row in gpio_pin["generic_info_rows"]))

    def test_it8625_chip_metadata_is_available(self) -> None:
        chip = build_it8625_chip(IT8625_PDF)

        self._assert_generic_ite_chip(chip, chip_id="it8625_l", pin_count=128, signal_name="FAN_CTL4")
        pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 1)
        self.assertIn("3VSB", pin["aliases"])
        self.assertGreater(len(pin["detail_entries"]), 0)

    def test_it8728_chip_metadata_is_available(self) -> None:
        chip = build_it8728_chip(IT8728_PDF)

        self._assert_generic_ite_chip(chip, chip_id="it8728_f", pin_count=128, signal_name="LAD0")
        pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 1)
        self.assertIn("CTS1#", pin["aliases"])
        self.assertIn("GP31", pin["aliases"])

    def test_it8772_chip_metadata_is_available(self) -> None:
        chip = build_it8772_chip(IT8772_PDF)

        self._assert_generic_ite_chip(chip, chip_id="it8772_f", pin_count=64, signal_name="FAN_TAC2")
        pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 1)
        self.assertIn("FAN_TAC2", pin["aliases"])
        self.assertTrue(pin["supports_3_3v"])

    def test_it8786_chip_metadata_is_available(self) -> None:
        chip = build_it8786_chip(IT8786_PDF)

        self._assert_generic_ite_chip(chip, chip_id="it8786_h", pin_count=128, signal_name="FAN_TAC5")
        pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 128)
        self.assertIn("RI6#", pin["aliases"])
        self.assertGreater(len(pin["generic_info_rows"]), 0)

    def test_asm1061_document_chip_is_available(self) -> None:
        chip = build_asm1061_chip(ASM1061_PDF)

        self.assertEqual(chip["chip_id"], "asm1061")
        self.assertEqual(chip["view_type"], "document_only")
        self.assertEqual(chip["pin_count"], 0)
        self.assertGreaterEqual(len(chip["sections"]), 10)
        self.assertGreaterEqual(len(chip["programming_items"]), 10)
        self.assertIn("PCIe to SATA Host Controller", chip["chip_role"])
        self.assertTrue(any("RXEC[2]" in item["registers"] for item in chip["programming_items"]))

    def test_ms8510_top_view_has_128_pins(self) -> None:
        pins = parse_ms8510_top_view(MS8510_PDF)
        self.assertEqual(len(pins), 128)
        self.assertEqual(sorted(pin["pin_number"] for pin in pins), list(range(1, 129)))

    def test_ms8510_chip_metadata_is_available(self) -> None:
        chip = build_ms8510_chip(MS8510_PDF)

        self.assertEqual(chip["chip_id"], "ms8510")
        self.assertEqual(chip["type_label"], "EC芯片")
        self.assertEqual(chip["pin_count"], 128)
        self.assertTrue(any(module["id"] == "gpio" for module in chip["modules"]))
        self.assertTrue(any(signal["signal"] == "LPCCLK" for signal in chip["signals"]))

        lpcck_pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 13)
        self.assertIn("LPCCLK", lpcck_pin["aliases"])
        self.assertTrue(lpcck_pin["supports_1_8v"])
        self.assertTrue(lpcck_pin["supports_3_3v"])
        self.assertGreater(len(lpcck_pin["detail_entries"]), 0)

    def test_bq25720_chip_metadata_is_available(self) -> None:
        chip = build_bq25720_chip(BQ25720_PDF)

        self.assertEqual(chip["chip_id"], "bq25720")
        self.assertEqual(chip["type_label"], "充电IC")
        self.assertEqual(chip["pin_count"], 32)
        self.assertTrue(any(module["id"] == "charger" for module in chip["modules"]))
        self.assertTrue(any(signal["signal"] == "CHRG_OK" for signal in chip["signals"]))

        sda_pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 12)
        self.assertIn("SDA", sda_pin["aliases"])
        self.assertTrue(sda_pin["supports_1_8v"])
        self.assertTrue(sda_pin["supports_3_3v"])
        self.assertGreater(len(sda_pin["detail_entries"]), 0)

    def test_cw2217_chip_metadata_is_available(self) -> None:
        chip = build_cw2217_chip(CW2217_PDF)

        self.assertEqual(chip["chip_id"], "cw2217baad")
        self.assertEqual(chip["type_label"], "电量计")
        self.assertEqual(chip["pin_count"], 12)
        self.assertTrue(any(module["id"] == "battery" for module in chip["modules"]))
        self.assertTrue(any(signal["signal"] == "VCELL" for signal in chip["signals"]))

        vdd_pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 3)
        self.assertEqual(vdd_pin["display_name"], "VDD")
        self.assertFalse(vdd_pin["supports_1_8v"])
        self.assertTrue(vdd_pin["supports_3_3v"])

    def test_ct7432_chip_metadata_is_available(self) -> None:
        chip = build_ct7432_chip(CT7432_PDF)

        self.assertEqual(chip["chip_id"], "ct7432")
        self.assertEqual(chip["type_label"], "温感")
        self.assertEqual(chip["pin_count"], 10)
        self.assertTrue(any(module["id"] == "thermal" for module in chip["modules"]))
        self.assertTrue(any(signal["signal"] == "THERM" for signal in chip["signals"]))

        therm2_pin = next(pin for pin in chip["pins"] if pin["pin_number"] == 8)
        self.assertIn("ALERT", therm2_pin["aliases"])
        self.assertIn("THERM2", therm2_pin["aliases"])
        self.assertGreater(len(therm2_pin["detail_entries"]), 0)


if __name__ == "__main__":
    unittest.main()

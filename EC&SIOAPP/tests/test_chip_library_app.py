import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QMessageBox

from chip_library_app import (
    ChipLibraryWindow,
    ChipSelectionDialog,
    _pump_events,
    clear_user_chip_library,
    ensure_application,
    load_chip_library,
    load_raw_chip_library,
    save_hidden_chip_ids,
)


class ChipLibraryAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.previous_hidden_path = os.environ.get("CHIP_LIBRARY_HIDDEN_PATH")
        cls.previous_deleted_path = os.environ.get("CHIP_LIBRARY_DELETED_PATH")
        cls.previous_user_library_path = os.environ.get("CHIP_LIBRARY_USER_LIBRARY_PATH")
        cls.hidden_path = str(Path(cls.temp_dir.name) / "chip_library_hidden.json")
        cls.user_library_path = str(Path(cls.temp_dir.name) / "chip_library.user.json")
        os.environ["CHIP_LIBRARY_HIDDEN_PATH"] = cls.hidden_path
        os.environ["CHIP_LIBRARY_DELETED_PATH"] = cls.hidden_path
        os.environ["CHIP_LIBRARY_USER_LIBRARY_PATH"] = cls.user_library_path
        cls.app = ensure_application()
        cls.app.setQuitOnLastWindowClosed(False)
        cls.library = load_raw_chip_library()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.previous_hidden_path is None:
            os.environ.pop("CHIP_LIBRARY_HIDDEN_PATH", None)
        else:
            os.environ["CHIP_LIBRARY_HIDDEN_PATH"] = cls.previous_hidden_path
        if cls.previous_deleted_path is None:
            os.environ.pop("CHIP_LIBRARY_DELETED_PATH", None)
        else:
            os.environ["CHIP_LIBRARY_DELETED_PATH"] = cls.previous_deleted_path
        if cls.previous_user_library_path is None:
            os.environ.pop("CHIP_LIBRARY_USER_LIBRARY_PATH", None)
        else:
            os.environ["CHIP_LIBRARY_USER_LIBRARY_PATH"] = cls.previous_user_library_path
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        save_hidden_chip_ids([])
        clear_user_chip_library()

    def tearDown(self) -> None:
        save_hidden_chip_ids([])
        clear_user_chip_library()

    def test_document_only_chip_clears_stale_pin_hit_regions(self) -> None:
        window = ChipLibraryWindow(library=self.library, test_mode=True)
        window.show()
        _pump_events(self.app, 180)

        window.load_chip("it5570_c")
        _pump_events(self.app, 180)
        self.assertGreater(len(window.canvas._pin_hit_regions), 0)

        window.load_chip("asm1061")
        _pump_events(self.app, 180)

        self.assertEqual(window.current_chip["chip_id"], "asm1061")
        self.assertEqual(window.canvas._pin_hit_regions, {})
        self.assertEqual(window.pin_list.count(), 0)

        window._update_hover_status(1)
        window.activate_pin_from_canvas(1)
        _pump_events(self.app, 60)

        window.close()
        _pump_events(self.app, 60)

    def test_chip_selection_dialog_can_hide_and_restore_chip(self) -> None:
        dialog = ChipSelectionDialog(self.library.get("chips", []), [], "asm1061")
        dialog.show()
        _pump_events(self.app, 100)
        dialog._select_chip("asm1061")

        with mock.patch("chip_library_app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            dialog._delete_current_chip()
            _pump_events(self.app, 80)
            self.assertIn("asm1061", dialog.hidden_chip_ids_list())
            visible_ids = [dialog.list_widget.item(index).data(256)["chip_id"] for index in range(dialog.list_widget.count())]
            self.assertNotIn("asm1061", visible_ids)

            dialog._restore_all_chips()
            _pump_events(self.app, 80)
            self.assertEqual(dialog.hidden_chip_ids_list(), [])
            dialog._select_type("PCIE转SATA")
            _pump_events(self.app, 80)
            visible_ids = [dialog.list_widget.item(index).data(256)["chip_id"] for index in range(dialog.list_widget.count())]
            self.assertIn("asm1061", visible_ids)

        dialog.close()
        _pump_events(self.app, 60)

    def test_chip_selection_dialog_groups_chips_by_type(self) -> None:
        dialog = ChipSelectionDialog(self.library.get("chips", []), [], "amd_family_19h_model_78h")
        dialog.show()
        _pump_events(self.app, 100)

        type_labels = [dialog.type_list_widget.item(index).data(256) for index in range(dialog.type_list_widget.count())]
        self.assertIn("EC芯片", type_labels)
        self.assertIn("SIO", type_labels)
        self.assertIn("CPU", type_labels)
        self.assertIn("PCIE转SATA", type_labels)
        self.assertIn("充电IC", type_labels)
        self.assertIn("电量计", type_labels)
        self.assertIn("温感", type_labels)

        dialog._select_type("CPU")
        _pump_events(self.app, 80)
        visible_ids = [dialog.list_widget.item(index).data(256)["chip_id"] for index in range(dialog.list_widget.count())]
        self.assertEqual(visible_ids, ["amd_family_19h_model_78h"])

        dialog._select_type("充电IC")
        _pump_events(self.app, 80)
        visible_ids = [dialog.list_widget.item(index).data(256)["chip_id"] for index in range(dialog.list_widget.count())]
        self.assertIn("bq25720", visible_ids)

        dialog.close()
        _pump_events(self.app, 60)

    def test_hidden_chip_ids_are_applied_to_window_list(self) -> None:
        save_hidden_chip_ids(["asm1061"])
        window = ChipLibraryWindow(library=self.library, test_mode=True)
        window.show()
        _pump_events(self.app, 180)

        visible_ids = [chip["chip_id"] for chip in window.chips]
        self.assertNotIn("asm1061", visible_ids)
        self.assertIn("asm1061", window.hidden_chip_ids)

        window.close()
        _pump_events(self.app, 60)

    def test_deleted_chip_ids_can_be_persisted_into_effective_library(self) -> None:
        save_hidden_chip_ids(["asm1061"])
        effective = load_chip_library()

        visible_ids = [chip["chip_id"] for chip in effective.get("chips", [])]
        self.assertNotIn("asm1061", visible_ids)


if __name__ == "__main__":
    unittest.main()

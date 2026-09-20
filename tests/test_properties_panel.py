from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox

from openseespy_studio.ui.main_window import PropertiesPanel


_APP = QApplication.instance() or QApplication([])


def _close(panel: PropertiesPanel) -> None:
    panel.close()
    panel.deleteLater()
    _APP.processEvents()


def test_properties_panel_distinguishes_read_only_and_editable_values():
    panel = PropertiesPanel()
    try:
        panel.set_properties(
            "Frame",
            [
                ("Tag", 7),
                (
                    "Group",
                    "frame",
                    {
                        "id": "group",
                        "editable": True,
                        "kind": "text",
                    },
                ),
                (
                    "Type",
                    "elasticBeamColumn",
                    {
                        "id": "element_type",
                        "editable": True,
                        "kind": "choice",
                        "current": "elasticBeamColumn",
                        "choices": [
                            ("elasticBeamColumn", "elasticBeamColumn"),
                            ("forceBeamColumn", "forceBeamColumn"),
                        ],
                    },
                ),
            ],
            context={"kind": "element", "tag": 7},
        )

        tag_item = panel.table.item(0, 1)
        group_item = panel.table.item(1, 1)
        assert tag_item is not None
        assert group_item is not None
        assert not bool(tag_item.flags() & Qt.ItemIsEditable)
        assert bool(group_item.flags() & Qt.ItemIsEditable)

        combo = panel.table.cellWidget(2, 1)
        assert isinstance(combo, QComboBox)
        assert combo.currentData() == "elasticBeamColumn"
    finally:
        _close(panel)


def test_properties_panel_emits_direct_edit_payloads():
    panel = PropertiesPanel()
    events: list[dict[str, object]] = []
    panel.property_edited.connect(events.append)
    try:
        panel.set_properties(
            "Node",
            [
                (
                    "X",
                    "1",
                    {
                        "id": "x",
                        "editable": True,
                        "kind": "float",
                    },
                ),
                (
                    "UX",
                    "Free",
                    {
                        "id": "fixity_0",
                        "editable": True,
                        "kind": "choice",
                        "current": 0,
                        "choices": [("Free", 0), ("Fixed", 1)],
                    },
                ),
            ],
            context={"kind": "node", "tag": 3},
        )

        panel.table.item(0, 1).setText("2.5")
        combo = panel.table.cellWidget(1, 1)
        assert isinstance(combo, QComboBox)
        combo.setCurrentIndex(1)
        _APP.processEvents()

        assert events[0]["context"] == {"kind": "node", "tag": 3}
        assert events[0]["id"] == "x"
        assert events[0]["value"] == "2.5"
        assert events[1]["id"] == "fixity_0"
        assert events[1]["value"] == 1
    finally:
        _close(panel)

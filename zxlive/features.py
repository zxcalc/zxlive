from __future__ import annotations

from typing import Optional, TypedDict

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel,
                               QVBoxLayout, QWidget)

from .common import get_settings_value, set_settings_value
from .settings import feature_defaults


class FeatureData(TypedDict):
    id: str
    label: str
    tooltip: str


FAULT_EQUIVALENCE = "feature/fault-equivalence"
ZW_CALCULUS = "feature/zw-calculus"
PAULI_WEBS = "feature/pauli-webs"

# Records whether the first-run feature picker has been shown.
PICKER_SEEN = "features/picker-seen"

FEATURES: list[FeatureData] = [
    {
        "id": FAULT_EQUIVALENCE,
        "label": "Fault-equivalent rewrites",
        "tooltip": "Show the fault-equivalent rewrite mode in the proof panel. "
                   "These rewrites preserve the fault tolerance of a diagram.",
    },
    {
        "id": ZW_CALCULUS,
        "label": "ZW-calculus (W-nodes and Z-boxes)",
        "tooltip": "Show W-node and Z-box vertices in the editor sidebar.",
    },
    {
        "id": PAULI_WEBS,
        "label": "Pauli webs",
        "tooltip": "Show the Pauli webs button in the editor and proof panels.",
    },
]


def is_feature_enabled(feature_id: str) -> bool:
    return get_settings_value(feature_id, bool, feature_defaults[feature_id])


def set_feature_enabled(feature_id: str, enabled: bool) -> None:
    set_settings_value(feature_id, enabled, bool)


def has_seen_feature_picker() -> bool:
    return get_settings_value(PICKER_SEEN, bool, False)


def mark_feature_picker_seen() -> None:
    set_settings_value(PICKER_SEEN, True, bool)


class FeaturePickerDialog(QDialog):
    """First-run picker for the optional features listed under View > Features."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to ZXLive")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)

        intro = QLabel(
            "ZXLive keeps its more specialised features out of the way by default. "
            "Tick the ones you would like to use \u2014 you can change this at any time "
            "from the View \u2192 Features menu.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addSpacing(8)

        self.checkboxes: dict[str, QCheckBox] = {}
        for feature in FEATURES:
            checkbox = QCheckBox(feature["label"])
            checkbox.setChecked(is_feature_enabled(feature["id"]))
            layout.addWidget(checkbox)
            description = QLabel(feature["tooltip"])
            description.setWordWrap(True)
            description.setIndent(22)
            description.setEnabled(False)  # dims the text in both light and dark themes
            layout.addWidget(description)
            layout.addSpacing(4)
            self.checkboxes[feature["id"]] = checkbox

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        if (ok_button := button_box.button(QDialogButtonBox.StandardButton.Ok)) is not None:
            ok_button.setText("Continue")
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

    def selection(self) -> dict[str, bool]:
        return {feature_id: box.isChecked() for feature_id, box in self.checkboxes.items()}


def show_feature_picker(parent: QWidget) -> Optional[dict[str, bool]]:
    """Ask which optional features to enable. Returns None if the dialog was dismissed."""
    dialog = FeaturePickerDialog(parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selection()
    return None

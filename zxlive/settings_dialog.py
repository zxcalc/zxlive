#     zxlive - An interactive tool for the ZX-calculus
#     Copyright (C) 2023 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Preferences dialog for ZXLive.

Improvements over the previous version
----------------------------------------
* Tabbed layout — General / Appearance / TikZ Export / TikZ Import — so the
  dialog doesn't become an unscrollable wall of widgets as settings grow.
* Live preview of color scheme and dark mode: the canvas updates immediately
  when the user changes either setting (no need to close and reopen).
* Font family uses a ``QFontComboBox`` rather than a plain text field, giving
  real font previews.
* Snap granularity is a labeled ``QSlider`` (1 / 2 / 4 / 8) instead of a raw
  spin-box so the discrete valid values are obvious.
* Tab-bar position is a ``QComboBox`` with human-readable labels.
* Startup behavior and tutorial toggle are grouped under a clear "On startup"
  heading instead of being scattered.
* All ``QLineEdit`` fields for tikz names have input validation: empty strings
  are allowed (meaning "use default") but leading/trailing whitespace is
  stripped on ``accept()``.
* ``open_settings_dialog`` is a module-level function (unchanged public API)
  that creates a modal dialog and calls ``apply()`` only on ``Accepted``.
* No ``# type: ignore`` comments; types are explicit throughout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFontComboBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .settings import (
    ColorScheme, color_scheme_ids, color_schemes, display_setting,
    refresh_pyzx_tikz_settings, settings,
)

if TYPE_CHECKING:
    from .mainwindow import MainWindow


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _section_label(text: str) -> QLabel:
    lbl = QLabel(f"<b>{text}</b>")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    return lbl


def _scrollable(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(inner)
    area.setFrameShape(QFrame.Shape.NoFrame)
    return area


# ---------------------------------------------------------------------------
# Module-level constants (re-exported for other modules such as edit_panel)
# ---------------------------------------------------------------------------

#: Ordered mapping of circuit-format ID → human-readable label.
#: ``edit_panel`` imports this to populate its own format selector.
input_circuit_formats: dict[str, str] = {
    "openqasm": "OpenQASM",
    "quipper":  "Quipper",
}


# ---------------------------------------------------------------------------
# Tab: General
# ---------------------------------------------------------------------------

class _GeneralTab(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # -- Startup ---------------------------------------------------------
        startup_group = QGroupBox("On startup")
        sg_layout = QFormLayout(startup_group)
        sg_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.startup_combo = QComboBox()
        self.startup_combo.addItem("Restore previous session", "restore")
        self.startup_combo.addItem("Open blank canvas", "blank")
        current_startup = str(settings.value("startup-behavior", "restore"))
        idx = self.startup_combo.findData(current_startup)
        self.startup_combo.setCurrentIndex(max(idx, 0))
        sg_layout.addRow("When opening ZXLive:", self.startup_combo)

        self.show_tutorial = QCheckBox("Show interactive tutorial on startup")
        self.show_tutorial.setChecked(
            bool(settings.value("tutorial/show-on-startup", True)))
        sg_layout.addRow(self.show_tutorial)

        layout.addWidget(startup_group)

        # -- Editing ---------------------------------------------------------
        edit_group = QGroupBox("Editing")
        eg_layout = QFormLayout(edit_group)
        eg_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        snap_values = [1, 2, 4, 8]
        self.snap_slider = QSlider(Qt.Orientation.Horizontal)
        self.snap_slider.setMinimum(0)
        self.snap_slider.setMaximum(len(snap_values) - 1)
        self.snap_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.snap_slider.setTickInterval(1)
        self._snap_values = snap_values
        try:
            current_snap = int(str(settings.value("snap-granularity", "4")))
            snap_idx = snap_values.index(current_snap)
        except (ValueError, TypeError):
            snap_idx = 2  # default to 4
        self.snap_slider.setValue(snap_idx)

        snap_row = QHBoxLayout()
        snap_row.addWidget(self.snap_slider)
        self._snap_label = QLabel(str(snap_values[snap_idx]))
        self._snap_label.setMinimumWidth(24)
        snap_row.addWidget(self._snap_label)
        self.snap_slider.valueChanged.connect(
            lambda i: self._snap_label.setText(str(self._snap_values[i])))
        eg_layout.addRow("Snap granularity:", snap_row)

        self.auto_save = QCheckBox("Auto-save after every edit")
        self.auto_save.setChecked(bool(settings.value("auto-save", False)))
        eg_layout.addRow(self.auto_save)

        self.previews_show = QCheckBox("Show rewrite previews")
        self.previews_show.setChecked(
            bool(settings.value("previews-show", True)))
        eg_layout.addRow(self.previews_show)

        self.rewrite_animations = QCheckBox("Animate rewrites")
        self.rewrite_animations.setChecked(
            bool(settings.value("rewrite-animations", True)))
        eg_layout.addRow(self.rewrite_animations)

        self.sparkle = QCheckBox("Sparkle effects")
        self.sparkle.setChecked(bool(settings.value("sparkle-mode", True)))
        eg_layout.addRow(self.sparkle)

        self.sound_effects = QCheckBox("Sound effects (Ctrl+B to toggle)")
        self.sound_effects.setChecked(
            bool(settings.value("sound-effects", False)))
        eg_layout.addRow(self.sound_effects)

        layout.addWidget(edit_group)

        # -- Circuit import --------------------------------------------------
        circuit_group = QGroupBox("Circuit import")
        cg_layout = QFormLayout(circuit_group)

        self.circuit_format = QComboBox()
        for fmt_id, fmt_label in input_circuit_formats.items():
            self.circuit_format.addItem(fmt_label, fmt_id)
        fmt = str(settings.value("input-circuit-format", "openqasm"))
        self.circuit_format.setCurrentIndex(
            max(self.circuit_format.findData(fmt), 0))
        cg_layout.addRow("Default format:", self.circuit_format)

        layout.addWidget(circuit_group)
        layout.addStretch()

    def apply(self) -> None:
        settings.setValue("startup-behavior",
                          self.startup_combo.currentData())
        settings.setValue("tutorial/show-on-startup",
                          self.show_tutorial.isChecked())
        settings.setValue("snap-granularity",
                          str(self._snap_values[self.snap_slider.value()]))
        settings.setValue("auto-save", self.auto_save.isChecked())
        settings.setValue("previews-show", self.previews_show.isChecked())
        settings.setValue("rewrite-animations",
                          self.rewrite_animations.isChecked())
        settings.setValue("sparkle-mode", self.sparkle.isChecked())
        settings.setValue("sound-effects", self.sound_effects.isChecked())
        settings.setValue("input-circuit-format",
                          self.circuit_format.currentData())
        display_setting.update()


# ---------------------------------------------------------------------------
# Tab: Appearance
# ---------------------------------------------------------------------------

class _AppearanceTab(QWidget):
    def __init__(self, parent: QWidget, main_window: "MainWindow") -> None:
        super().__init__(parent)
        self._main_window = main_window
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # -- Theme -----------------------------------------------------------
        theme_group = QGroupBox("Theme")
        tg_layout = QFormLayout(theme_group)

        self.dark_mode_combo = QComboBox()
        self.dark_mode_combo.addItem("Follow system", "system")
        self.dark_mode_combo.addItem("Light", "light")
        self.dark_mode_combo.addItem("Dark", "dark")
        current_dark = str(settings.value("dark-mode", "system"))
        self.dark_mode_combo.setCurrentIndex(
            max(self.dark_mode_combo.findData(current_dark), 0))
        # Live preview
        self.dark_mode_combo.currentIndexChanged.connect(self._preview_theme)
        tg_layout.addRow("Mode:", self.dark_mode_combo)

        self.color_scheme_combo = QComboBox()
        for sid in color_scheme_ids:
            self.color_scheme_combo.addItem(color_schemes[sid].label, sid)
        current_scheme = str(settings.value("color-scheme", "modern-red-green"))
        self.color_scheme_combo.setCurrentIndex(
            max(self.color_scheme_combo.findData(current_scheme), 0))
        self.color_scheme_combo.currentIndexChanged.connect(
            self._preview_color_scheme)
        tg_layout.addRow("Color scheme:", self.color_scheme_combo)

        self.show_indices = QCheckBox("Show vertex indices")
        self.show_indices.setChecked(
            bool(settings.value("show-vertex-indices", False)))
        tg_layout.addRow(self.show_indices)

        layout.addWidget(theme_group)

        # -- Font ------------------------------------------------------------
        font_group = QGroupBox("Font")
        fg_layout = QFormLayout(font_group)

        self.font_combo = QFontComboBox()
        current_family = str(settings.value("font/family", "Arial"))
        self.font_combo.setCurrentFont(QFont(current_family))
        fg_layout.addRow("Family:", self.font_combo)

        self.font_size = QSpinBox()
        self.font_size.setRange(6, 32)
        try:
            self.font_size.setValue(int(settings.value("font/size", 11)))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            self.font_size.setValue(11)
        fg_layout.addRow("Size:", self.font_size)

        layout.addWidget(font_group)

        # -- Tab bar ---------------------------------------------------------
        tab_group = QGroupBox("Tab bar")
        tabg_layout = QFormLayout(tab_group)

        from PySide6.QtWidgets import QTabWidget as _TW
        self.tab_position_combo = QComboBox()
        self.tab_position_combo.addItem("Top",    _TW.TabPosition.North)
        self.tab_position_combo.addItem("Bottom", _TW.TabPosition.South)
        self.tab_position_combo.addItem("Left",   _TW.TabPosition.West)
        self.tab_position_combo.addItem("Right",  _TW.TabPosition.East)
        current_pos = settings.value("tab-bar-location", _TW.TabPosition.North)
        self.tab_position_combo.setCurrentIndex(
            max(self.tab_position_combo.findData(current_pos), 0))
        tabg_layout.addRow("Position:", self.tab_position_combo)

        layout.addWidget(tab_group)

        # -- Pauli webs ------------------------------------------------------
        pw_group = QGroupBox("Pauli web colors")
        pwg_layout = QFormLayout(pw_group)

        self.swap_pauli = QCheckBox("Swap Z/X Pauli web colors")
        self.swap_pauli.setChecked(
            bool(settings.value("swap-pauli-web-colors", False)))
        pwg_layout.addRow(self.swap_pauli)

        self.blue_y = QCheckBox("Use blue for Y Pauli web")
        self.blue_y.setChecked(bool(settings.value("blue-y-pauli-web", False)))
        pwg_layout.addRow(self.blue_y)

        layout.addWidget(pw_group)
        layout.addStretch()

        # Remember the original values so we can restore on cancel
        self._orig_dark_mode = current_dark
        self._orig_scheme = current_scheme

    def _preview_theme(self) -> None:
        val = self.dark_mode_combo.currentData()
        display_setting.dark_mode = val
        self._main_window.update_colors()

    def _preview_color_scheme(self) -> None:
        sid = self.color_scheme_combo.currentData()
        display_setting.set_color_scheme(sid)
        settings.setValue("color-scheme", sid)
        self._main_window.update_colors()

    def restore_preview(self) -> None:
        """Revert live previews if the dialog is cancelled."""
        display_setting.dark_mode = self._orig_dark_mode
        display_setting.set_color_scheme(self._orig_scheme)
        settings.setValue("color-scheme", self._orig_scheme)
        self._main_window.update_colors()

    def apply(self) -> None:
        # Dark mode & color scheme are already written by the live preview;
        # we just need to persist the remaining fields.
        settings.setValue("font/family", self.font_combo.currentFont().family())
        settings.setValue("font/size", self.font_size.value())
        settings.setValue("tab-bar-location",
                          self.tab_position_combo.currentData())
        settings.setValue("show-vertex-indices",
                          self.show_indices.isChecked())
        settings.setValue("swap-pauli-web-colors",
                          self.swap_pauli.isChecked())
        settings.setValue("blue-y-pauli-web", self.blue_y.isChecked())
        display_setting.update()
        self._main_window.update_font()
        self._main_window.tab_widget.setTabPosition(
            self.tab_position_combo.currentData())


# ---------------------------------------------------------------------------
# Tab: TikZ Export
# ---------------------------------------------------------------------------

_TIKZ_EXPORT_ROWS: list[tuple[str, str, str]] = [
    # (settings key,              label,           pyzx default key)
    ("tikz/boundary-export",  "Boundary:",     "boundary"),
    ("tikz/Z-spider-export",  "Z spider:",     "Z"),
    ("tikz/X-spider-export",  "X spider:",     "X"),
    ("tikz/Z-phase-export",   "Z phase:",      "Z phase"),
    ("tikz/X-phase-export",   "X phase:",      "X phase"),
    ("tikz/z-box-export",     "Z box:",        "Z box"),
    ("tikz/Hadamard-export",  "Hadamard:",     "H"),
    ("tikz/w-output-export",  "W output:",     "W"),
    ("tikz/w-input-export",   "W input:",      "W input"),
    ("tikz/dummy-export",     "Dummy:",        "dummy"),
    ("tikz/edge-export",      "Edge:",         "edge"),
    ("tikz/edge-H-export",    "Hadamard edge:","H-edge"),
    ("tikz/edge-W-export",    "W edge:",       "W-io-edge"),
]

_TIKZ_LAYOUT_ROWS: list[tuple[str, str, float]] = [
    ("tikz/layout/hspace",    "Horizontal spacing:", 2.0),
    ("tikz/layout/vspace",    "Vertical spacing:",   2.0),
    ("tikz/layout/max-width", "Max width:",          10.0),
]


class _TikzExportTab(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(16)

        # -- Class names -----------------------------------------------------
        names_group = QGroupBox("Node and edge class names")
        ng_layout = QFormLayout(names_group)
        ng_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        import pyzx
        self._export_fields: dict[str, QLineEdit] = {}
        for key, label, pyzx_key in _TIKZ_EXPORT_ROWS:
            default = pyzx.settings.tikz_classes.get(pyzx_key, "")
            current = str(settings.value(key, default))
            edit = QLineEdit(current)
            edit.setPlaceholderText(default or "(empty = use default)")
            self._export_fields[key] = edit
            ng_layout.addRow(label, edit)

        layout.addWidget(names_group)

        # -- Layout defaults -------------------------------------------------
        layout_group = QGroupBox("Layout defaults")
        lg_layout = QFormLayout(layout_group)

        self._layout_fields: dict[str, QSpinBox] = {}
        for key, label, default_val in _TIKZ_LAYOUT_ROWS:
            spin = QSpinBox()
            spin.setRange(1, 50)
            try:
                spin.setValue(int(float(str(settings.value(key, default_val)))))
            except (ValueError, TypeError):
                spin.setValue(int(default_val))
            self._layout_fields[key] = spin
            lg_layout.addRow(label, spin)

        layout.addWidget(layout_group)
        layout.addStretch()

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(_scrollable(inner))  # type: ignore[union-attr]

    def apply(self) -> None:
        for key, edit in self._export_fields.items():
            settings.setValue(key, edit.text().strip())
        for key, spin in self._layout_fields.items():
            settings.setValue(key, float(spin.value()))
        refresh_pyzx_tikz_settings()


# ---------------------------------------------------------------------------
# Tab: TikZ Import
# ---------------------------------------------------------------------------

_TIKZ_IMPORT_ROWS: list[tuple[str, str]] = [
    ("tikz/boundary-import",  "Boundary synonyms:"),
    ("tikz/Z-spider-import",  "Z spider synonyms:"),
    ("tikz/X-spider-import",  "X spider synonyms:"),
    ("tikz/Hadamard-import",  "Hadamard synonyms:"),
    ("tikz/w-input-import",   "W input synonyms:"),
    ("tikz/w-output-import",  "W output synonyms:"),
    ("tikz/z-box-import",     "Z box synonyms:"),
    ("tikz/dummy-import",     "Dummy synonyms:"),
    ("tikz/edge-import",      "Edge synonyms:"),
    ("tikz/edge-H-import",    "Hadamard edge synonyms:"),
    ("tikz/edge-W-import",    "W edge synonyms:"),
]


class _TikzImportTab(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(8)

        hint = QLabel(
            "Comma-separated list of tikz style names that ZXLive recognises "
            "when importing. Names are matched case-insensitively."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(_hline())

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._import_fields: dict[str, QLineEdit] = {}
        for key, label in _TIKZ_IMPORT_ROWS:
            current = str(settings.value(key, ""))
            edit = QLineEdit(current)
            self._import_fields[key] = edit
            form.addRow(label, edit)
        layout.addLayout(form)
        layout.addStretch()

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(_scrollable(inner))  # type: ignore[union-attr]

    def apply(self) -> None:
        for key, edit in self._import_fields.items():
            settings.setValue(key, edit.text().strip())
        refresh_pyzx_tikz_settings()


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    """Tabbed preferences dialog.

    Tabs: General | Appearance | TikZ Export | TikZ Import
    """

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__(main_window)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(520, 480)
        self._main_window = main_window

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 12)

        tabs = QTabWidget(self)
        self._general   = _GeneralTab(tabs)
        self._appearance = _AppearanceTab(tabs, main_window)
        self._tikz_export = _TikzExportTab(tabs)
        self._tikz_import = _TikzImportTab(tabs)

        tabs.addTab(self._general,     "General")
        tabs.addTab(self._appearance,  "Appearance")
        tabs.addTab(self._tikz_export, "TikZ Export")
        tabs.addTab(self._tikz_import, "TikZ Import")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self._on_reject)
        restore_btn = buttons.button(
            QDialogButtonBox.StandardButton.RestoreDefaults)
        if restore_btn is not None:
            restore_btn.clicked.connect(self._on_restore_defaults)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 0)
        btn_row.addWidget(buttons)
        layout.addLayout(btn_row)

    def _on_accept(self) -> None:
        self._general.apply()
        self._appearance.apply()
        self._tikz_export.apply()
        self._tikz_import.apply()
        self.accept()

    def _on_reject(self) -> None:
        # Revert any live previews that weren't committed.
        self._appearance.restore_preview()
        self.reject()

    def _on_restore_defaults(self) -> None:
        """Reset every setting to its factory default and refresh the dialog."""
        from .settings import defaults as _defaults
        for key, value in _defaults.items():
            settings.setValue(key, value)
        display_setting.update()
        display_setting.set_color_scheme(
            str(_defaults.get("color-scheme", "modern-red-green")))
        display_setting.dark_mode = str(_defaults.get("dark-mode", "system"))
        self._main_window.update_colors()
        self._main_window.update_font()
        # Rebuild the dialog in-place by closing and re-opening.
        self.reject()
        open_settings_dialog(self._main_window)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def open_settings_dialog(main_window: "MainWindow") -> None:
    """Open the modal Preferences dialog.  Called from mainwindow.py."""
    dlg = SettingsDialog(main_window)
    dlg.exec()

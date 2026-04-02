from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QFile, QIODevice, QTextStream, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget, QInputDialog)
from pyzx import Circuit, extract_circuit
from pyzx.utils import VertexType

from .common import GraphT, VT, find_unknown_tikz_styles, from_tikz
from .settings import get_settings_value
from .custom_rule import CustomRule, check_rule
from .proof import ProofModel

if TYPE_CHECKING:
    from .mainwindow import MainWindow


class FileFormat(Enum):
    """Supported formats for importing/exporting diagrams."""

    All = "zxg *.json *.qasm *.tikz *.zxp *.zxr *.gif", "All Supported Formats"
    QGraph = "zxg", "QGraph"  # "file extension", "format name"
    QASM = "qasm", "QASM"
    TikZ = "tikz", "TikZ"
    Json = "json", "JSON"
    ZXProof = "zxp", "ZXProof"
    ZXRule = "zxr", "ZXRule"
    Gif = "gif", "Gif"
    _value_: str

    def __new__(cls, *args, **kwds):  # type: ignore
        obj = object.__new__(cls)
        obj._value_ = args[0]  # Use extension as `_value_`
        return obj

    def __init__(self, _extension: str, name: str) -> None:
        # Ignore extension param since it's already set by `__new__`
        self._name = name

    @property
    def extension(self) -> str:
        """The file extension for this format.

        The extension is returned *without* a leading dot."""
        return self._value_

    @property
    def name(self) -> str:
        """The text used to display this file format."""
        return self._name_

    @property
    def filter(self) -> str:
        """The filter string for this file type.

        Used by `QFileDialog` to filter the shown file extensions."""
        return f"{self.name} (*.{self.extension})"


@dataclass
class ImportGraphOutput:
    file_type: FileFormat
    file_path: str
    g: GraphT


@dataclass
class ImportProofOutput:
    file_type: FileFormat
    file_path: str
    p: ProofModel


@dataclass
class ImportRuleOutput:
    file_type: FileFormat
    file_path: str
    r: CustomRule


def show_error_msg(title: str, description: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
    """Displays an error message box."""
    msg = QMessageBox(parent)  # Set the parent of the QMessageBox
    msg.setText(title)
    msg.setIcon(QMessageBox.Icon.Critical)
    if description is not None:
        msg.setInformativeText(description)
    msg.exec()


class TikzUnknownStylesDialog(QDialog):
    """Dialog for categorising unknown TikZ vertex styles.

    Shows the unknown styles found during import and lets the user assign
    each to a vertex category (Z spider, X spider, etc.) or skip it.
    The chosen mappings are saved to the TikZ import preferences so that
    future imports recognise the styles automatically.
    """

    # (display label, settings key). ``None`` means "skip this style".
    # TODO(#537): Unify the settings keys with the ones in settings.py
    # so accidental mismatches don't get introduced in the future.
    CATEGORIES: list[tuple[str, Optional[str]]] = [
        ("(skip)", None),
        ("Z spider", "tikz/Z-spider-import"),
        ("X spider", "tikz/X-spider-import"),
        ("Boundary", "tikz/boundary-import"),
        ("H-box", "tikz/Hadamard-import"),
        ("W input", "tikz/w-input-import"),
        ("W output", "tikz/w-output-import"),
        ("Z box", "tikz/z-box-import"),
        ("Dummy", "tikz/dummy-import"),
    ]

    RETRY = 1
    IGNORE = 2

    def __init__(self, unknown_styles: list[str], error_msg: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("TikZ import: unknown styles")
        self.result_action = 0

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "The following vertex styles are not recognised.\n"
            "Assign each to a category, or skip it."
        ))

        if error_msg:
            err = QLabel(error_msg)
            err.setWordWrap(True)
            layout.addWidget(err)

        form = QFormLayout()
        self._combos: list[tuple[str, QComboBox]] = []
        for style in unknown_styles:
            combo = QComboBox()
            for label, _ in self.CATEGORIES:
                combo.addItem(label)
            form.addRow(f'"{style}"', combo)
            self._combos.append((style, combo))
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        retry_btn = QPushButton("Add to preferences && retry")
        retry_btn.clicked.connect(lambda: self._finish(self.RETRY))
        ignore_btn = QPushButton("Import ignoring errors")
        ignore_btn.clicked.connect(lambda: self._finish(self.IGNORE))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(retry_btn)
        btn_layout.addWidget(ignore_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _finish(self, action: int) -> None:
        self.result_action = action
        self.accept()

    def selected_mappings(self) -> dict[str, str]:
        """Return ``{style_name: settings_key}`` for non-skipped entries."""
        mappings: dict[str, str] = {}
        for style, combo in self._combos:
            idx = combo.currentIndex()
            _, key = self.CATEGORIES[idx]
            if key is not None:
                mappings[style] = key
        return mappings


def _apply_tikz_style_mappings(mappings: dict[str, str]) -> None:
    """Add *mappings* to the TikZ import preferences and refresh PyZX synonyms.

    Each key in *mappings* is a style name; each value is a settings key
    such as ``"tikz/Z-spider-import"``.
    """
    from .settings import settings, refresh_pyzx_tikz_settings

    for style, key in mappings.items():
        current = str(settings.value(key, ""))
        entries = [s.strip() for s in current.split(",") if s.strip()]
        if style.lower() not in (e.lower() for e in entries):
            entries.append(style)
            settings.setValue(key, ", ".join(entries))

    refresh_pyzx_tikz_settings()


def _confirm_ignore_errors(title: str, body: str, button_text: str,
                           parent: Optional[QWidget]) -> bool:
    """Show a warning dialog with a custom accept button; return ``True`` if accepted."""
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setText(title)
    msg.setInformativeText(body)
    accept_btn = msg.addButton(button_text, QMessageBox.ButtonRole.AcceptRole)
    msg.addButton(QMessageBox.StandardButton.Cancel)
    msg.exec()
    return msg.clickedButton() is accept_btn


def _retry_strict_with_mappings(tikz: str, mappings: dict[str, str],
                                parent: Optional[QWidget]) -> tuple[Optional[GraphT], bool]:
    """Apply style mappings and retry strict TikZ import.

    Returns ``(graph, fall_through)``: ``graph`` is the imported graph on
    success, otherwise ``None``; ``fall_through`` is ``True`` if the strict
    retry failed and the user chose to attempt a tolerant import next.
    """
    if mappings:
        _apply_tikz_style_mappings(mappings)
    try:
        return from_tikz(tikz), False
    except Exception as retry_error:
        return None, _confirm_ignore_errors(
            "TikZ import: remaining errors",
            f"Style mappings were saved, but other errors remain:\n{retry_error}",
            "Import ignoring remaining errors", parent)


def try_import_tikz(tikz: str, parent: Optional[QWidget] = None) -> Optional[GraphT]:
    """Import TikZ with interactive error handling.

    Tries strict import first.  On failure, if unknown styles are found,
    shows a dialog that lets the user categorise them (saving the mappings
    to preferences) and retry.  Otherwise offers to retry with all errors
    tolerated.
    """
    try:
        return from_tikz(tikz)
    except Exception as e:
        strict_error = e

    unknown = find_unknown_tikz_styles(tikz)
    if unknown:
        dlg = TikzUnknownStylesDialog(unknown, str(strict_error), parent=parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        if dlg.result_action == TikzUnknownStylesDialog.RETRY:
            graph, fall_through = _retry_strict_with_mappings(
                tikz, dlg.selected_mappings(), parent)
            if graph is not None:
                return graph
            if not fall_through:
                return None
    elif not _confirm_ignore_errors("TikZ import error", str(strict_error),
                                    "Retry ignoring errors", parent):
        return None

    try:
        return from_tikz(tikz, ignore_errors=True)
    except Exception as e:
        show_error_msg("TikZ import error",
                       f"Error while importing TikZ: {e}",
                       parent=parent)
        return None


def import_diagram_dialog(parent: QWidget) -> Optional[ImportGraphOutput | ImportProofOutput | ImportRuleOutput]:
    """Shows a dialog to import a diagram from disk.

    Returns the imported graph or `None` if the import failed."""
    file_path, selected_filter = QFileDialog.getOpenFileName(
        parent=parent,
        caption="Open File",
        filter=";;".join([f.filter for f in FileFormat]),
    )
    if selected_filter == "":
        # This happens if the user clicks on cancel
        return None

    return import_diagram_from_file(file_path, selected_filter, parent)


def create_circuit_dialog(explanation: str, example: str, parent: QWidget) -> Optional[str]:
    """Shows a dialog to input a circuit."""
    s, success = QInputDialog.getMultiLineText(parent, "Circuit input", explanation, example)
    return s if success else None


# TODO: Fix code complexity
# noqa: complexipy
def import_diagram_from_file(file_path: str, selected_filter: str = FileFormat.All.filter, parent: Optional[QWidget] = None) -> \
        Optional[ImportGraphOutput | ImportProofOutput | ImportRuleOutput]:  # noqa: PLR0912
    """Imports a diagram from a given file path.

    Returns the imported graph or `None` if the import failed."""
    file = QFile(file_path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        show_error_msg(f"Could not open file: {file_path}.", parent=parent)
        return None
    stream = QTextStream(file)
    data = stream.readAll()
    file.close()

    selected_format = next(f for f in FileFormat if f.filter == selected_filter)
    if selected_format == FileFormat.All:
        ext = file_path.split(".")[-1]
        try:
            selected_format = next(f for f in FileFormat if f.extension == ext)
        except StopIteration:
            show_error_msg("Failed to import file", f"Couldn't determine filetype: {file_path}.", parent=parent)
            return None

    # TODO: This would be nicer with match statements (requires python 3.10 though)...
    try:
        if selected_format == FileFormat.ZXProof:
            return ImportProofOutput(selected_format, file_path, ProofModel.from_json(data))
        elif selected_format == FileFormat.ZXRule:
            return ImportRuleOutput(selected_format, file_path, CustomRule.from_json(data))
        elif selected_format in (FileFormat.QGraph, FileFormat.Json):
            g = GraphT.from_json(data)
            if TYPE_CHECKING:
                assert isinstance(g, GraphT)
            g.set_auto_simplify(False)
            return ImportGraphOutput(selected_format, file_path, g)  # type: ignore # This is something that needs to be better annotated in PyZX
        elif selected_format == FileFormat.QASM:
            g = Circuit.from_qasm(data).to_graph(zh=True, backend='multigraph')  # type: ignore # We know the return type is Multigraph, but mypy doesn't
            if TYPE_CHECKING:
                assert isinstance(g, GraphT)
            g.set_auto_simplify(False)
            return ImportGraphOutput(selected_format, file_path, g)  # type: ignore
        elif selected_format == FileFormat.TikZ:
            tikz_g = try_import_tikz(data, parent=parent)
            if tikz_g is None:
                return None
            return ImportGraphOutput(selected_format, file_path, tikz_g)
        else:
            assert selected_format == FileFormat.All
            try:
                g = Circuit.load(file_path).to_graph(zh=True, backend='multigraph')  # type: ignore # We know the return type is Multigraph, but mypy doesn't
                if TYPE_CHECKING:
                    assert isinstance(g, GraphT)
                g.set_auto_simplify(False)
                return ImportGraphOutput(FileFormat.QASM, file_path, g)  # type: ignore
            except TypeError:
                try:
                    g = GraphT.from_json(data)
                    if TYPE_CHECKING:
                        assert isinstance(g, GraphT)
                    g.set_auto_simplify(False)
                    return ImportGraphOutput(FileFormat.QGraph, file_path, g)  # type: ignore
                except Exception:
                    tikz_g = try_import_tikz(data, parent=parent)
                    if tikz_g is not None:
                        return ImportGraphOutput(FileFormat.TikZ, file_path, tikz_g)
                    show_error_msg(f"Failed to import {selected_format.name} file",
                                   f"Couldn't determine filetype: {file_path}.", parent=parent)
                    return None

    except Exception as e:
        show_error_msg(f"Failed to import {selected_format.name} file: {file_path}", str(e), parent=parent)
        return None


def write_to_file(file_path: str, data: str, parent: QWidget) -> bool:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data)
        return True
    except Exception as e:
        show_error_msg("Could not write to file", f"{file_path}\n{str(e)}", parent=parent)
        return False


def get_file_path_and_format(parent: QWidget, filter: str, default_input: str = "") -> Optional[tuple[str, FileFormat]]:
    file_path, selected_filter = QFileDialog.getSaveFileName(
        parent=parent,
        caption="Save File",
        dir=default_input,
        filter=filter,
    )
    if selected_filter == "":
        # This happens if the user clicks on cancel
        return None

    selected_format = next(f for f in FileFormat if f.filter == selected_filter)
    if selected_format == FileFormat.All:
        try:
            ext = file_path.split(".")[-1]
            selected_format = next(f for f in FileFormat if f.extension == ext)
        except StopIteration:
            show_error_msg("Unable to determine file format.", parent=parent)
            return None

    # Add file extension if missing
    if file_path.split(".")[-1].lower() != selected_format.extension:
        file_path += "." + selected_format.extension

    return file_path, selected_format


def save_diagram_dialog(graph: GraphT, parent: QWidget) -> Optional[tuple[str, FileFormat]]:
    file_path_and_format = get_file_path_and_format(parent, ";;".join([f.filter for f in FileFormat if f != FileFormat.ZXProof]))
    if file_path_and_format is None or not file_path_and_format[0]:
        return None
    file_path, selected_format = file_path_and_format

    if selected_format in (FileFormat.QGraph, FileFormat.Json):
        try:
            graph.auto_detect_io()
        except TypeError:
            pass
        data = graph.to_json()
    elif selected_format == FileFormat.QASM:
        try:
            circuit = extract_circuit(graph)
        except Exception as e:
            show_error_msg("Failed to convert the diagram to a circuit", str(e), parent=parent)
            return None
        data = circuit.to_qasm()
    else:
        assert selected_format == FileFormat.TikZ
        data = graph.to_tikz()

    if not write_to_file(file_path, data, parent):
        return None

    return file_path, selected_format


def _save_rule_or_proof_dialog(data: str, parent: QWidget, filter: str, filename: str = "") -> Optional[tuple[str, FileFormat]]:
    file_path_and_format = get_file_path_and_format(parent, filter, filename)
    if file_path_and_format is None or not file_path_and_format[0]:
        return None
    file_path, selected_format = file_path_and_format
    if not write_to_file(file_path, data, parent):
        return None
    return file_path, selected_format


def save_proof_dialog(proof_model: ProofModel, parent: QWidget) -> Optional[tuple[str, FileFormat]]:
    return _save_rule_or_proof_dialog(proof_model.to_json(), parent, FileFormat.ZXProof.filter)


def save_rule_dialog(rule: CustomRule, parent: QWidget, filename: str = "") -> Optional[tuple[str, FileFormat]]:
    rules_folder = get_settings_value("path/custom-rules", str)
    if filename:
        default_path = os.path.join(rules_folder, filename)
    elif rule.name:
        default_path = os.path.join(rules_folder, rule.name + ".zxr")
    else:
        default_path = rules_folder
    return _save_rule_or_proof_dialog(rule.to_json(), parent, FileFormat.ZXRule.filter, default_path)


def export_proof_dialog(parent: QWidget) -> Optional[str]:
    file_path_and_format = get_file_path_and_format(parent, FileFormat.TikZ.filter)
    if file_path_and_format is None or not file_path_and_format[0]:
        return None
    return file_path_and_format[0]


def export_gif_dialog(parent: QWidget) -> Optional[str]:
    file_path_and_format = get_file_path_and_format(parent, FileFormat.Gif.filter)
    if file_path_and_format is None or not file_path_and_format[0]:
        return None
    return file_path_and_format[0]


def get_lemma_name_and_description(parent: MainWindow) -> tuple[Optional[str], Optional[str]]:
    dialog = QDialog(parent)
    rewrite_form = QFormLayout(dialog)
    name = QLineEdit()
    rewrite_form.addRow("Name", name)
    description = QTextEdit()
    rewrite_form.addRow("Description", description)
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    rewrite_form.addRow(button_box)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return name.text(), description.toPlainText()
    return None, None


def create_new_rewrite(parent: MainWindow) -> None:
    dialog = QDialog(parent)
    rewrite_form = QFormLayout(dialog)
    name = QLineEdit()
    rewrite_form.addRow("Name", name)
    description = QTextEdit()
    rewrite_form.addRow("Description", description)
    left_button = QPushButton("Left-hand side of the rule")
    right_button = QPushButton("Right-hand side of the rule")
    left_graph = None
    right_graph = None

    def get_file(self: MainWindow, button: QPushButton, side: str) -> None:
        nonlocal left_graph, right_graph
        out = import_diagram_dialog(self)
        if out is not None and isinstance(out, ImportGraphOutput):
            button.setText(out.file_path)
            if side == "left":
                left_graph = out.g
            else:
                right_graph = out.g

    left_button.clicked.connect(lambda: get_file(parent, left_button, "left"))
    right_button.clicked.connect(lambda: get_file(parent, right_button, "right"))
    rewrite_form.addRow(left_button)
    rewrite_form.addRow(right_button)
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    rewrite_form.addRow(button_box)

    def add_rewrite() -> None:
        nonlocal left_graph, right_graph
        if left_graph is None or right_graph is None or name.text() == "" or description.toPlainText() == "":
            return
        rule = CustomRule(left_graph, right_graph, name.text(), description.toPlainText())
        try:
            check_rule(rule)
        except Exception as e:
            show_error_msg("Warning!", str(e), parent=parent)
        if save_rule_dialog(rule, parent):
            dialog.accept()
    button_box.accepted.connect(add_rewrite)
    button_box.rejected.connect(dialog.reject)
    if not dialog.exec():
        return


def update_dummy_vertex_text(parent: QWidget, graph: GraphT, v: VT) -> Optional[GraphT]:
    """Prompt the user for text and return a new graph with the text stored in the vertex's vdata under key 'text'.
    If the user cancels, return None. Otherwise, return the new graph with the updated vdata.
    """
    if graph.type(v) != VertexType.DUMMY:
        show_error_msg("Invalid Vertex Type", "This function can only be used on dummy vertices.", parent=parent)
        return None
    current_text = graph.vdata(v, 'text', '')
    input_, ok = QInputDialog.getText(
        parent, "Set Text",
        "Enter text (LaTeX supported, e.g. $\\alpha$, x^2, \\frac{1}{2}):",
        text=current_text)
    if not ok:
        return None
    new_g = copy.deepcopy(graph)
    new_g.set_vdata(v, 'text', input_)
    return new_g


def show_update_available_dialog(current_version: str, latest_version: str, release_url: str, parent: Optional[QWidget] = None) -> None:
    """Shows a dialog informing the user about a new version."""
    msg = QMessageBox(parent)
    msg.setWindowTitle("Update Available")
    msg.setText("A new version of ZXLive is available!")
    msg.setInformativeText(
        f"Current version: {current_version}\n"
        f"Latest version: {latest_version}\n\n"
        f"Visit the releases page to download the latest version."
    )
    msg.setIcon(QMessageBox.Icon.Information)
    view_release_button = msg.addButton("View Release", QMessageBox.ButtonRole.AcceptRole)
    msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(view_release_button)
    msg.exec()
    if msg.clickedButton() == view_release_button:
        QDesktopServices.openUrl(QUrl(release_url))

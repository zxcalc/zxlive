from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

from PySide6.QtCore import QFile, QIODevice, QTextStream
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QLineEdit, QMessageBox,
                               QPushButton, QTextEdit, QWidget)
from pyzx import Circuit, extract_circuit

from .common import GraphT
from .custom_rule import CustomRule, check_rule
from .proof import ProofModel

if TYPE_CHECKING:
    from .mainwindow import MainWindow


class FileFormat(Enum):
    """Supported formats for importing/exporting diagrams."""

    All = "zxg *.json *.qasm *.tikz *.zxp *.zxr", "All Supported Formats"
    QGraph = "zxg", "QGraph"  # "file extension", "format name"
    QASM = "qasm", "QASM"
    TikZ = "tikz", "TikZ"
    Json = "json", "JSON"
    ZXProof = "zxp", "ZXProof"
    ZXRule = "zxr", "ZXRule"
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

def show_error_msg(title: str, description: Optional[str] = None) -> None:
    """Displays an error message box."""
    msg = QMessageBox()
    msg.setText(title)
    msg.setIcon(QMessageBox.Icon.Critical)
    if description is not None:
        msg.setInformativeText(description)
    msg.exec()

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

    file = QFile(file_path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        show_error_msg("Could not open file")
        return None
    stream = QTextStream(file)
    data = stream.readAll()
    file.close()

    selected_format = next(f for f in FileFormat if f.filter == selected_filter)
    if selected_format == FileFormat.All:
        ext = file_path.split(".")[-1]
        selected_format = next(f for f in FileFormat if f.extension == ext)

    # TODO: This would be nicer with match statements...
    try:
        if selected_format == FileFormat.ZXProof:
            return ImportProofOutput(selected_format, file_path, ProofModel.from_json(data))
        elif selected_format == FileFormat.ZXRule:
            return ImportRuleOutput(selected_format, file_path, CustomRule.from_json(data))
        elif selected_format in (FileFormat.QGraph, FileFormat.Json):
            return ImportGraphOutput(selected_format, file_path, GraphT.from_json(data))  # type: ignore # This is something that needs to be better annotated in PyZX
        elif selected_format == FileFormat.QASM:
            return ImportGraphOutput(selected_format, file_path, Circuit.from_qasm(data).to_graph()) # type: ignore
        elif selected_format == FileFormat.TikZ:
            return ImportGraphOutput(selected_format, file_path, GraphT.from_tikz(data))  # type: ignore
        else:
            assert selected_format == FileFormat.All
            try:
                circ = Circuit.load(file_path)
                return ImportGraphOutput(FileFormat.QASM, file_path, circ.to_graph())  # type: ignore
            except TypeError:
                try:
                    return ImportGraphOutput(FileFormat.QGraph, file_path, GraphT.from_json(data))  # type: ignore
                except Exception:
                    try:
                        return ImportGraphOutput(FileFormat.TikZ, file_path, GraphT.from_tikz(data))  # type: ignore
                    except:
                        show_error_msg(f"Failed to import {selected_format.name} file", "Couldn't determine filetype.")
                        return None

    except Exception as e:
        show_error_msg(f"Failed to import {selected_format.name} file", str(e))
        return None

def write_to_file(file_path: str, data: str) -> bool:
    file = QFile(file_path)
    if not file.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Text):
        show_error_msg("Could not write to file")
        return False
    out = QTextStream(file)
    out << data
    file.close()
    return True


def get_file_path_and_format(parent: QWidget, filter: str) -> Optional[Tuple[str, FileFormat]]:
    file_path, selected_filter = QFileDialog.getSaveFileName(
        parent=parent,
        caption="Save File",
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
            show_error_msg("Unable to determine file format.")
            return None

    # Add file extension if it's not already there
    if file_path.split(".")[-1].lower() != selected_format.extension:
        file_path += "." + selected_format.extension

    return file_path, selected_format

def export_diagram_dialog(graph: GraphT, parent: QWidget) -> Optional[Tuple[str, FileFormat]]:
    file_path_and_format = get_file_path_and_format(parent, ";;".join([f.filter for f in FileFormat if f != FileFormat.ZXProof]))
    if file_path_and_format is None or not file_path_and_format[0]:
        return None
    file_path, selected_format = file_path_and_format

    if selected_format in (FileFormat.QGraph, FileFormat.Json):
        data = graph.to_json()
    elif selected_format == FileFormat.QASM:
        try:
            circuit = extract_circuit(graph)
        except Exception as e:
            show_error_msg("Failed to convert the diagram to a circuit", str(e))
            return None
        data = circuit.to_qasm()
    else:
        assert selected_format == FileFormat.TikZ
        data = graph.to_tikz()

    if not write_to_file(file_path, data):
        return None

    return file_path, selected_format

def export_proof_dialog(proof_model: ProofModel, parent: QWidget) -> Optional[Tuple[str, FileFormat]]:
    file_path_and_format = get_file_path_and_format(parent, FileFormat.ZXProof.filter)
    if file_path_and_format is None or not file_path_and_format[0]:
        return None
    file_path, selected_format = file_path_and_format
    data = proof_model.to_json()
    if not write_to_file(file_path, data):
        return None
    return file_path, selected_format

def export_rule_dialog(rule: CustomRule, parent: QWidget) -> Optional[Tuple[str, FileFormat]]:
    file_path_and_format = get_file_path_and_format(parent, FileFormat.ZXRule.filter)
    if file_path_and_format is None or not file_path_and_format[0]:
        return None
    file_path, selected_format = file_path_and_format
    data = rule.to_json()
    if not write_to_file(file_path, data):
        return None
    return file_path, selected_format

def get_lemma_name_and_description(parent: MainWindow) -> tuple[Optional[str], Optional[str]]:
    dialog = QDialog()
    parent.rewrite_form = QFormLayout(dialog)
    name = QLineEdit()
    parent.rewrite_form.addRow("Name", name)
    description = QTextEdit()
    parent.rewrite_form.addRow("Description", description)
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    parent.rewrite_form.addRow(button_box)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return name.text(), description.toPlainText()
    return None, None

def create_new_rewrite(parent: MainWindow) -> None:
    dialog = QDialog()
    parent.rewrite_form = QFormLayout(dialog)
    name = QLineEdit()
    parent.rewrite_form.addRow("Name", name)
    description = QTextEdit()
    parent.rewrite_form.addRow("Description", description)
    left_button = QPushButton("Left-hand side of the rule")
    right_button = QPushButton("Right-hand side of the rule")
    parent.left_graph = None
    parent.right_graph = None

    def get_file(self: MainWindow, button: QPushButton, side: str) -> None:
        out = import_diagram_dialog(self)
        if out is not None and isinstance(out, ImportGraphOutput):
            button.setText(out.file_path)
            if side == "left":
                self.left_graph = out.g
            else:
                self.right_graph = out.g

    left_button.clicked.connect(lambda: get_file(parent, left_button, "left"))
    right_button.clicked.connect(lambda: get_file(parent, right_button, "right"))
    parent.rewrite_form.addRow(left_button)
    parent.rewrite_form.addRow(right_button)
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    parent.rewrite_form.addRow(button_box)
    def add_rewrite() -> None:
        if parent.left_graph is None or parent.right_graph is None or \
            name.text() == "" or description.toPlainText() == "":
            return
        rule = CustomRule(parent.left_graph, parent.right_graph, name.text(), description.toPlainText())
        check_rule(rule, show_error=True)
        if export_rule_dialog(rule, parent):
            dialog.accept()
    button_box.accepted.connect(add_rewrite)
    button_box.rejected.connect(dialog.reject)
    if not dialog.exec(): return

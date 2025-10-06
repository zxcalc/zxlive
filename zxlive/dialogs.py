from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QFile, QIODevice, QTextStream
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QLineEdit, QMessageBox,
                               QPushButton, QTextEdit, QWidget, QInputDialog,
                               QCheckBox, QVBoxLayout, QLabel)
from pyzx import Circuit, extract_circuit
from pyzx.utils import VertexType

from .common import GraphT, VT, from_tikz
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
    msg = QMessageBox(parent) #Set the parent of the QMessageBox
    msg.setText(title)
    msg.setIcon(QMessageBox.Icon.Critical)
    if description is not None:
        msg.setInformativeText(description)
    msg.exec()


def show_tikz_error_with_options(error_message: str, parent: Optional[QWidget] = None) -> Optional[dict[str, bool]]:
    """Shows a TikZ import error and offers retry options.
    
    Returns a dictionary of options to use for retrying, or None if user cancels.
    Options returned: ignore_nonzx, fuse_overlap, ignore_overlap_warning
    """
    msg = QMessageBox(parent)
    msg.setWindowTitle("TikZ Import Error")
    msg.setText("Failed to import TikZ diagram")
    msg.setInformativeText(f"Error: {error_message}\n\nWould you like to try again with error handling options?")
    msg.setIcon(QMessageBox.Icon.Warning)
    
    # Add custom buttons
    retry_button = msg.addButton("Retry with options...", QMessageBox.ButtonRole.AcceptRole)
    cancel_button = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(retry_button)
    
    msg.exec()
    
    if msg.clickedButton() == cancel_button:
        return None
    
    # Show dialog with options
    dialog = QDialog(parent)
    dialog.setWindowTitle("TikZ Import Options")
    layout = QFormLayout()
    
    # Create checkboxes for different error handling options
    from PySide6.QtWidgets import QCheckBox, QVBoxLayout, QLabel
    
    info_label = QLabel("Select options to ignore certain errors during import:")
    layout.addRow(info_label)
    
    ignore_nonzx_cb = QCheckBox()
    ignore_nonzx_cb.setChecked(True)
    ignore_nonzx_cb.setToolTip("Ignore nodes/edges with unknown styles or invalid definitions")
    layout.addRow("Ignore invalid styles:", ignore_nonzx_cb)
    
    fuse_overlap_cb = QCheckBox()
    fuse_overlap_cb.setChecked(True)
    fuse_overlap_cb.setToolTip("Merge vertices that have the same position")
    layout.addRow("Merge overlapping vertices:", fuse_overlap_cb)
    
    ignore_warning_cb = QCheckBox()
    ignore_warning_cb.setChecked(True)
    ignore_warning_cb.setToolTip("Don't raise warnings about overlapping vertices")
    layout.addRow("Ignore overlap warnings:", ignore_warning_cb)
    
    # Add buttons
    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    layout.addRow(button_box)
    
    dialog.setLayout(layout)
    
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return {
            'ignore_nonzx': ignore_nonzx_cb.isChecked(),
            'fuse_overlap': fuse_overlap_cb.isChecked(),
            'ignore_overlap_warning': ignore_warning_cb.isChecked()
        }
    
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


def import_diagram_from_file(file_path: str, selected_filter: str = FileFormat.All.filter, parent: Optional[QWidget] = None) -> \
        Optional[ImportGraphOutput | ImportProofOutput | ImportRuleOutput]:
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
            if TYPE_CHECKING: assert isinstance(g, GraphT)
            g.set_auto_simplify(False)
            return ImportGraphOutput(selected_format, file_path, g)  # type: ignore # This is something that needs to be better annotated in PyZX
        elif selected_format == FileFormat.QASM:
            g = Circuit.from_qasm(data).to_graph(zh=True,backend='multigraph') # type: ignore # We know the return type is Multigraph, but mypy doesn't
            if TYPE_CHECKING: assert isinstance(g, GraphT)
            g.set_auto_simplify(False)
            return ImportGraphOutput(selected_format, file_path, ) # type: ignore
        elif selected_format == FileFormat.TikZ:
            g = from_tikz(data, parent=parent)  # type: ignore[assignment]
            if g is None:
                return None
            if TYPE_CHECKING: assert isinstance(g, GraphT)
            g.set_auto_simplify(False)
            return ImportGraphOutput(selected_format, file_path, g)  # type: ignore
        else:
            assert selected_format == FileFormat.All
            try:
                g = Circuit.load(file_path).to_graph(zh=True,backend='multigraph') # type: ignore # We know the return type is Multigraph, but mypy doesn't
                if TYPE_CHECKING: assert isinstance(g, GraphT)
                g.set_auto_simplify(False)
                return ImportGraphOutput(FileFormat.QASM, file_path, g)  # type: ignore
            except TypeError:
                try:
                    g = GraphT.from_json(data)
                    if TYPE_CHECKING: assert isinstance(g, GraphT)
                    g.set_auto_simplify(False)
                    return ImportGraphOutput(FileFormat.QGraph, file_path, g)  # type: ignore
                except Exception:
                    g = from_tikz(data, parent=parent)  # type: ignore[assignment]
                    if g is None:
                        show_error_msg(f"Failed to import {selected_format.name} file",
                                       f"Couldn't determine filetype: {file_path}.", parent=parent)
                        return None
                    if TYPE_CHECKING: assert isinstance(g, GraphT)
                    g.set_auto_simplify(False)
                    return ImportGraphOutput(FileFormat.TikZ, file_path, g)  # type: ignore

    except Exception as e:
        show_error_msg(f"Failed to import {selected_format.name} file: {file_path}", str(e), parent=parent)
        return None

def write_to_file(file_path: str, data: str, parent: QWidget) -> bool:
    file = QFile(file_path)
    if not file.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Text):
        show_error_msg("Could not write to file", parent=parent)
        return False
    out = QTextStream(file)
    out << data
    file.close()
    return True


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

    # Add file extension if it's not already there
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

def save_rule_dialog(rule: CustomRule, parent: QWidget, filename: str ="") -> Optional[tuple[str, FileFormat]]:
    return _save_rule_or_proof_dialog(rule.to_json(), parent, FileFormat.ZXRule.filter, filename)

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
    if not dialog.exec(): return

def update_dummy_vertex_text(parent: QWidget, graph: GraphT, v: VT) -> Optional[GraphT]:
    """Prompt the user for text and return a new graph with the text stored in the vertex's vdata under key 'text'.
    If the user cancels, return None. Otherwise, return the new graph with the updated vdata.
    """
    if graph.type(v) != VertexType.DUMMY:
        show_error_msg("Invalid Vertex Type", "This function can only be used on dummy vertices.", parent=parent)
        return None
    current_text = graph.vdata(v, 'text', '')
    input_, ok = QInputDialog.getText(parent, "Set Text", "Enter text for dummy node:", text=current_text)
    if not ok:
        return None
    new_g = copy.deepcopy(graph)
    new_g.set_vdata(v, 'text', input_)
    return new_g

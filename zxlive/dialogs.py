from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass

from PySide6.QtCore import QFile, QIODevice, QTextStream
from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox
from pyzx import Circuit, extract_circuit

from zxlive.proof import ProofModel

from .common import VT,ET, GraphT, Graph


class FileFormat(Enum):
    """Supported formats for importing/exporting diagrams."""

    All = "zxg *.json *.qasm *.tikz", "All Supported Formats"
    QGraph = "zxg", "QGraph"  # "file extension", "format name"
    QASM = "qasm", "QASM"
    TikZ = "tikz", "TikZ"
    Json = "json", "JSON"

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
class ImportOutput:
    file_type: FileFormat
    file_path: str
    g: GraphT


def show_error_msg(title: str, description: Optional[str] = None) -> None:
    """Displays an error message box."""
    msg = QMessageBox(icon=QMessageBox.Icon.Critical, text=title)
    if description is not None:
        msg.setInformativeText(description)
    msg.exec()


def import_diagram_dialog(parent: QWidget) -> Optional[ImportOutput]:
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
    selected_format = next(f for f in FileFormat if f.filter == selected_filter)

    file = QFile(file_path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        show_error_msg("Could not open file")
        return None
    stream = QTextStream(file)
    data = stream.readAll()
    file.close()

    # TODO: This would be nicer with match statements...
    try:
        if selected_format in (FileFormat.QGraph, FileFormat.Json):
            return ImportOutput(selected_format, file_path, Graph.from_json(data))  # type: ignore # This is something that needs to be better annotated in PyZX
        elif selected_format == FileFormat.QASM:
            return ImportOutput(selected_format, file_path, Circuit.from_qasm(data).to_graph()) # type: ignore
        elif selected_format == FileFormat.TikZ:
            return ImportOutput(selected_format, file_path, Graph.from_tikz(data))  # type: ignore
        else:
            assert selected_format == FileFormat.All
            try:
                circ = Circuit.load(file_path)
                return ImportOutput(FileFormat.QASM, file_path, circ.to_graph())  # type: ignore
            except TypeError:
                try:
                    return ImportOutput(FileFormat.QGraph, file_path, Graph.from_json(data))  # type: ignore
                except Exception:
                    try:
                        return ImportOutput(FileFormat.TikZ, file_path, Graph.from_tikz(data))  # type: ignore
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

    ext = file_path.split(".")[-1]
    selected_format = next(f for f in FileFormat if f.filter == selected_filter)
    if selected_format == FileFormat.All:
        selected_format = next(f for f in FileFormat if f.extension == ext)

    # Add file extension if it's not already there
    if file_path.split(".")[-1].lower() != selected_format.extension:
        file_path += "." + selected_format.extension

    return file_path, selected_format

def export_diagram_dialog(graph: GraphT, parent: QWidget) -> Optional[Tuple[str, FileFormat]]:
    selected_format = None
    file_path, selected_format = get_file_path_and_format(parent, ";;".join([f.filter for f in FileFormat]))
    if not file_path:
        return None

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
    file_path, selected_format = get_file_path_and_format(parent, FileFormat.Json.filter)
    if not file_path:
        return None
    data = proof_model.to_json()
    if not write_to_file(file_path, data):
        return None
    return file_path, selected_format

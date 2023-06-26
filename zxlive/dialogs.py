from enum import Enum
from typing import Optional, Tuple

from PySide6.QtCore import QFile, QFileInfo, QIODevice, QTextStream
from PySide6.QtWidgets import QWidget, QFileDialog, QMessageBox
from pyzx import Graph, Circuit, extract_circuit
from pyzx.graph.base import BaseGraph, VT, ET


class FileFormat(Enum):
    """Supported formats for importing/exporting diagrams."""

    QGraph = "zxg", "QGraph"  # "file extension", "format name"
    QASM = "quasm", "QASM"
    TikZ = "tikz", "TikZ"
    Json = "json", "JSON"
    All = "*", "All"

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]  # Use extension as `_value_`
        return obj

    def __init__(self, _extension: str, name: str):
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


def show_error_msg(title: str, description: Optional[str] = None) -> None:
    """Displays an error message box."""
    msg = QMessageBox(icon=QMessageBox.Critical, text=title)
    if description is not None:
        msg.setInformativeText(description)
    msg.exec()


def import_diagram_dialog(parent: QWidget) -> Optional[Tuple[BaseGraph[VT, ET],str]]:
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
    if not file.open(QIODevice.ReadOnly | QIODevice.Text):
        show_error_msg("Could not open file")
        return None
    stream = QTextStream(file)
    data = stream.readAll()
    file.close()
    name = QFileInfo(file_path).baseName()

    # TODO: This would be nicer with match statements...
    try:
        if selected_format in (FileFormat.QGraph, FileFormat.Json):
            return Graph.from_json(data), name
        elif selected_format == FileFormat.QASM:
            return Circuit.from_qasm(data).to_graph(), name
        elif selected_format == FileFormat.TikZ:
            return Graph.from_tikz(data), name
        else:
            assert selected_format == FileFormat.All
            try:
                circ = Circuit.load(file_path)
                return circ.to_graph(), name
            except TypeError:
                try:
                    return Graph.from_json(data), name
                except Exception:
                    try:
                        return Graph.from_tikz(data), name
                    except:
                        show_error_msg(f"Failed to import {selected_format.name} file", "Couldn't determine filetype.")
                        return None

    except Exception as e:
        show_error_msg(f"Failed to import {selected_format.name} file", str(e))
        return None


def export_diagram_dialog(graph: BaseGraph[VT, ET], parent: QWidget) -> bool:
    """Shows a dialog to export the given diagram to disk.

    Returns `True` if the diagram was successfully saved."""
    file_path, selected_filter = QFileDialog.getSaveFileName(
        parent=parent,
        caption="Save File",
        filter=";;".join([f.filter for f in FileFormat]),
    )
    if selected_filter == "":
        # This happens if the user clicks on cancel
        return False
    selected_format = next(f for f in FileFormat if f.filter == selected_filter)

    # Add file extension if it's not already there
    if file_path.split(".")[-1].lower() != selected_format.extension:
        file_path += "." + selected_format.extension

    if selected_format in (FileFormat.QGraph, FileFormat.Json):
        data = graph.to_json()
    elif selected_format == FileFormat.QASM:
        try:
            circuit = extract_circuit(graph)
        except Exception as e:
            show_error_msg("Failed to convert the diagram to a circuit", str(e))
            return False
        data = circuit.to_qasm()
    else:
        assert selected_format == FileFormat.TikZ
        data = graph.to_tikz()

    file = QFile(file_path)
    if not file.open(QIODevice.WriteOnly | QIODevice.Text):
        show_error_msg("Could not write to file")
        return False
    out = QTextStream(file)
    out << data
    file.close()
    return True

```python
# tutorial_overlay.py
#
# Standalone walkthrough/tutorial system for a ZX-calculus style UI app.
# Designed to avoid bloating the main application code.
#
# PyQt5 implementation example.

from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QApplication,
)
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen


class TutorialStep:
    def __init__(self, title, text, target_widget=None):
        self.title = title
        self.text = text
        self.target_widget = target_widget


class TutorialOverlay(QWidget):

    def __init__(self, parent=None, steps=None):
        super().__init__(parent)

        self.steps = steps or []
        self.current_step = 0

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self.resize(parent.size())

        self.panel = QWidget(self)
        self.panel.setStyleSheet("""
            background-color: white;
            border-radius: 10px;
            padding: 12px;
        """)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.text_label = QLabel()
        self.text_label.setWordWrap(True)

        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.skip_button = QPushButton("Skip")

        self.prev_button.clicked.connect(self.previous_step)
        self.next_button.clicked.connect(self.next_step)
        self.skip_button.clicked.connect(self.close)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.next_button)
        button_layout.addStretch()
        button_layout.addWidget(self.skip_button)

        layout = QVBoxLayout()
        layout.addWidget(self.title_label)
        layout.addWidget(self.text_label)
        layout.addLayout(button_layout)

        self.panel.setLayout(layout)
        self.panel.resize(360, 180)

        self.show_step()

    def show_step(self):

        if not self.steps:
            return

        step = self.steps[self.current_step]

        self.title_label.setText(step.title)
        self.text_label.setText(step.text)

        self.prev_button.setEnabled(self.current_step > 0)

        if self.current_step == len(self.steps) - 1:
            self.next_button.setText("Finish")
        else:
            self.next_button.setText("Next")

        self.position_panel(step)

        self.update()

    def position_panel(self, step):

        if step.target_widget:
            widget_geom = step.target_widget.geometry()

            x = widget_geom.right() + 20
            y = widget_geom.top()

            if x + self.panel.width() > self.width():
                x = widget_geom.left() - self.panel.width() - 20

            self.panel.move(max(20, x), max(20, y))

        else:
            self.panel.move(50, 50)

    def next_step(self):

        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self.show_step()
        else:
            self.close()

    def previous_step(self):

        if self.current_step > 0:
            self.current_step -= 1
            self.show_step()

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)

        overlay_color = QColor(0, 0, 0, 180)
        painter.fillRect(self.rect(), overlay_color)

        step = self.steps[self.current_step]

        if step.target_widget:

            rect = step.target_widget.geometry()

            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect.adjusted(-5, -5, 5, 5), Qt.transparent)

            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            pen = QPen(QColor(255, 255, 0), 3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(-5, -5, 5, 5))


def create_main_tutorial(main_window):

    return [

        TutorialStep(
            title="Welcome",
            text="This tutorial will guide you through the main ZX editor features."
        ),

        TutorialStep(
            title="Add Vertex Tool",
            text="Use Add Vertex to place Z or X spiders onto the canvas.",
            target_widget=main_window.add_vertex_button
        ),

        TutorialStep(
            title="Add Edge Tool",
            text="Use Add Edge to connect spiders and build ZX diagrams.",
            target_widget=main_window.add_edge_button
        ),

        TutorialStep(
            title="Sidebar",
            text="The sidebar contains graph controls, rewrite tools, and proof settings.",
            target_widget=main_window.sidebar
        ),

        TutorialStep(
            title="Adding Phases",
            text="Double-click a vertex to add or edit a phase value.",
            target_widget=main_window.canvas
        ),

        TutorialStep(
            title="Proof Mode",
            text="Proof mode lets you formally verify rewrite sequences.",
            target_widget=main_window.proof_mode_button
        ),

        TutorialStep(
            title="Applying Rewrites",
            text="Select a rewrite rule and click highlighted matches to simplify the graph.",
            target_widget=main_window.rewrite_panel
        ),

        TutorialStep(
            title="Magic Wand Tool",
            text="The magic wand attempts automatic simplifications and rewrite suggestions.",
            target_widget=main_window.magic_wand_button
        ),

        TutorialStep(
            title="Done",
            text="You are now ready to start using the ZX editor."
        )
    ]


# Example usage:
#
# tutorial = TutorialOverlay(
#     parent=main_window,
#     steps=create_main_tutorial(main_window)
# )
#
# tutorial.show()


# ---------------------------------------------------------
# Proof-mode-specific tutorial section
# ---------------------------------------------------------

def create_proof_mode_tutorial(main_window):

    return [

        TutorialStep(
            title="Proof Mode",
            text="You have entered proof mode."
        ),

        TutorialStep(
            title="Rewrite Tracking",
            text="Each rewrite is tracked as a formal proof step.",
            target_widget=main_window.proof_panel
        ),

        TutorialStep(
            title="Proof History",
            text="Use the proof history sidebar to inspect previous transformations.",
            target_widget=main_window.history_sidebar
        ),

        TutorialStep(
            title="Verification",
            text="Proof mode ensures each rewrite preserves diagram equivalence."
        )
    ]


# ---------------------------------------------------------
# Replay tutorial from Help menu
# ---------------------------------------------------------

def replay_tutorial(main_window):

    tutorial = TutorialOverlay(
        parent=main_window,
        steps=create_main_tutorial(main_window)
    )

    tutorial.show()
```

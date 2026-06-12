from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class TutorialStep:
    title: str
    description: str
    target_widget: Optional[str] = None
    action: Optional[Callable] = None
    proof_mode_only: bool = False


MAIN_TUTORIAL = [
    TutorialStep(
        title="Welcome to ZXLive",
        description=(
            "ZXLive is an interactive editor for ZX-calculus diagrams.\n\n"
            "This tutorial will guide you through the core tools."
        )
    ),

    TutorialStep(
        title="Add Vertex Tool",
        description=(
            "Use the Add Vertex tool to place spiders into the graph."
        ),
        target_widget="toolbar_add_vertex"
    ),

    TutorialStep(
        title="Add Edge Tool",
        description=(
            "Use Add Edge to connect spiders together."
        ),
        target_widget="toolbar_add_edge"
    ),

    TutorialStep(
        title="Phases",
        description=(
            "Double-click a spider to add or edit a phase."
        )
    ),

    TutorialStep(
        title="Magic Wand",
        description=(
            "The magic wand automatically simplifies graphs "
            "using rewrite rules."
        ),
        target_widget="toolbar_magic_wand"
    ),

    TutorialStep(
        title="Rewrite Rules",
        description=(
            "ZXLive supports many rewrite operations like "
            "spider fusion and bialgebra."
        )
    ),

    TutorialStep(
        title="Proof Mode",
        description=(
            "Proof mode lets you build derivations step-by-step."
        ),
        target_widget="toolbar_proof_mode"
    ),
]

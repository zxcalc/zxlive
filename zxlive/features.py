from __future__ import annotations

from typing import TypedDict

from .common import get_settings_value, set_settings_value
from .settings import feature_defaults


class FeatureData(TypedDict):
    id: str
    label: str
    tooltip: str


FAULT_EQUIVALENCE = "feature/fault-equivalence"
ZH_CALCULUS = "feature/zh-calculus"
ZW_CALCULUS = "feature/zw-calculus"
PAULI_WEBS = "feature/pauli-webs"

FEATURES: list[FeatureData] = [
    {
        "id": FAULT_EQUIVALENCE,
        "label": "Fault-equivalent rewrites",
        "tooltip": "Show the fault-equivalent rewrite mode in the proof panel. "
                   "These rewrites preserve the fault tolerance of a diagram.",
    },
    {
        "id": ZH_CALCULUS,
        "label": "ZH-calculus (H-boxes)",
        "tooltip": "Show H-box vertices in the editor sidebar.",
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

from __future__ import annotations

from typing import Dict, Any, TypedDict

import pyzx
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QTabWidget

from .common import get_settings_value, SCALE


class ColorScheme(TypedDict):
    id: str
    label: str
    z_spider: QColor
    z_spider_pressed: QColor
    x_spider: QColor
    x_spider_pressed: QColor
    hadamard: QColor
    hadamard_pressed: QColor
    boundary: QColor
    boundary_pressed: QColor
    w_input: QColor
    w_input_pressed: QColor
    w_output: QColor
    w_output_pressed: QColor
    outline: QColor
    dummy: QColor
    dummy_pressed: QColor
    edge: QColor
    dummy_edge: QColor


general_defaults: dict[str, str | QTabWidget.TabPosition | int | bool] = {
    "path/custom-rules": "rules/",
    "color-scheme": "modern-red-green",
    "tab-bar-location": QTabWidget.TabPosition.North,
    "snap-granularity": '4',
    "input-circuit-format": 'openqasm',
    "previews-show": True,
    "sparkle-mode": True,
    'sound-effects': False,
    "matrix/precision": 4,
    "dark-mode": False,
    "auto-save": False,
}

font_defaults: dict[str, str | int | None] = {
    "font/size": 11,
    "font/family": "Arial",
}

tikz_export_defaults: dict[str, str] = {
    "tikz/boundary-export": pyzx.settings.tikz_classes['boundary'],
    "tikz/Z-spider-export": pyzx.settings.tikz_classes['Z'],
    "tikz/X-spider-export": pyzx.settings.tikz_classes['X'],
    "tikz/Z-phase-export": pyzx.settings.tikz_classes['Z phase'],
    "tikz/X-phase-export": pyzx.settings.tikz_classes['X phase'],
    "tikz/z-box-export": pyzx.settings.tikz_classes['Z box'],
    "tikz/Hadamard-export": pyzx.settings.tikz_classes['H'],
    "tikz/w-output-export": pyzx.settings.tikz_classes['W'],
    "tikz/w-input-export": pyzx.settings.tikz_classes['W input'],
    "tikz/dummy-export": pyzx.settings.tikz_classes['dummy'],
    "tikz/edge-export": pyzx.settings.tikz_classes['edge'],
    "tikz/edge-H-export": pyzx.settings.tikz_classes['H-edge'],
    "tikz/edge-W-export": pyzx.settings.tikz_classes['W-io-edge'],
}

tikz_import_defaults: dict[str, str] = {
    "tikz/boundary-import": ", ".join(pyzx.tikz.synonyms_boundary),
    "tikz/Z-spider-import": ", ".join(pyzx.tikz.synonyms_z),
    "tikz/X-spider-import": ", ".join(pyzx.tikz.synonyms_x),
    "tikz/Hadamard-import": ", ".join(pyzx.tikz.synonyms_hadamard),
    "tikz/w-input-import": ", ".join(pyzx.tikz.synonyms_w_input),
    "tikz/w-output-import": ", ".join(pyzx.tikz.synonyms_w_output),
    "tikz/z-box-import": ", ".join(pyzx.tikz.synonyms_z_box),
    "tikz/dummy-import": ", ".join(pyzx.tikz.synonyms_dummy),
    "tikz/edge-import": ", ".join(pyzx.tikz.synonyms_edge),
    "tikz/edge-H-import": ", ".join(pyzx.tikz.synonyms_hedge),
    "tikz/edge-W-import": ", ".join(pyzx.tikz.synonyms_wedge),
}

tikz_layout_defaults: dict[str, float] = {
    "tikz/layout/hspace": 2.0,
    "tikz/layout/vspace": 2.0,
    "tikz/layout/max-width": 10.0,
}

tikz_names_defaults: dict[str, str] = {
    "tikz/names/fuse spiders": "f",
    "tikz/names/bialgebra": "b",
    "tikz/names/change color to Z": "cc",
    "tikz/names/change color to X": "cc",
    "tikz/names/remove identity": "id",
    "tikz/names/Add Z identity": "id",
    "tikz/names/copy 0/pi spider": "cp",
    "tikz/names/push Pauli": "pi",
    "tikz/names/decompose hadamard": "eu",
}

defaults = general_defaults | font_defaults | tikz_export_defaults | \
           tikz_import_defaults | tikz_layout_defaults | tikz_names_defaults


modern_red_green: ColorScheme = {
    "id": 'modern-red-green',
    "label": "Modern Red & Green",
    "z_spider": QColor("#ccffcc"),
    "z_spider_pressed": QColor("#64BC90"),
    "x_spider": QColor("#ff8888"),
    "x_spider_pressed": QColor("#bb0f0f"),
    "hadamard": QColor("#ffff00"),
    "hadamard_pressed": QColor("#f1c232"),
    "boundary": QColor("#000000"),
    "boundary_pressed": QColor("#444444"),
    "w_input": QColor("#000000"),
    "w_input_pressed": QColor("#444444"),
    "w_output": QColor("#000000"),
    "w_output_pressed": QColor("#444444"),
    "outline": QColor("#000000"),
    "dummy": QColor("#B6B6B6"),
    "dummy_pressed": QColor("#808080"),
    "edge": QColor("#000000"),
    "dummy_edge": QColor("#808080"),
}

classic_red_green: ColorScheme = {
    **modern_red_green,
    "id": "classic-red-green",
    "label": "Classic Red & Green",
    "z_spider": QColor("#00ff00"),
    "z_spider_pressed": QColor("#00dd00"),
    "x_spider": QColor("#ff0d00"),
    "x_spider_pressed": QColor("#dd0b00"),
}

white_gray: ColorScheme = {
    **modern_red_green,
    "id": 'white-grey',
    "label": "Dodo book White & Grey",
    "z_spider": QColor("#ffffff"),
    "z_spider_pressed": QColor("#eeeeee"),
    "x_spider": QColor("#b4b4b4"),
    "x_spider_pressed": QColor("#a0a0a0"),
    "hadamard": QColor("#ffffff"),
    "hadamard_pressed": QColor("#dddddd"),
}

gidney: ColorScheme = {
    **white_gray,
    "id": 'gidney',
    "label": "Gidney's Black & White",
    "z_spider": QColor("#000000"),
    "z_spider_pressed": QColor("#222222"),
    "x_spider": QColor("#ffffff"),
    "x_spider_pressed": QColor("#dddddd"),
}

color_schemes = {
    scheme["id"]: scheme for scheme in [modern_red_green, classic_red_green, white_gray, gidney]
}

color_scheme_ids = list(color_schemes.keys())


def load_tikz_classes() -> dict[str, str]:
    return {
        'boundary': str(settings.value('tikz/boundary-export', pyzx.settings.tikz_classes['boundary'])),
        'Z': str(settings.value('tikz/Z-spider-export', pyzx.settings.tikz_classes['Z'])),
        'X': str(settings.value('tikz/X-spider-export', pyzx.settings.tikz_classes['X'])),
        'Z phase': str(settings.value('tikz/Z-phase-export', pyzx.settings.tikz_classes['Z phase'])),
        'X phase': str(settings.value('tikz/X-phase-export', pyzx.settings.tikz_classes['X phase'])),
        'Z box': str(settings.value('tikz/Z-box-export', pyzx.settings.tikz_classes['Z box'])),
        'H': str(settings.value('tikz/Hadamard-export', pyzx.settings.tikz_classes['H'])),
        'W': str(settings.value('tikz/W-output-export', pyzx.settings.tikz_classes['W'])),
        'W input': str(settings.value('tikz/W-input-export', pyzx.settings.tikz_classes['W input'])),
        'dummy': str(settings.value('tikz/dummy-export', pyzx.settings.tikz_classes['dummy'])),
        'edge': str(settings.value('tikz/edge-export', pyzx.settings.tikz_classes['edge'])),
        'H-edge': str(settings.value('tikz/edge-H-export', pyzx.settings.tikz_classes['H-edge'])),
        'W-io-edge': str(settings.value('tikz/edge-W-export', pyzx.settings.tikz_classes['W-io-edge'])),
    }


def refresh_pyzx_tikz_settings() -> None:
    def _get_synonyms(key: str, default: list[str]) -> list[str]:
        val: object = settings.value(key)
        if not val:
            return default
        return [s.strip().lower() for s in str(val).split(',')]

    pyzx.settings.tikz_classes = load_tikz_classes()
    pyzx.tikz.synonyms_boundary = _get_synonyms('tikz/boundary-import', pyzx.tikz.synonyms_boundary)
    pyzx.tikz.synonyms_z = _get_synonyms('tikz/Z-spider-import', pyzx.tikz.synonyms_z)
    pyzx.tikz.synonyms_x = _get_synonyms('tikz/X-spider-import', pyzx.tikz.synonyms_x)
    pyzx.tikz.synonyms_hadamard = _get_synonyms('tikz/Hadamard-import', pyzx.tikz.synonyms_hadamard)
    pyzx.tikz.synonyms_w_input = _get_synonyms('tikz/W-input-import', pyzx.tikz.synonyms_w_input)
    pyzx.tikz.synonyms_w_output = _get_synonyms('tikz/W-output-import', pyzx.tikz.synonyms_w_output)
    pyzx.tikz.synonyms_z_box = _get_synonyms('tikz/Z-box-import', pyzx.tikz.synonyms_z_box)
    pyzx.tikz.synonyms_dummy = _get_synonyms('tikz/dummy-import', pyzx.tikz.synonyms_dummy)
    pyzx.tikz.synonyms_edge = _get_synonyms('tikz/edge-import', pyzx.tikz.synonyms_edge)
    pyzx.tikz.synonyms_hedge = _get_synonyms('tikz/edge-H-import', pyzx.tikz.synonyms_hedge)
    pyzx.tikz.synonyms_wedge = _get_synonyms('tikz/edge-W-import', pyzx.tikz.synonyms_wedge)


class DisplaySettings:
    SNAP_DIVISION = 4  # Should be an integer dividing SCALE

    def __init__(self) -> None:
        self.colors = color_schemes[str(settings.value("color-scheme"))]
        self.update()

    def set_color_scheme(self, scheme_id: str) -> None:
        self.colors = color_schemes[scheme_id]

    def update(self) -> None:
        self.SNAP_DIVISION = int(get_settings_value("snap-granularity", str))
        self.font = QFont(
            get_settings_value("font/family", str),
            get_settings_value("font/size", int)
        )
        self.SNAP = SCALE / self.SNAP_DIVISION

    @property
    def previews_show(self) -> bool:
        return get_settings_value("previews-show", bool)

    @previews_show.setter
    def previews_show(self, value: bool) -> None:
        settings.setValue("previews-show", value)

    @property
    def dark_mode(self) -> bool:
        return get_settings_value("dark-mode", bool)

    @dark_mode.setter
    def dark_mode(self, value: bool) -> None:
        settings.setValue("dark-mode", value)

    @property
    def effective_colors(self) -> dict[str, QColor]:
        # Return a color scheme adapted for dark mode (subtle adjustment), no change for light mode
        from PySide6.QtGui import QColor
        def adjust_for_dark(color: QColor) -> QColor:
            if not isinstance(color, QColor):
                raise ValueError(f"Expected QColor, got {type(color)}")
            h: int = color.hslHue()
            s: int = color.hslSaturation()
            l: int = color.lightness()
            a: int = color.alpha()            # Make colors slightly darker and less saturated for dark mode
            l = int(l * 0.6)
            s = int(s * 0.4)
            return QColor.fromHsl(h, s, l, a)
        base: dict[str, QColor] = {k: v for k, v in self.colors.items() if isinstance(v, QColor)}
        if self.dark_mode:
            for k in base:
                if k in ("outline", "edge", "boundary", "boundary_pressed", "w_input", "w_input_pressed", "w_output", "w_output_pressed"):
                    base[k] = QColor("#dbdbdb") if k != "outline" else QColor("#dbdbdb")
                else:
                    base[k] = adjust_for_dark(base[k])
        # else: do not adjust for light mode
        return base


# Initialise settings
settings = QSettings("zxlive", "zxlive")
for key, value in defaults.items():
    if not settings.contains(key):
        settings.setValue(key, value)

refresh_pyzx_tikz_settings()  # Call it once on startup

display_setting = DisplaySettings()

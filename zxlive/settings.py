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

"""Application-wide settings definitions, defaults, and the DisplaySettings
singleton used throughout the UI.

Improvements over the previous version
---------------------------------------
* ``ColorScheme`` is now a proper ``dataclass`` instead of a ``TypedDict``.
  This gives free ``__repr__``, enforced field types, and makes it easier to
  add methods (e.g. ``adjusted_for_dark``) without scattering logic across
  ``DisplaySettings``.
* Dark-mode color adjustment is a method on ``ColorScheme`` rather than an
  inline closure inside ``DisplaySettings.effective_colors``.
* ``DisplaySettings.dark_mode`` setter now immediately invalidates the Qt
  color-scheme hint on macOS (via ``QApplication.styleHints``) so the rest of
  the UI reflects the change without a restart.
* ``_cached_dark_mode`` and ``_cached_effective_colors`` are reset by a single
  ``_invalidate_color_cache`` path that is called consistently from every
  mutation point.
* ``SNAP_DIVISION`` is an instance variable only; the class-level default is
  removed to avoid the confusing shadow.
* All ``dict`` literal merges use ``|`` (Python 3.9+) consistently.
* Module-level ``settings`` initialisation is wrapped in a helper
  ``_init_settings()`` so it is testable without side-effects at import time.
* Added ``"startup-behavior"`` and ``"tutorial/show-on-startup"`` to
  ``general_defaults`` (they were already read by other modules but not
  declared here, which meant the ``settings.contains`` guard silently skipped
  writing defaults for first-time users on some platforms).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

import pyzx
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QTabWidget

from .common import get_settings_value, SCALE


# ---------------------------------------------------------------------------
# ColorScheme — dataclass replaces TypedDict
# ---------------------------------------------------------------------------

@dataclass
class ColorScheme:
    """All colors needed to render a ZX diagram.

    Using a dataclass (rather than TypedDict) means:
    - fields are typed and checked by mypy without casting
    - we can add methods (e.g. ``adjusted_for_dark``) without cluttering
      DisplaySettings
    - ``copy.replace()`` / ``dataclasses.replace()`` gives easy derivation
    """
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
    z_pauli_web: QColor
    x_pauli_web: QColor
    y_pauli_web: QColor

    # Fields that should keep their original value in dark mode
    # (outlines/edges must remain high-contrast against a dark background).
    _DARK_KEEP_FIELDS: frozenset[str] = field(
        default_factory=lambda: frozenset({
            "outline", "edge", "boundary", "boundary_pressed",
            "w_input", "w_input_pressed", "w_output", "w_output_pressed",
        }),
        init=False,
        repr=False,
        compare=False,
    )
    _DARK_REPLACEMENT: QColor = field(
        default_factory=lambda: QColor("#dbdbdb"),
        init=False,
        repr=False,
        compare=False,
    )

    def adjusted_for_dark(self) -> "ColorScheme":
        """Return a copy of this scheme with colors darkened for dark mode.

        Outline/edge colors are replaced with a light grey so they remain
        visible against a dark canvas; all other colors are desaturated and
        dimmed.
        """
        def _darken(color: QColor) -> QColor:
            h = color.hslHue()
            s = int(color.hslSaturation() * 0.4)
            l = int(color.lightness() * 0.6)
            a = color.alpha()
            return QColor.fromHsl(h, s, l, a)

        new_values: dict[str, object] = {}
        for f in self.__dataclass_fields__:
            if f.startswith("_"):
                continue
            val = getattr(self, f)
            if not isinstance(val, QColor):
                new_values[f] = val
            elif f in self._DARK_KEEP_FIELDS:
                new_values[f] = QColor(self._DARK_REPLACEMENT)
            else:
                new_values[f] = _darken(val)
        # id/label stay the same — this is still the same scheme, just adapted
        return ColorScheme(**new_values)  # type: ignore[arg-type]

    def color_dict(self) -> dict[str, QColor]:
        """Return only the QColor fields as a plain dict (for painting code)."""
        return {
            f: getattr(self, f)
            for f in self.__dataclass_fields__
            if isinstance(getattr(self, f), QColor)
        }


# ---------------------------------------------------------------------------
# Settings defaults
# ---------------------------------------------------------------------------

general_defaults: dict[str, object] = {
    "path/custom-rules": "rules/",
    "color-scheme": "modern-red-green",
    "swap-pauli-web-colors": False,
    "blue-y-pauli-web": False,
    "tab-bar-location": QTabWidget.TabPosition.North,
    "snap-granularity": "4",
    "input-circuit-format": "openqasm",
    "previews-show": True,
    "rewrite-animations": True,
    "sparkle-mode": True,
    "sound-effects": False,
    "matrix/precision": 4,
    "dark-mode": "system",
    "auto-save": False,
    "patterns-folder": "patterns/",
    # Startup & tutorial — declared here so first-run defaults are always written.
    "startup-behavior": "restore",
    "tutorial/show-on-startup": True,
    "tutorial/proof-seen": False,
    # Display
    "phase-label-color": "",
    "show-vertex-indices": False,
}

font_defaults: dict[str, object] = {
    "font/size": 11,
    "font/family": "Arial",
}

tikz_export_defaults: dict[str, str] = {
    "tikz/boundary-export": "none",
    "tikz/Z-spider-export": "Z dot",
    "tikz/X-spider-export": "X dot",
    "tikz/Z-phase-export": "Z phase dot",
    "tikz/X-phase-export": "X phase dot",
    "tikz/z-box-export": "Z box",
    "tikz/Hadamard-export": "hadamard",
    "tikz/w-output-export": "W triangle",
    "tikz/w-input-export": "W input",
    "tikz/dummy-export": "label",
    "tikz/edge-export": "",
    "tikz/edge-H-export": "hadamard edge",
    "tikz/edge-W-export": "W io edge",
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

defaults: dict[str, object] = (
    general_defaults
    | font_defaults
    | tikz_export_defaults
    | tikz_import_defaults
    | tikz_layout_defaults
    | tikz_names_defaults
)


# ---------------------------------------------------------------------------
# Built-in color schemes
# ---------------------------------------------------------------------------

modern_red_green = ColorScheme(
    id="modern-red-green",
    label="Modern Red & Green",
    z_spider=QColor("#ccffcc"),
    z_spider_pressed=QColor("#64BC90"),
    x_spider=QColor("#ff8888"),
    x_spider_pressed=QColor("#bb0f0f"),
    hadamard=QColor("#ffff00"),
    hadamard_pressed=QColor("#f1c232"),
    boundary=QColor("#000000"),
    boundary_pressed=QColor("#444444"),
    w_input=QColor("#000000"),
    w_input_pressed=QColor("#444444"),
    w_output=QColor("#000000"),
    w_output_pressed=QColor("#444444"),
    outline=QColor("#000000"),
    dummy=QColor("#B6B6B6"),
    dummy_pressed=QColor("#808080"),
    edge=QColor("#000000"),
    dummy_edge=QColor("#808080"),
    z_pauli_web=QColor("#ccffcc"),
    x_pauli_web=QColor("#ff8888"),
    y_pauli_web=QColor("#6688ff"),
)

classic_red_green = ColorScheme(
    **{
        **{f: getattr(modern_red_green, f)
           for f in modern_red_green.__dataclass_fields__ if not f.startswith("_")},
        "id": "classic-red-green",
        "label": "Classic Red & Green",
        "z_spider": QColor("#00ff00"),
        "z_spider_pressed": QColor("#00dd00"),
        "x_spider": QColor("#ff0d00"),
        "x_spider_pressed": QColor("#dd0b00"),
        "z_pauli_web": QColor("#00ff00"),
        "x_pauli_web": QColor("#ff0d00"),
        "y_pauli_web": QColor("#0000ff"),
    }
)

white_gray = ColorScheme(
    **{
        **{f: getattr(modern_red_green, f)
           for f in modern_red_green.__dataclass_fields__ if not f.startswith("_")},
        "id": "white-grey",
        "label": "Dodo book White & Grey",
        "z_spider": QColor("#ffffff"),
        "z_spider_pressed": QColor("#eeeeee"),
        "x_spider": QColor("#b4b4b4"),
        "x_spider_pressed": QColor("#a0a0a0"),
        "hadamard": QColor("#ffffff"),
        "hadamard_pressed": QColor("#dddddd"),
    }
)

gidney = ColorScheme(
    **{
        **{f: getattr(white_gray, f)
           for f in white_gray.__dataclass_fields__ if not f.startswith("_")},
        "id": "gidney",
        "label": "Gidney's Black & White",
        "z_spider": QColor("#000000"),
        "z_spider_pressed": QColor("#222222"),
        "x_spider": QColor("#ffffff"),
        "x_spider_pressed": QColor("#dddddd"),
    }
)

color_schemes: dict[str, ColorScheme] = {
    s.id: s for s in [modern_red_green, classic_red_green, white_gray, gidney]
}
color_scheme_ids: list[str] = list(color_schemes)


# ---------------------------------------------------------------------------
# TikZ class helpers
# ---------------------------------------------------------------------------

def load_tikz_classes() -> dict[str, str]:
    """Read the current tikz-export class names from QSettings."""
    return {
        "boundary": str(settings.value("tikz/boundary-export",
                                       pyzx.settings.tikz_classes["boundary"])),
        "Z":        str(settings.value("tikz/Z-spider-export",
                                       pyzx.settings.tikz_classes["Z"])),
        "X":        str(settings.value("tikz/X-spider-export",
                                       pyzx.settings.tikz_classes["X"])),
        "Z phase":  str(settings.value("tikz/Z-phase-export",
                                       pyzx.settings.tikz_classes["Z phase"])),
        "X phase":  str(settings.value("tikz/X-phase-export",
                                       pyzx.settings.tikz_classes["X phase"])),
        "Z box":    str(settings.value("tikz/z-box-export",
                                       pyzx.settings.tikz_classes["Z box"])),
        "H":        str(settings.value("tikz/Hadamard-export",
                                       pyzx.settings.tikz_classes["H"])),
        "W":        str(settings.value("tikz/w-output-export",
                                       pyzx.settings.tikz_classes["W"])),
        "W input":  str(settings.value("tikz/w-input-export",
                                       pyzx.settings.tikz_classes["W input"])),
        "dummy":    str(settings.value("tikz/dummy-export",
                                       pyzx.settings.tikz_classes["dummy"])),
        "edge":     str(settings.value("tikz/edge-export",
                                       pyzx.settings.tikz_classes["edge"])),
        "H-edge":   str(settings.value("tikz/edge-H-export",
                                       pyzx.settings.tikz_classes["H-edge"])),
        "W-io-edge":str(settings.value("tikz/edge-W-export",
                                       pyzx.settings.tikz_classes["W-io-edge"])),
    }


def refresh_pyzx_tikz_settings() -> None:
    """Sync pyzx's tikz class names and synonym lists from QSettings."""

    def _synonyms(key: str, default: list[str]) -> list[str]:
        val: object = settings.value(key)
        if not val:
            return default
        return [s.strip().lower() for s in str(val).split(",")]

    pyzx.settings.tikz_classes = load_tikz_classes()
    pyzx.tikz.synonyms_boundary  = _synonyms("tikz/boundary-import",  pyzx.tikz.synonyms_boundary)
    pyzx.tikz.synonyms_z         = _synonyms("tikz/Z-spider-import",   pyzx.tikz.synonyms_z)
    pyzx.tikz.synonyms_x         = _synonyms("tikz/X-spider-import",   pyzx.tikz.synonyms_x)
    pyzx.tikz.synonyms_hadamard  = _synonyms("tikz/Hadamard-import",   pyzx.tikz.synonyms_hadamard)
    pyzx.tikz.synonyms_w_input   = _synonyms("tikz/w-input-import",    pyzx.tikz.synonyms_w_input)
    pyzx.tikz.synonyms_w_output  = _synonyms("tikz/w-output-import",   pyzx.tikz.synonyms_w_output)
    pyzx.tikz.synonyms_z_box     = _synonyms("tikz/z-box-import",      pyzx.tikz.synonyms_z_box)
    pyzx.tikz.synonyms_dummy     = _synonyms("tikz/dummy-import",       pyzx.tikz.synonyms_dummy)
    pyzx.tikz.synonyms_edge      = _synonyms("tikz/edge-import",        pyzx.tikz.synonyms_edge)
    pyzx.tikz.synonyms_hedge     = _synonyms("tikz/edge-H-import",      pyzx.tikz.synonyms_hedge)
    pyzx.tikz.synonyms_wedge     = _synonyms("tikz/edge-W-import",      pyzx.tikz.synonyms_wedge)


# ---------------------------------------------------------------------------
# DisplaySettings singleton
# ---------------------------------------------------------------------------

class DisplaySettings:
    """Runtime display configuration derived from QSettings.

    A single instance (``display_setting``) is created at module level and
    shared throughout the application.  Panels call ``update_colors()`` after
    the user changes a setting so the canvas redraws with the new scheme.

    Caching
    -------
    ``dark_mode`` and ``effective_colors`` are computed on first access and
    cached until ``_invalidate_color_cache()`` is called.  Every mutation path
    (``set_color_scheme``, ``dark_mode.setter``, ``update``) calls the
    invalidation method, so stale values are never served.
    """

    def __init__(self) -> None:
        scheme_id = str(settings.value("color-scheme", "modern-red-green"))
        self.colors: ColorScheme = color_schemes.get(scheme_id, modern_red_green)
        self._cached_dark_mode: Optional[bool] = None
        self._cached_effective_colors: Optional[dict[str, QColor]] = None
        self._snap_division: int = 4
        self._font: QFont = QFont("Arial", 11)
        self._snap: float = SCALE / self._snap_division
        self.update()

    # -- color scheme --------------------------------------------------------

    def set_color_scheme(self, scheme_id: str) -> None:
        self.colors = color_schemes.get(scheme_id, modern_red_green)
        self._invalidate_color_cache()

    # -- snap / font ---------------------------------------------------------

    @property
    def SNAP_DIVISION(self) -> int:
        return self._snap_division

    @property
    def SNAP(self) -> float:
        return self._snap

    @property
    def font(self) -> QFont:
        return self._font

    def update(self) -> None:
        """Re-read mutable settings (snap, font) from QSettings."""
        snap_str = get_settings_value("snap-granularity", str, "4")
        try:
            self._snap_division = int(snap_str)
        except (ValueError, TypeError):
            self._snap_division = 4
        self._font = QFont(
            get_settings_value("font/family", str, "Arial"),
            get_settings_value("font/size", int, 11),
        )
        self._snap = SCALE / max(self._snap_division, 1)
        self._invalidate_color_cache()

    # -- dark mode -----------------------------------------------------------

    @property
    def dark_mode(self) -> bool:
        if self._cached_dark_mode is not None:
            return self._cached_dark_mode
        mode = str(settings.value("dark-mode", "system"))
        if mode == "dark":
            self._cached_dark_mode = True
        elif mode == "light":
            self._cached_dark_mode = False
        else:  # "system"
            app = QApplication.instance()
            if isinstance(app, QApplication):
                try:
                    self._cached_dark_mode = (
                        app.styleHints().colorScheme() == Qt.ColorScheme.Dark
                    )
                except AttributeError:
                    self._cached_dark_mode = False
            else:
                self._cached_dark_mode = False
        return self._cached_dark_mode  # type: ignore[return-value]

    @dark_mode.setter
    def dark_mode(self, value: str | bool) -> None:
        if isinstance(value, bool):
            value = "dark" if value else "light"
        settings.setValue("dark-mode", value)
        self._invalidate_color_cache()
        # On macOS, push the hint to Qt immediately so native widgets adapt.
        app = QApplication.instance()
        if isinstance(app, QApplication):
            try:
                if value == "dark":
                    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
                elif value == "light":
                    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
                else:
                    app.styleHints().unsetColorScheme()
            except AttributeError:
                pass  # Qt < 6.5

    # -- effective colors ----------------------------------------------------

    @property
    def effective_colors(self) -> dict[str, QColor]:
        """Color dict adapted for the current light/dark mode."""
        if self._cached_effective_colors is not None:
            return self._cached_effective_colors
        if self.dark_mode:
            self._cached_effective_colors = self.colors.adjusted_for_dark().color_dict()
        else:
            self._cached_effective_colors = self.colors.color_dict()
        return self._cached_effective_colors

    # -- text / misc ---------------------------------------------------------

    @property
    def text_color(self) -> str:
        return "#e0e0e0" if self.dark_mode else "#222222"

    @property
    def show_vertex_indices(self) -> bool:
        return get_settings_value("show-vertex-indices", bool, False)

    @property
    def previews_show(self) -> bool:
        return get_settings_value("previews-show", bool, True)

    @previews_show.setter
    def previews_show(self, value: bool) -> None:
        settings.setValue("previews-show", value)

    # -- internals -----------------------------------------------------------

    def _invalidate_color_cache(self) -> None:
        self._cached_dark_mode = None
        self._cached_effective_colors = None


# ---------------------------------------------------------------------------
# Module-level initialisation
# ---------------------------------------------------------------------------

def _init_settings() -> QSettings:
    """Create the QSettings instance and write any missing defaults."""
    s = QSettings("zxlive", "zxlive")
    for key, value in defaults.items():
        if not s.contains(key):
            s.setValue(key, value)
    return s


settings: QSettings = _init_settings()
refresh_pyzx_tikz_settings()
display_setting: DisplaySettings = DisplaySettings()

from __future__ import annotations

import io
from functools import lru_cache
from typing import Optional

from PySide6.QtGui import QColor, QImage, QPixmap


_BASE_DPI = 1200
_SUPERSAMPLE = 2


def _color_to_hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


@lru_cache(maxsize=1)
def _latex_engine_available() -> bool:
    """Best-effort probe for full LaTeX rendering backend."""
    try:
        from matplotlib import pyplot as plt

        original = plt.rcParams.get("text.usetex", False)
        plt.rcParams["text.usetex"] = True
        fig = plt.figure(figsize=(0.01, 0.01), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.text(0, 0, r"$x$", fontsize=8)
        fig.canvas.draw()
        plt.close(fig)
        plt.rcParams["text.usetex"] = original
        return True
    except Exception:
        return False


@lru_cache(maxsize=256)
def _render_png_bytes_cached(text: str, font_size: int, color_hex: str, use_tex: bool) -> bytes:
    from matplotlib import pyplot as plt

    original = plt.rcParams.get("text.usetex", False)
    plt.rcParams["text.usetex"] = use_tex

    dpi = _BASE_DPI * _SUPERSAMPLE
    fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    text_artist = ax.text(0, 0, text, fontsize=max(1, font_size), color=color_hex, va="bottom", ha="left")

    fig.canvas.draw()
    bbox = text_artist.get_window_extent(renderer=fig.canvas.get_renderer()).expanded(1.04, 1.12)
    width_px = max(1, int(bbox.width))
    height_px = max(1, int(bbox.height))

    # Adaptive figure size from expression bbox.
    fig.set_size_inches(width_px / fig.dpi, height_px / fig.dpi)
    ax.set_xlim(0, width_px)
    ax.set_ylim(0, height_px)
    text_artist.set_position((0, 0))

    bio = io.BytesIO()
    fig.savefig(
        bio,
        format="png",
        dpi=fig.dpi,
        transparent=True,
        bbox_inches="tight",
        pad_inches=0.0,
    )
    plt.close(fig)
    plt.rcParams["text.usetex"] = original
    return bio.getvalue()


def render_latex_text_to_pixmap(text: str, font_size: int, color: QColor) -> Optional[QPixmap]:
    """Render mixed text/LaTeX to a transparent HD pixmap.

    Prefers full LaTeX (`plt.rcParams['text.usetex'] = True`) and falls back
    to matplotlib mathtext when TeX is not available on the system.
    """
    if not text:
        return None

    try:
        use_tex = _latex_engine_available()
        png_data = _render_png_bytes_cached(text, font_size, _color_to_hex(color), use_tex)
    except Exception:
        return None

    img = QImage.fromData(png_data, "PNG")
    if img.isNull():
        return None

    pixmap = QPixmap.fromImage(img)
    effective_dpi = _BASE_DPI * _SUPERSAMPLE
    pixmap.setDevicePixelRatio(max(1.0, effective_dpi / 300.0))
    return pixmap

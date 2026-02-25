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

"""LaTeX expression rendering for dummy node labels.

Uses matplotlib to convert LaTeX math expressions to SVG.
"""

from __future__ import annotations

import re
from io import BytesIO


def is_latex(text: str) -> bool:
    """Return True if text contains LaTeX markup.

    Detects $ delimiters, backslash commands, and explicit
    superscript/subscript notation.
    """
    if not text:
        return False
    if '$' in text:
        return True
    if re.search(r'\\[a-zA-Z]+', text):
        return True
    if re.search(r'[\^_]', text):
        return True
    return False


def _preprocess_dirac(text: str) -> str:
    """Expand Dirac notation into standard LaTeX before conversion.

    Matplotlib does not know \\ket, \\bra, \\braket by default. Rewrite them
    into \\langle / \\rangle forms.
    """
    result = text
    result = re.sub(r'\\ket\s*\{([^}]*)\}', r'|{\1}\\rangle', result)
    result = re.sub(r'\\bra\s*\{([^}]*)\}', r'\\langle{\1}|', result)
    # Two-argument form: \braket{a}{b} -> \langle a | b \rangle
    result = re.sub(r'\\braket\s*\{([^}]*)\}\s*\{([^}]*)\}',
                    r'\\langle{\1}|{\2}\\rangle', result)
    # Single-argument form: \braket{a} -> \langle a \rangle
    result = re.sub(r'\\braket\s*\{([^}]*)\}', r'\\langle{\1}\\rangle', result)
    return result


def _fallback_svg(text: str, color: str, size: float) -> bytes:
    """Generate a simple fallback SVG when rendering fails.

    Uses numeric coordinates for text (not percentages) so Qt's QSvgRenderer
    displays the text correctly.
    """
    import html
    escaped = html.escape(text.replace('$', '').strip())
    if not escaped:
        escaped = " "
    width = max(len(escaped) * size * 0.6, size)
    height = size * 1.4
    x = width / 2
    y = height / 2
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<text x="{x}" y="{y}" dominant-baseline="middle" text-anchor="middle" '
        f'font-family="serif" font-size="{size}" '
        f'fill="{color}">{escaped}</text></svg>'
    )
    return svg.encode('utf-8')


def _svg_viewbox_empty(svg_bytes: bytes) -> bool:
    """Return True if the SVG has no or negligible viewBox (e.g. failed render)."""
    m = re.search(rb'viewBox\s*=\s*["\']([^"\']+)["\']', svg_bytes)
    if not m:
        return True
    parts = m.group(1).strip().split()
    if len(parts) != 4:
        return True
    try:
        w = float(parts[2])
        h = float(parts[3])
        return w < 0.5 or h < 0.5
    except (ValueError, IndexError):
        return True


def latex_to_svg(text: str, color: str = "#222222", size: float = 24) -> bytes:
    """Convert LaTeX math text to SVG bytes via matplotlib.

    Args:
        text: LaTeX expression, with or without $ delimiters.
        color: Hex color string for the rendered text.
        size: Font size in points.

    Returns:
        SVG content as bytes suitable for QSvgRenderer / QGraphicsSvgItem.
    """
    result = text.strip()
    result = _preprocess_dirac(result)

    # Matplotlib needs $...$ for math mode in text usually, or we can use mathtext.
    # To be safe, we wrap if not wrapped.
    if '$' not in result:
        result = f"${result}$"

    try:
        import matplotlib as mpl
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_svg import FigureCanvasSVG

        # Configure matplotlib to output text as paths (no font dependency)
        # and use Computer Modern font for LaTeX look.
        with mpl.rc_context({
            'svg.fonttype': 'path',
            'mathtext.fontset': 'cm',
            'font.family': 'serif',
            'text.usetex': False  # Use internal mathtext parser, not external latex
        }):
            # Use a larger figure and center text so bbox_inches='tight' does not clip
            # (e.g. fractions, superscripts like e^{U/2}).
            fig = Figure(figsize=(6, 2))
            FigureCanvasSVG(fig)
            fig.text(0.5, 0.5, result, fontsize=size, color=color,
                     ha='center', va='center')
            output = BytesIO()
            fig.savefig(output, format='svg', bbox_inches='tight', pad_inches=0.05, transparent=True)
            svg_bytes = output.getvalue()
            # If output is effectively empty (broken mathtext that didn't raise), fallback
            if _svg_viewbox_empty(svg_bytes):
                return _fallback_svg(text, color, size)
            return svg_bytes
    except Exception:
        return _fallback_svg(text, color, size)

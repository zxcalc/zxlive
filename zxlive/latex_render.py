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
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.backends.backend_svg import FigureCanvasSVG

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
    result = re.sub(r'\\braket\s*\{([^}]*)\}', r'\\langle{\1}\\rangle', result)
    return result


def _fallback_svg(text: str, color: str, size: float) -> bytes:
    """Generate a simple fallback SVG when rendering fails."""
    import html
    escaped = html.escape(text.replace('$', ''))
    # Approximate width based on character count
    width = len(escaped) * size * 0.6
    height = size * 1.4
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        f'font-family="serif" font-size="{size}" '
        f'fill="{color}">{escaped}</text></svg>'
    )
    return svg.encode('utf-8')


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
        # Configure matplotlib to output text as paths (no font dependency)
        # and use Computer Modern font for LaTeX look.
        with mpl.rc_context({
            'svg.fonttype': 'path', 
            'mathtext.fontset': 'cm',
            'font.family': 'serif',
            'text.usetex': False  # Use internal mathtext parser, not external latex
        }):
            fig = Figure(figsize=(0.01, 0.01))
            FigureCanvasSVG(fig)
            
            # Add text. We use a figure just to hold the text.
            # Using fig.text() is generally reliable.
            text_obj = fig.text(0, 0, result, fontsize=size, color=color)
            
            output = BytesIO()
            # bbox_inches='tight' computes the bounding box of the text
            fig.savefig(output, format='svg', bbox_inches='tight', pad_inches=0.01, transparent=True)
            
            return output.getvalue()
    except Exception as e:
        # Fallback if matplotlib fails (e.g. invalid latex)
        return _fallback_svg(text, color, size)

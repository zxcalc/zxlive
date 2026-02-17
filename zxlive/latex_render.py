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

Uses ziamath to convert LaTeX math expressions to SVG, then
flattens <symbol>/<use> references into inline paths so that
Qt's SVG Tiny renderer can display them.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET

import ziamath as zm

_SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace('', _SVG_NS)


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

    ziamath does not know \\ket, \\bra, \\braket. Rewrite them
    into \\langle / \\rangle forms.
    """
    result = text
    result = re.sub(r'\\ket\s*\{([^}]*)\}', r'|{\1}\\rangle', result)
    result = re.sub(r'\\bra\s*\{([^}]*)\}', r'\\langle{\1}|', result)
    result = re.sub(r'\\braket\s*\{([^}]*)\}', r'\\langle{\1}\\rangle', result)
    return result


def _ensure_dollar_wrapped(text: str) -> str:
    """Wrap text in $ delimiters if not already present."""
    stripped = text.strip()
    if stripped.startswith('$') and stripped.endswith('$'):
        return stripped
    return f'${stripped}$'


def _flatten_svg(svg_str: str) -> str:
    """Inline <symbol>/<use> pairs into <g transform="..."> groups.

    Qt's SVG renderer (SVG Tiny 1.2) rejects both <symbol>/<use>
    references and nested <svg> elements.  This function resolves
    every <use> into a <g> with an explicit translate+scale
    transform that maps the symbol's viewBox into the <use>'s
    (x, y, width, height) region, then removes the <symbol> defs.
    """
    root = ET.fromstring(svg_str)

    symbols: dict[str, ET.Element] = {}
    for symbol_el in root.findall(f'{{{_SVG_NS}}}symbol'):
        sid = symbol_el.get('id', '')
        if sid:
            symbols[sid] = symbol_el

    for use in list(root.findall(f'{{{_SVG_NS}}}use')):
        href = use.get('href') or use.get(f'{{{_SVG_NS}}}href') or ''
        ref_id = href.lstrip('#')
        sym = symbols.get(ref_id)
        if sym is None:
            continue

        ux = float(use.get('x', '0'))
        uy = float(use.get('y', '0'))
        uw = float(use.get('width', '0'))
        uh = float(use.get('height', '0'))

        vb = sym.get('viewBox', '')
        vb_parts = vb.split()
        if len(vb_parts) == 4:
            vb_x, vb_y, vb_w, vb_h = (float(v) for v in vb_parts)
        else:
            vb_x, vb_y, vb_w, vb_h = 0.0, 0.0, uw, uh

        sx = uw / vb_w if vb_w else 1.0
        sy = uh / vb_h if vb_h else 1.0

        tx = ux - vb_x * sx
        ty = uy - vb_y * sy

        g = ET.SubElement(root, f'{{{_SVG_NS}}}g')
        g.set('transform', f'translate({tx},{ty}) scale({sx},{sy})')

        fill = use.get('fill')
        if fill:
            g.set('fill', fill)

        for child in sym:
            g.append(copy.deepcopy(child))

        root.remove(use)

    for symbol_el in list(root.findall(f'{{{_SVG_NS}}}symbol')):
        root.remove(symbol_el)

    return ET.tostring(root, encoding='unicode')


def _fallback_svg(text: str, color: str, size: float) -> bytes:
    """Generate a simple fallback SVG when ziamath fails to parse."""
    import html
    escaped = html.escape(text.replace('$', ''))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{len(escaped) * size * 0.6}" height="{size * 1.4}">'
        f'<text x="0" y="{size}" '
        f'font-family="serif" font-size="{size}" '
        f'fill="{color}">{escaped}</text></svg>'
    )
    return svg.encode('utf-8')


def latex_to_svg(text: str, color: str = "#222222",
                 size: float = 24) -> bytes:
    """Convert LaTeX math text to SVG bytes via ziamath.

    Args:
        text: LaTeX expression, with or without $ delimiters.
        color: Hex color string for the rendered text.
        size: Font size in points.

    Returns:
        SVG content as bytes suitable for QSvgRenderer / QGraphicsSvgItem.
    """
    result = text.strip()
    # Users often type $...$ delimiters. ziamath input doesn't need them, and
    # keeping them can result in literal '$' glyphs appearing in Qt rendering.
    result = result.replace('$', '')
    result = _preprocess_dirac(result)

    try:
        svg_str: str = zm.Latex(result, size=size, color=color).svg()
        flat = _flatten_svg(svg_str)
        return flat.encode('utf-8')
    except Exception:
        return _fallback_svg(text, color, size)

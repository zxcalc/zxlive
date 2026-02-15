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

Uses pylatexenc to convert LaTeX commands to unicode, then applies
HTML post-processing for superscripts/subscripts for Qt rich text.
"""

from __future__ import annotations

import re

from pylatexenc.latex2text import LatexNodes2Text

_l2t = LatexNodes2Text()


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

    pylatexenc does not know \\ket, \\bra, \\braket. Rewrite them
    into \\langle / \\rangle forms that it does handle.
    """
    result = text
    result = re.sub(r'\\ket\s*\{([^}]*)\}', r'|{\1}\\rangle', result)
    result = re.sub(r'\\bra\s*\{([^}]*)\}', r'\\langle{\1}|', result)
    result = re.sub(r'\\braket\s*\{([^}]*)\}', r'\\langle{\1}\\rangle', result)
    return result


def latex_to_html(text: str, color: str = "#222222") -> str:
    """Convert LaTeX math text to HTML for Qt rich text rendering.

    Uses pylatexenc for the heavy lifting (thousands of LaTeX commands
    covered), then applies HTML post-processing for superscripts and
    subscripts which pylatexenc leaves as ^ and _ characters.
    """
    result = text.strip()
    # Strip $ delimiters
    result = re.sub(r'\$', '', result)

    # Expand Dirac notation before pylatexenc conversion
    result = _preprocess_dirac(result)

    # Let pylatexenc convert LaTeX commands to unicode
    result = _l2t.latex_to_text(result)

    # Post-process: convert ^ and _ to HTML sup/sub tags
    result = re.sub(r'\^\s*\{([^}]*)\}', r'<sup>\1</sup>', result)
    result = re.sub(r'\^(\S)', r'<sup>\1</sup>', result)
    result = re.sub(r'_\s*\{([^}]*)\}', r'<sub>\1</sub>', result)
    result = re.sub(r'_(\S)', r'<sub>\1</sub>', result)

    # Strip remaining braces
    result = result.replace('{', '').replace('}', '')

    return f'<span style="color:{color};">{result.strip()}</span>'

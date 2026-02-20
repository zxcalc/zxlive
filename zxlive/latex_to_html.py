from __future__ import annotations

import html
import re


# Common KaTeX/LaTeX control sequences supported in dummy-node labels.
_LATEX_SYMBOLS = {
    "\\Alpha": "Α",
    "\\Beta": "Β",
    "\\Gamma": "Γ",
    "\\Delta": "Δ",
    "\\Epsilon": "Ε",
    "\\Zeta": "Ζ",
    "\\Eta": "Η",
    "\\Theta": "Θ",
    "\\Iota": "Ι",
    "\\Kappa": "Κ",
    "\\Lambda": "Λ",
    "\\Mu": "Μ",
    "\\Nu": "Ν",
    "\\Xi": "Ξ",
    "\\Omicron": "Ο",
    "\\Pi": "Π",
    "\\Rho": "Ρ",
    "\\Sigma": "Σ",
    "\\Tau": "Τ",
    "\\Upsilon": "Υ",
    "\\Phi": "Φ",
    "\\Chi": "Χ",
    "\\Psi": "Ψ",
    "\\Omega": "Ω",
    "\\alpha": "α",
    "\\beta": "β",
    "\\gamma": "γ",
    "\\delta": "δ",
    "\\epsilon": "ϵ",
    "\\varepsilon": "ε",
    "\\zeta": "ζ",
    "\\eta": "η",
    "\\theta": "θ",
    "\\vartheta": "ϑ",
    "\\iota": "ι",
    "\\kappa": "κ",
    "\\lambda": "λ",
    "\\mu": "μ",
    "\\nu": "ν",
    "\\xi": "ξ",
    "\\omicron": "ο",
    "\\pi": "π",
    "\\varpi": "ϖ",
    "\\rho": "ρ",
    "\\varrho": "ϱ",
    "\\sigma": "σ",
    "\\varsigma": "ς",
    "\\tau": "τ",
    "\\upsilon": "υ",
    "\\phi": "ϕ",
    "\\varphi": "φ",
    "\\chi": "χ",
    "\\psi": "ψ",
    "\\omega": "ω",
    "\\infty": "∞",
    "\\partial": "∂",
    "\\nabla": "∇",
    "\\forall": "∀",
    "\\exists": "∃",
    "\\neg": "¬",
    "\\land": "∧",
    "\\lor": "∨",
    "\\oplus": "⊕",
    "\\otimes": "⊗",
    "\\cdot": "·",
    "\\times": "×",
    "\\pm": "±",
    "\\mp": "∓",
    "\\neq": "≠",
    "\\leq": "≤",
    "\\geq": "≥",
    "\\ll": "≪",
    "\\gg": "≫",
    "\\approx": "≈",
    "\\equiv": "≡",
    "\\propto": "∝",
    "\\to": "→",
    "\\mapsto": "↦",
    "\\leftarrow": "←",
    "\\leftrightarrow": "↔",
    "\\Rightarrow": "⇒",
    "\\Leftarrow": "⇐",
    "\\Leftrightarrow": "⇔",
    "\\in": "∈",
    "\\notin": "∉",
    "\\ni": "∋",
    "\\subset": "⊂",
    "\\subseteq": "⊆",
    "\\supset": "⊃",
    "\\supseteq": "⊇",
    "\\cap": "∩",
    "\\cup": "∪",
    "\\setminus": "∖",
    "\\emptyset": "∅",
    "\\mathbb{N}": "ℕ",
    "\\mathbb{Z}": "ℤ",
    "\\mathbb{Q}": "ℚ",
    "\\mathbb{R}": "ℝ",
    "\\mathbb{C}": "ℂ",
    "\\int": "∫",
    "\\oint": "∮",
    "\\sum": "∑",
    "\\prod": "∏",
    "\\sqrt": "√",
    "\\angle": "∠",
    "\\degree": "°",
}


def dummy_text_to_html(text: str) -> str:
    """Convert dummy-node labels with `$...$` math segments into rich text."""
    if not text:
        return ""

    segments = re.split(r"(\$[^$]*\$)", text)
    out: list[str] = []
    for seg in segments:
        if seg.startswith("$") and seg.endswith("$") and len(seg) >= 2:
            out.append(_render_math(seg[1:-1]))
        else:
            out.append(html.escape(seg))
    return "".join(out)


def _render_math(expr: str) -> str:
    rendered = html.escape(expr)
    rendered = rendered.replace(r"\left", "")
    rendered = rendered.replace(r"\right", "")
    rendered = rendered.replace(r"\,", " ")
    rendered = rendered.replace(r"\;", " ")
    rendered = rendered.replace(r"\!", "")

    rendered = _replace_text_blocks(rendered)
    rendered = _replace_fracs(rendered)
    rendered = _replace_sqrt(rendered)
    rendered = _replace_quantum_notation(rendered)
    rendered = _replace_vec(rendered)
    rendered = _replace_commands(rendered)
    rendered = _replace_super_subscripts(rendered)
    return f"<span>{rendered}</span>"


def _replace_text_blocks(expr: str) -> str:
    text_pattern = re.compile(r"\\text\{([^{}]+)\}")
    return text_pattern.sub(lambda m: html.escape(m.group(1)), expr)


def _replace_fracs(expr: str) -> str:
    frac_pattern = re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}")
    while True:
        match = frac_pattern.search(expr)
        if not match:
            return expr
        num, den = match.groups()
        replacement = (
            "<span style=\"white-space: nowrap;\">"
            f"<sup>{num}</sup>&frasl;<sub>{den}</sub>"
            "</span>"
        )
        expr = expr[:match.start()] + replacement + expr[match.end():]


def _replace_sqrt(expr: str) -> str:
    sqrt_pattern = re.compile(r"\\sqrt\{([^{}]+)\}")
    return sqrt_pattern.sub(r"√(<span>\1</span>)", expr)




def _replace_quantum_notation(expr: str) -> str:
    ket_pattern = re.compile(r"\\ket\{([^{}]+)\}")
    bra_pattern = re.compile(r"\\bra\{([^{}]+)\}")
    braket_pattern = re.compile(r"\\braket\{([^{}|]+)\|([^{}|]+)\}")
    ketbra_pattern = re.compile(r"\\ketbra\{([^{}]+)\}\{([^{}]+)\}")

    expr = ketbra_pattern.sub(r"|\1⟩⟨\2|", expr)
    expr = braket_pattern.sub(r"⟨\1|\2⟩", expr)
    expr = ket_pattern.sub(r"|\1⟩", expr)
    expr = bra_pattern.sub(r"⟨\1|", expr)
    return expr

def _replace_vec(expr: str) -> str:
    vec_pattern = re.compile(r"\\vec\{([^{}]+)\}")
    return vec_pattern.sub(lambda m: _apply_vec_accent(m.group(1)), expr)


def _apply_vec_accent(text: str) -> str:
    return "".join(ch if ch.isspace() else f"{ch}⃗" for ch in text)

def _replace_commands(expr: str) -> str:
    for latex in sorted(_LATEX_SYMBOLS, key=len, reverse=True):
        symbol = _LATEX_SYMBOLS[latex]
        expr = re.sub(re.escape(latex) + r"(?![A-Za-z])", symbol, expr)
    return expr


def _replace_super_subscripts(expr: str) -> str:
    sup_braced = re.compile(r"\^\{([^{}]+)\}")
    sub_braced = re.compile(r"_\{([^{}]+)\}")
    sup_simple = re.compile(r"\^([A-Za-z0-9+\-*/=])")
    sub_simple = re.compile(r"_([A-Za-z0-9+\-*/=])")

    expr = sup_braced.sub(r"<sup>\1</sup>", expr)
    expr = sub_braced.sub(r"<sub>\1</sub>", expr)
    expr = sup_simple.sub(r"<sup>\1</sup>", expr)
    expr = sub_simple.sub(r"<sub>\1</sub>", expr)
    return expr

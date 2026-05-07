"""converters/math_helpers.py — Math font detection, LaTeX validation, pix2tex wrapper."""

import re

_MATH_FONTS = {"CMEX", "CMMI", "CMSY", "MSAM", "MSBM", "EUFM", "RSFS", "STIX"}

_FORMULA_RENDER_MAT = None  # lazily initialised at 3× for pix2tex quality


def _formula_render_mat() -> "fitz.Matrix":
    global _FORMULA_RENDER_MAT
    if _FORMULA_RENDER_MAT is None:
        import fitz
        _FORMULA_RENDER_MAT = fitz.Matrix(3, 3)
    return _FORMULA_RENDER_MAT


def _is_math_font(name: str) -> bool:
    u = name.upper()
    return any(u.startswith(mf) or u.startswith("+" + mf) for mf in _MATH_FONTS)


def _has_formula_chars(text: str) -> bool:
    """True if text contains CMEX control chars or private-use-area bracket glyphs.

    Detects ASCII ctrl 0x00-0x1F (excl. tab/newline/CR/space) used by CMEX for
    large delimiters, and private-use-area 0xF800-0xF8FF for bracket glyphs.
    Deliberately excludes U+FB01 (fi ligature, 0xFB01 > 0xF8FF).
    """
    return any(
        (ord(c) < 0x20 and c not in '\t\n\r ')
        or (0xf800 <= ord(c) <= 0xf8ff)
        for c in text
    )


def _looks_like_formula(pil_img) -> bool:
    """Heuristic: is a raster image shape consistent with a formula (not a chart)?"""
    w, h = pil_img.size
    if w < 20 or h < 20:
        return False
    if w * h > 4_000_000:
        return False
    return 0.3 < w / h < 20


def _is_valid_latex(latex: str) -> bool:
    """Reject pix2tex outputs that are clearly garbage (excessive spacing commands)."""
    if not latex or not any(c in latex for c in r"\^_{}"):
        return False
    commands = re.findall(r"\\[a-zA-Z]+", latex)
    quad_count = sum(1 for c in commands if c in (r"\quad", r"\qquad"))
    return quad_count / max(1, len(commands)) < 0.4


def _try_latex(latex_model, pil_img) -> str | None:
    """Run pix2tex on a PIL image; return clean LaTeX string or None."""
    try:
        latex = latex_model(pil_img)
        if latex and _is_valid_latex(latex.strip()):
            return latex.strip()
    except Exception:
        pass
    return None

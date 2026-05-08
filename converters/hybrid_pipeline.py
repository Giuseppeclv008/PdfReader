"""converters/hybrid_pipeline.py — Hybrid text+image markdown converter (format 9).

Per-block strategy:
- Good text blocks  → plain markdown text
- Bad blocks (formula garbage, dominant math fonts) → warning callout + text + PNG crop
- Image blocks (type 1) → PNG crop only
- Chart noise (axis labels, legends, page counters) → skipped entirely
- Scanned pages (no extractable text) → full-page PNG
"""

import re
import sys
from pathlib import Path

from converters.math_helpers import _has_formula_chars, _is_math_font
from converters.base import ConversionFormat, register
from utils.utils import progress


def _block_should_skip(block_text: str) -> bool:
    """True if block is chart noise — axis labels, legends, or page counters."""
    lines = [line.strip() for line in block_text.splitlines() if line.strip()]
    # Pure numeric lines (chart axis tick labels)
    if lines and all(re.fullmatch(r"[-−]?\d+\.?\d*", t) for t in lines):
        return True
    # Chart legend: single short line with em-dash and "= value"
    if (
        len(lines) == 1
        and len(block_text.strip()) <= 60
        and re.search(r'[—–]', block_text)
        and re.search(r'=\s*[\d.]', block_text)
    ):
        return True
    # Slide page counter "3/64"
    if re.fullmatch(r"\d+/\d+", block_text.strip()):
        return True
    return False


def _block_is_legible(block, block_text: str) -> bool:
    """Stub: Check if block has legible text."""
    raise NotImplementedError


def _math_font_fraction(block) -> float:
    """Stub: Calculate fraction of text in math fonts."""
    raise NotImplementedError


def _render_block_png(page, block, mat, out_path):
    """Stub: Render block to PNG."""
    raise NotImplementedError


def _pdf_to_md_hybrid(doc, stem, out_dir, **_):
    """Stub: Convert PDF to markdown (format 9)."""
    raise NotImplementedError

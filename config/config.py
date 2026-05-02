"""config/config.py — global constants (rendering DPI, fitz availability check)"""

import sys

try:
    import fitz  # pymupdf
except ImportError:
    sys.exit("Install: pip install pymupdf")

_RENDER_DPI = 150
_OCR_DPI    = 200
_RENDER_MAT = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)
_OCR_MAT    = fitz.Matrix(_OCR_DPI / 72,    _OCR_DPI / 72)

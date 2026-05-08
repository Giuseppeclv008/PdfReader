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


def _math_font_fraction(block) -> float:
    """Fraction of chars in block rendered with math fonts (CM, STIX, etc.)."""
    total = math_chars = 0
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = span.get("text", "")
            total += len(t)
            if _is_math_font(span.get("font", "")):
                math_chars += len(t)
    return math_chars / total if total > 0 else 0.0


def _block_is_legible(block, block_text: str) -> bool:
    """True if block text is human-readable (no CMEX garbage, no dominant math fonts)."""
    if _has_formula_chars(block_text):
        return False
    if _math_font_fraction(block) > 0.30:
        return False
    return True


def _render_block_png(page, block, mat, out_path: Path) -> bool:
    """Render a block bounding box to PNG at 2× resolution. Returns True on success."""
    import fitz
    bbox = block["bbox"]
    if bbox[2] - bbox[0] < 5 or bbox[3] - bbox[1] < 5:
        return False
    try:
        pix = page.get_pixmap(matrix=mat, clip=fitz.Rect(bbox))
        pix.save(str(out_path))
        return True
    except Exception:
        print(f"[warn] skip block crop {out_path.name}", file=sys.stderr)
        return False


def _extract_block_text(block) -> str:
    """Concatenate all span texts in a block into a single string."""
    lines = []
    for line in block.get("lines", []):
        line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
        if line_text:
            lines.append(line_text)
    return " ".join(lines)


def _pdf_to_md_hybrid(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    import fitz

    blocks_dir = out_dir / f"{stem}_blocks"
    mat = fitz.Matrix(2, 2)
    blocks_dir_created = False

    def ensure_blocks_dir():
        nonlocal blocks_dir_created
        if not blocks_dir_created:
            blocks_dir.mkdir(exist_ok=True)
            blocks_dir_created = True

    lines = [f"# {stem}\n"]
    pages = list(enumerate(doc, start=1))

    for page_num, page in progress(pages, desc="Hybrid", unit="pg", position=1, leave=False):
        lines.append(f"\n---\n\n## Page {page_num}\n")

        # Scanned page: no extractable text → full-page PNG
        if not page.get_text("text").strip():
            ensure_blocks_dir()
            out_path = blocks_dir / f"p{page_num}_full.png"
            try:
                pix = page.get_pixmap(matrix=mat)
                pix.save(str(out_path))
                lines.append(f"\n![]({stem}_blocks/p{page_num}_full.png)\n")
            except Exception:
                print(f"[warn] skip scanned page {page_num}", file=sys.stderr)
            continue

        d = page.get_text("dict")
        blocks = sorted(d.get("blocks", []), key=lambda b: b["bbox"][1])

        for block_idx, block in enumerate(blocks):
            block_type = block.get("type", 0)

            if block_type == 1:
                # Raster image embedded in PDF
                ensure_blocks_dir()
                out_path = blocks_dir / f"p{page_num}_b{block_idx}.png"
                if _render_block_png(page, block, mat, out_path):
                    lines.append(f"\n![]({stem}_blocks/p{page_num}_b{block_idx}.png)\n")
                continue

            if block_type != 0:
                continue

            block_text = _extract_block_text(block)
            if not block_text:
                continue

            if _block_should_skip(block_text):
                continue

            if _block_is_legible(block, block_text):
                lines.append(f"\n{block_text}\n")
            else:
                ensure_blocks_dir()
                out_path = blocks_dir / f"p{page_num}_b{block_idx}.png"
                quoted = "\n> ".join(block_text.splitlines())
                lines.append(
                    f"\n> ⚠️ Testo estratto (potrebbe essere impreciso):\n> {quoted}\n"
                )
                if _render_block_png(page, block, mat, out_path):
                    lines.append(f"\n![]({stem}_blocks/p{page_num}_b{block_idx}.png)\n")

    return "\n".join(lines), f"{stem}_hybrid.md"


# ── registration ──────────────────────────────────────────────────────────────

register(ConversionFormat(
    key="9",
    name="Markdown ibrido testo+immagine",
    description=(
        "Testo per blocchi leggibili; callout ⚠️ + PNG per formule/grafici. "
        "Output: _hybrid.md + <nome>_blocks/."
    ),
    ext="md",
    source_ext=".pdf",
    convert=_pdf_to_md_hybrid,
    extra_args=None,
))

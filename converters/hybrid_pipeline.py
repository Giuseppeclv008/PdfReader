"""converters/hybrid_pipeline.py — Hybrid text+image markdown converter (format 9).

Per-block strategy:
- Good text blocks  → plain markdown text
- Bad blocks (formula garbage, dominant math fonts) → LaTeX via pix2tex if available,
  else warning callout + text + PNG crop
- Image blocks (type 1) → LaTeX via pix2tex if image looks like formula, else PNG crop
- Chart noise (axis labels, legends, page counters) → skipped entirely
- Scanned pages (no extractable text) → full-page PNG
"""

import re
import sys
from pathlib import Path

from converters.math_helpers import (
    _has_formula_chars,
    _is_math_font,
    _looks_like_formula,
    _try_latex,
    _formula_render_mat,
)
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


def _latex_from_block_region(page, block, latex_model, Image_cls, io_mod) -> str | None:
    """Render block bbox at 3× and run pix2tex. Returns LaTeX string or None."""
    if latex_model is None:
        return None
    try:
        import fitz
        formula_mat = _formula_render_mat()  # 3× for pix2tex quality
        clip_pix = page.get_pixmap(matrix=formula_mat, clip=fitz.Rect(block["bbox"]))
        formula_img = Image_cls.open(io_mod.BytesIO(clip_pix.tobytes("png")))
        return _try_latex(latex_model, formula_img)
    except Exception:
        return None


def _hybrid_extra_args() -> dict:
    raw = input("Enable LaTeX formula recognition via pix2tex? [y/N]: ").strip().lower()
    math_ocr = raw in ("y", "yes")
    if math_ocr:
        print("→ LaTeX recognition enabled (requires: pip install pix2tex)\n")
    return {"math_ocr": math_ocr}


def _pdf_to_md_hybrid(
    doc, stem: str, out_dir: Path, math_ocr: bool = False, **_
) -> tuple[str, str]:
    import fitz

    latex_model = None
    Image_cls = None
    io_mod = None
    if math_ocr:
        try:
            from pix2tex.cli import LatexOCR
            from PIL import Image as _Image
            import io as _io
            latex_model = LatexOCR()
            Image_cls = _Image
            io_mod = _io
        except ImportError:
            sys.exit(
                "LaTeX formula recognition requires an extra package:\n"
                "  pip install pix2tex"
            )

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
                # Raster image: try pix2tex if image looks like a formula
                latex = None
                if latex_model is not None:
                    try:
                        img_bytes = block.get("image", b"")
                        if img_bytes:
                            pil_img = Image_cls.open(io_mod.BytesIO(img_bytes))
                            if _looks_like_formula(pil_img):
                                latex = _try_latex(latex_model, pil_img)
                    except Exception:
                        pass
                if latex:
                    lines.append(f"\n$$\n{latex}\n$$\n")
                else:
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
                # Try pix2tex on block region; fallback to callout + PNG
                latex = _latex_from_block_region(page, block, latex_model, Image_cls, io_mod)
                if latex:
                    lines.append(f"\n$$\n{latex}\n$$\n")
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
        "Testo per blocchi leggibili; LaTeX (pix2tex) o PNG per formule/grafici. "
        "Output: _hybrid.md + <nome>_blocks/."
    ),
    ext="md",
    source_ext=".pdf",
    convert=_pdf_to_md_hybrid,
    extra_args=_hybrid_extra_args,
))

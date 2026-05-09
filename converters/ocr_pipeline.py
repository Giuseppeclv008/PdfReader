"""converters/ocr_pipeline.py — OCR pipeline for format 7: pytesseract + pix2tex.

Imports math detection primitives from math_helpers.
Registers format 7 (Markdown + OCR text).
"""

import sys
import re
from pathlib import Path

from config.config import _OCR_MAT
from utils.utils import progress
from converters.base import ConversionFormat, register
from converters.math_helpers import (
    _has_formula_chars,
    _is_math_font,
    _looks_like_formula,
    _try_latex,
    _formula_render_mat,
)


# ── text-extraction helpers ───────────────────────────────────────────────────

def _span_chars(span) -> str:
    """Join char objects from a PyMuPDF text span (rawdict format)."""
    return "".join(c["c"] for c in span.get("chars", []))


def _reconstruct_block_text(block) -> str:
    """Join a block's lines into text, reconstructing inline fractions.

    Detects fraction numerators by non-monotonic y0 in text-stream order:
    a short line (≤6 chars, no spaces) whose y0 < previous line's y0 is
    positioned above the baseline → it's a numerator; the following line
    is the denominator.  E.g. ['where C =', '1', 'nλ'] → 'where C = 1/nλ'.
    """
    lines = block.get("lines", [])
    if not lines:
        return ""

    line_info = []
    for line in lines:
        text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
        line_info.append((line["bbox"][1], text))

    parts: list[str] = []
    i = 0
    while i < len(line_info):
        y0, text = line_info[i]
        if (
            i > 0
            and y0 < line_info[i - 1][0]
            and 1 <= len(text) <= 6
            and not re.search(r"[\s\x00-\x1f]", text)
            and i + 1 < len(line_info)
        ):
            denom = line_info[i + 1][1]
            if denom:
                parts.append(f"{text}/{denom}")
                i += 2
                continue
        parts.append(text)
        i += 1

    return " ".join(p for p in parts if p)


def _is_fraction_join(prev: str, curr: str) -> bool:
    """True if prev ends with a non-ASCII math symbol and curr starts with a digit.

    Used in proximity merge to join 'λ' + '2 ∥w∥2:' as 'λ/2 ∥w∥2:'.
    """
    p = prev.rstrip()
    c = curr.lstrip()
    return bool(p and c and ord(p[-1]) > 127 and c[0].isdigit())


# ── formula region detection ──────────────────────────────────────────────────

def _extract_vector_formula_regions(page, pad_h=8, pad_v=4, gap=25,
                                    max_chars=80, min_math_frac=0.10) -> list:
    """Detect display-formula regions in vector/text PDFs (e.g. LaTeX-compiled).

    Uses CM math font detection to find formula blocks, excludes blocks whose
    y0 falls inside a prose block (inline formulas), merges nearby survivors.
    Returns list of fitz.Rect.
    """
    import fitz
    d = page.get_text("rawdict")

    prose_yranges: list[tuple[float, float]] = []
    candidates: list[fitz.Rect] = []

    for block in d["blocks"]:
        if block.get("type", 0) != 0:
            continue
        mc = ac = 0
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = _span_chars(span)
                ac += len(t)
                if _is_math_font(span["font"]):
                    mc += len(t)
        frac = mc / ac if ac else 0
        r = fitz.Rect(block["bbox"])
        block_text_raw = "".join(
            _span_chars(s)
            for line in block.get("lines", [])
            for s in line.get("spans", [])
        )
        has_fchars = _has_formula_chars(block_text_raw)
        if (frac < min_math_frac or ac > max_chars) and not has_fchars:
            prose_yranges.append((r.y0, r.y1))
        if (mc > 0 and frac >= min_math_frac and ac <= max_chars) or (has_fchars and mc > 0):
            # Skip pure numeric labels (chart axis ticks like -1.5, 0.0, 1.5)
            block_text = "".join(
                _span_chars(s)
                for line in block.get("lines", [])
                for s in line.get("spans", [])
            )
            if all(c in "0123456789.-−,− " for c in block_text):
                continue
            candidates.append(r)

    # Drop inline formula blocks (their y0 overlaps a prose block's y-range)
    display_cands = [
        r for r in candidates
        if not any(py0 <= r.y0 <= py1 for py0, py1 in prose_yranges)
    ]

    display_cands.sort(key=lambda r: r.y0)
    merged: list[fitz.Rect] = []
    for r in display_cands:
        if merged and r.y0 - merged[-1].y1 <= gap:
            prev = merged[-1]
            # Don't merge if a prose block falls between the two formula regions
            prose_between = any(
                prev.y1 <= py0 and py1 <= r.y0
                for py0, py1 in prose_yranges
                if py1 - py0 > 4  # ignore tiny hairline blocks
            )
            if prose_between:
                merged.append(r)
            else:
                merged[-1] = prev | r
        else:
            merged.append(r)

    # Drop tiny regions: height < 10px or width < 20px are chart labels / stray chars
    merged = [r for r in merged if r.height >= 10 and r.width >= 20]

    # Asymmetric pad: small vertical pad to avoid prose bleed, larger horizontal
    return [
        fitz.Rect(r.x0 - pad_h, r.y0 - pad_v, r.x1 + pad_h, r.y1 + pad_v)
        for r in merged
    ]


def _page_is_vector(page) -> bool:
    """True if page has extractable text (LaTeX-compiled PDF, not scanned)."""
    return bool(page.get_text("text").strip())


def _vector_page_to_md(page, latex_model, io_mod, Image_cls) -> str:
    """Convert a vector (text-based) PDF page to markdown.

    Extracts prose via get_text("dict"), detects display-formula regions,
    runs pix2tex on each, then interleaves prose and LaTeX by y-position
    so formulas appear in the correct reading position (not appended at end).
    """
    import fitz

    # Build formula region → latex map, keyed by (y0, y1)
    formula_slots: list[tuple[float, float, str]] = []  # (y0, y1, latex)
    if latex_model is not None:
        mat = _formula_render_mat()
        for r in _extract_vector_formula_regions(page):
            try:
                # Skip pix2tex when PyMuPDF can already extract clean text (no CMEX garbage).
                # For LaTeX-compiled PDFs, direct extraction is more accurate than image OCR.
                raw_d = page.get_text("rawdict", clip=r)
                raw_text = "".join(
                    c["c"]
                    for b in raw_d.get("blocks", []) if b.get("type", 0) == 0
                    for line in b.get("lines", [])
                    for span in line.get("spans", [])
                    for c in span.get("chars", [])
                )
                if raw_text.strip() and not _has_formula_chars(raw_text):
                    continue  # Good text available — prose loop will handle it
                clip_pix = page.get_pixmap(matrix=mat, clip=r)
                formula_img = Image_cls.open(io_mod.BytesIO(clip_pix.tobytes("png")))
                latex = _try_latex(latex_model, formula_img)
                if latex:
                    formula_slots.append((r.y0, r.y1, latex))
            except Exception:
                pass

        # Also check raster-embedded images
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = page.parent.extract_image(xref)
                formula_img = Image_cls.open(io_mod.BytesIO(base_image["image"]))
                if not _looks_like_formula(formula_img):
                    continue
                latex = _try_latex(latex_model, formula_img)
                if latex:
                    bboxes = [
                        page.get_image_bbox(info)
                        for info in page.get_images(full=True)
                        if info[0] == xref
                    ]
                    y_mid = bboxes[0].y0 if bboxes else 9999
                    formula_slots.append((y_mid, y_mid + 1, latex))
            except Exception:
                pass

    # Collect prose text blocks, skipping those inside formula regions
    # that successfully produced LaTeX (so we don't lose content on pix2tex failure)
    d = page.get_text("dict")
    items: list[tuple[float, str]] = []  # (y0, content)

    for block in d["blocks"]:
        if block["type"] != 0:
            continue
        by0 = block["bbox"][1]
        by1 = block["bbox"][3]
        # Skip block only if it sits inside a region that produced valid LaTeX
        in_formula = any(
            fy0 - 5 <= by0 and by1 <= fy1 + 5
            for fy0, fy1, _ in formula_slots
        )
        if in_formula:
            continue
        bw = block["bbox"][2] - block["bbox"][0]
        bh = block["bbox"][3] - block["bbox"][1]
        # Skip very small blocks (chart axis labels, stray annotations)
        if bw < 15 and bh < 10:
            continue
        block_text = _reconstruct_block_text(block)
        if not block_text:
            continue
        # Skip CMEX bracket/delimiter glyphs that leaked as prose
        if _has_formula_chars(block_text):
            continue
        # Skip chart legend labels: single-line, short, "Name — param = value" pattern
        if (
            '\n' not in block_text.strip()
            and bh <= 11
            and re.search(r'[—–]', block_text)
            and re.search(r'=\s*[\d.]', block_text)
        ):
            continue
        # Skip slide page-counter blocks like "3/64", "12/64"
        if re.fullmatch(r"\d+/\d+", block_text.strip()):
            continue
        # Skip purely-numeric blocks (chart axis tick labels)
        block_lines_text = [
            "".join(s.get("text", "") for s in line["spans"]).strip()
            for line in block["lines"]
        ]
        if block_lines_text and all(
            re.fullmatch(r"[-−]?\d+\.?\d*", t) for t in block_lines_text if t
        ):
            continue
        items.append((by0, block_text))

    # Add formula slots as items
    for fy0, fy1, latex in formula_slots:
        items.append((fy0, f"\n$$\n{latex}\n$$\n"))

    items.sort(key=lambda x: x[0])

    # Merge consecutive text items that are vertically close (same line / inline split)
    merged_items: list[tuple[float, str]] = []
    for y0, content in items:
        if (
            merged_items
            and not content.startswith("\n$$")
            and not merged_items[-1][1].startswith("\n$$")
            and y0 - merged_items[-1][0] < 12  # within ~1 line height
        ):
            prev_y, prev_text = merged_items[-1]
            sep = "/" if _is_fraction_join(prev_text, content) else " "
            merged_items[-1] = (prev_y, prev_text + sep + content)
        else:
            merged_items.append((y0, content))

    return "\n\n".join(content for _, content in merged_items)


# ── format 7 converter + extra-args prompt ────────────────────────────────────

def _pdf_ocr_extra_args() -> dict:
    raw = input("OCR language (e.g. eng, ita, ita+eng) [default: ita+eng]: ").strip()
    lang = raw if raw else "ita+eng"
    print(f"→ OCR language: {lang}\n")

    math_raw = input("Enable math formula recognition via pix2tex? [y/N]: ").strip().lower()
    math_ocr = math_raw in ("y", "yes")
    if math_ocr:
        print("→ Math OCR enabled (requires: pip install pix2tex)\n")

    ai_raw = input("Enable AI OCR cleanup via local Ollama LLM? [y/N]: ").strip().lower()
    ai_clean = ai_raw in ("y", "yes")
    if ai_clean:
        import os
        model = os.environ.get("AI_MODEL", "qwen2.5:3b")
        print(f"→ AI cleanup enabled (model: {model}, override via AI_MODEL env var)\n")

    return {"lang": lang, "math_ocr": math_ocr, "ai_clean": ai_clean}


def _preprocess_for_ocr(pil_img, ImageOps_mod):
    """Light preprocessing to improve OCR on stamps and dense pages.

    Grayscale + autocontrast — keeps faint text legible without destroying
    handwritten regions through aggressive thresholding.
    """
    return ImageOps_mod.autocontrast(pil_img.convert("L"), cutoff=2)


def _is_ocr_noise(line: str) -> bool:
    """True if a line is OCR garbage (stamp/signature fragments)."""
    s = line.strip()
    if len(s) <= 2:
        return True
    alpha = sum(1 for c in s if c.isalpha())
    if alpha / len(s) < 0.4:
        return True
    tokens = s.split()
    if tokens and len(tokens) <= 4 and all(len(t) <= 2 for t in tokens):
        return True
    return False


def _clean_ocr_text(raw: str) -> str:
    """Drop OCR-noise lines while preserving real content."""
    return "\n".join(line for line in raw.splitlines() if not _is_ocr_noise(line))


def _pdf_to_md_ocr(
    doc, stem: str, out_dir: Path,
    lang: str = "ita+eng", math_ocr: bool = False, ai_clean: bool = False, **_
) -> tuple[str, str]:
    try:
        import pytesseract
        from PIL import Image, ImageOps
        import io
    except ImportError:
        sys.exit(
            "Format requires extra packages:\n"
            "  pip install pytesseract pillow\n"
            "  + install Tesseract binary: https://tesseract-ocr.github.io/tessdoc/Installation.html"
        )

    latex_model = None
    if math_ocr:
        try:
            from pix2tex.cli import LatexOCR
            latex_model = LatexOCR()
        except ImportError:
            sys.exit(
                "Math formula recognition requires an extra package:\n"
                "  pip install pix2tex"
            )

    lines = [f"# {stem}\n"]
    pages = list(enumerate(doc, start=1))
    for i, page in progress(pages, desc="OCR", unit="pg", position=1, leave=False):
        lines.append(f"\n---\n\n## Page {i}\n")

        if _page_is_vector(page):
            # Vector PDF (LaTeX-compiled): use text extraction + pix2tex inline
            page_md = _vector_page_to_md(page, latex_model, io, Image)
        else:
            # Scanned page: pytesseract OCR + pix2tex on raster formula images
            pix = page.get_pixmap(matrix=_OCR_MAT)
            page_img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_img = _preprocess_for_ocr(page_img, ImageOps)
            raw_ocr = pytesseract.image_to_string(
                ocr_img, lang=lang, config="--psm 6"
            )
            page_md = _clean_ocr_text(raw_ocr).strip()
            if ai_clean and page_md:
                from converters.ai_helpers import clean_ocr_text
                page_md = clean_ocr_text(page_md)

            if latex_model is not None:
                extra = []
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        formula_img = Image.open(io.BytesIO(base_image["image"]))
                        if not _looks_like_formula(formula_img):
                            continue
                        latex = _try_latex(latex_model, formula_img)
                        if latex:
                            extra.append(f"\n$$\n{latex}\n$$\n")
                    except Exception:
                        pass
                if extra:
                    page_md = page_md + "\n" + "\n".join(extra)

        if page_md:
            lines.append(f"\n{page_md}\n")

    return "\n".join(lines), f"{stem}_ocr.md"


# ── registration ──────────────────────────────────────────────────────────────

register(ConversionFormat(
    key="7", name="Markdown + OCR text (pytesseract + optional math)",
    description="OCR via pytesseract; optionally adds LaTeX math via pix2tex. Requires: pip install pytesseract pillow + Tesseract binary. Math: pip install pix2tex.",
    ext="md", source_ext=".pdf", convert=_pdf_to_md_ocr, extra_args=_pdf_ocr_extra_args,
))

# Math/LaTeX Module Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all math/LaTeX detection and OCR pipeline code from the monolithic `converters/pdf_to_formats.py` into two focused modules (`math_helpers.py` and `ocr_pipeline.py`) so each module has one clear responsibility.

**Architecture:** `math_helpers.py` holds low-level math-detection primitives (font detection, char filtering, LaTeX validation, pix2tex wrapping). `ocr_pipeline.py` holds the text-extraction and OCR pipeline that orchestrates those primitives into format 7. `pdf_to_formats.py` shrinks to ~100 lines of simple, self-contained format converters (1–6). No behavior changes — pure structural move.

**Tech Stack:** Python 3.10+, PyMuPDF (`fitz`), pix2tex (optional), pytesseract (optional), Pillow

---

## File Map

| File | Status | Responsibility after refactor |
|------|--------|-------------------------------|
| `converters/math_helpers.py` | **CREATE** | Math detection primitives: font sets, char filters, LaTeX validator, pix2tex wrapper |
| `converters/ocr_pipeline.py` | **CREATE** | OCR pipeline: text helpers, formula region detection, vector-page converter, format 7 function + registration |
| `converters/pdf_to_formats.py` | **SHRINK** | General converters only: formats 1–6, ~100 lines |
| `converters/__init__.py` | **MODIFY** | Add `from . import ocr_pipeline` |
| `ARCHITECTURE.md` | **UPDATE** | Reflect new module structure, dependency graph, single-responsibility table |

---

### Task 1: Create `converters/math_helpers.py`

Move all low-level math-detection code here. Nothing in this file imports from `ocr_pipeline` or `pdf_to_formats` — it is a pure leaf module.

**Files:**
- Create: `converters/math_helpers.py`

- [ ] **Step 1: Create the file with exact content**

```python
"""converters/math_helpers.py — Math font detection, LaTeX validation, pix2tex wrapper."""

_MATH_FONTS = {"CMEX", "CMMI", "CMSY", "MSAM", "MSBM", "EUFM", "RSFS", "STIX"}

_FORMULA_RENDER_MAT = None  # lazily initialised at 3× for pix2tex quality


def _formula_render_mat():
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
    import re
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
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd /Users/giuseppecalvello/Documents/PdfReader && venv/bin/python3 -c "from converters.math_helpers import _is_math_font, _has_formula_chars, _try_latex; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Smoke-test the key functions**

```bash
venv/bin/python3 -c "
from converters.math_helpers import _is_math_font, _has_formula_chars, _is_valid_latex

# font detection
assert _is_math_font('CMEX10'), 'CMEX not detected'
assert _is_math_font('+CMMI12'), '+prefix not detected'
assert not _is_math_font('Arial'), 'Arial wrongly flagged'

# char detection
assert _has_formula_chars('\x00'), 'ctrl char not detected'
assert _has_formula_chars(''), 'pua char not detected'
assert not _has_formula_chars('define'),  'fi-ligature word wrongly flagged'
assert not _has_formula_chars('ﬁ'), 'fi ligature wrongly flagged'

# latex validation
assert _is_valid_latex(r'x^{2} + y^{2}'), 'valid latex rejected'
assert not _is_valid_latex(r'\quad \quad \quad \quad \qquad'), 'garbage latex accepted'

print('All assertions passed')
"
```

Expected output: `All assertions passed`

- [ ] **Step 4: Commit**

```bash
git add converters/math_helpers.py
git commit -m "refactor: extract math detection primitives into math_helpers.py"
```

---

### Task 2: Create `converters/ocr_pipeline.py`

Move the text-extraction helpers and full OCR pipeline here. This module imports from `math_helpers` (Task 1) and registers format 7.

**Files:**
- Create: `converters/ocr_pipeline.py`

- [ ] **Step 1: Create the file with exact content**

```python
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
                                    max_chars=80, min_math_frac=0.10):
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

    return {"lang": lang, "math_ocr": math_ocr}


def _pdf_to_md_ocr(
    doc, stem: str, out_dir: Path,
    lang: str = "ita+eng", math_ocr: bool = False, **_
) -> tuple[str, str]:
    try:
        import pytesseract
        from PIL import Image
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
            page_md = pytesseract.image_to_string(page_img, lang=lang).strip()

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
```

- [ ] **Step 2: Verify the module imports cleanly (before touching pdf_to_formats.py)**

```bash
cd /Users/giuseppecalvello/Documents/PdfReader && venv/bin/python3 -c "from converters.ocr_pipeline import _extract_vector_formula_regions, _vector_page_to_md; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add converters/ocr_pipeline.py
git commit -m "refactor: extract OCR pipeline into ocr_pipeline.py"
```

---

### Task 3: Trim `converters/pdf_to_formats.py` to formats 1–6 only

Remove all math helpers, OCR pipeline code, and format 7 from `pdf_to_formats.py`. What remains is six simple converter functions plus their registrations.

**Files:**
- Modify: `converters/pdf_to_formats.py`

- [ ] **Step 1: Replace the entire file with trimmed content**

```python
"""converters/pdf_to_formats.py — built-in PDF → * formats (keys 1–6), registered at import time.

Math/LaTeX helpers live in converters/math_helpers.py.
The OCR pipeline (format 7) lives in converters/ocr_pipeline.py.
"""

import json
from pathlib import Path

from config.config import _RENDER_MAT
from utils.utils import extract_images_b64, progress
from converters.base import ConversionFormat, register


# ── converter functions ───────────────────────────────────────────────────────
# All signatures: (doc, stem: str, out_dir: Path, **kwargs) -> (content: str, filename: str)

def _pdf_to_md_text(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    lines = [f"# {stem}\n"]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            lines.append(f"\n---\n\n## Page {i}\n\n{text}\n")
    return "\n".join(lines), f"{stem}.md"


def _pdf_to_md_ai(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    lines = [f"# {stem}\n"]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        images = extract_images_b64(page)
        lines.append(f"\n---\n\n## Page {i}\n")
        if text:
            lines.append(f"\n{text}\n")
        for j, data_uri in enumerate(images, start=1):
            lines.append(f"\n![Page {i} — Image {j}]({data_uri})\n")
    return "\n".join(lines), f"{stem}_ai.md"


def _pdf_to_txt(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    parts = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            parts.append(f"[Page {i}]\n{text}")
    return "\n\n".join(parts), f"{stem}.txt"


def _pdf_to_json(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    img_dir = out_dir / f"{stem}_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        img_paths = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                ext = base_image.get("ext", "png")
                img_file = img_dir / f"p{i}_img{len(img_paths) + 1}.{ext}"
                img_file.write_bytes(base_image["image"])
                img_paths.append(str(img_file))
            except Exception:
                pass
        pages.append({"page": i, "text": text, "images": img_paths})
    content = json.dumps({"document": stem, "pages": pages}, ensure_ascii=False, indent=2)
    return content, f"{stem}.json"


def _pdf_to_html(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    parts = [
        "<!DOCTYPE html><html><head>",
        f"<meta charset='utf-8'><title>{stem}</title>",
        "<style>body{font-family:sans-serif;max-width:900px;margin:auto;padding:2em}"
        "hr{margin:2em 0}img{max-width:100%;margin:1em 0;display:block}</style>",
        f"</head><body><h1>{stem}</h1>",
    ]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        images = extract_images_b64(page)
        parts.append(f"<hr><h2>Page {i}</h2>")
        if text:
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append(f"<pre>{escaped}</pre>")
        for data_uri in images:
            parts.append(f"<img src='{data_uri}' alt='Page {i}'>")
    parts.append("</body></html>")
    return "\n".join(parts), f"{stem}.html"


def _pdf_to_md_linked(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    img_dir = out_dir / f"{stem}_pages"
    img_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}\n"]
    pages = list(enumerate(doc, start=1))
    for i, page in progress(pages, desc="Rendering", unit="pg", position=1, leave=False):
        pix = page.get_pixmap(matrix=_RENDER_MAT)
        img_file = img_dir / f"page_{i:04d}.jpg"
        pix.save(str(img_file))
        rel = f"{stem}_pages/page_{i:04d}.jpg"
        lines.append(f"\n---\n\n## Page {i}\n\n![Page {i}]({rel})\n")
    return "\n".join(lines), f"{stem}_linked.md"


# ── registration ──────────────────────────────────────────────────────────────

register(ConversionFormat(
    key="1", name="Markdown — text only",
    description="Extracted text, structured by page. Fast, compact.",
    ext="md", source_ext=".pdf", convert=_pdf_to_md_text,
))
register(ConversionFormat(
    key="2", name="Markdown + embedded images (AI-ready)",
    description="Text + images as inline base64. Single file, but large for scanned books.",
    ext="md", source_ext=".pdf", convert=_pdf_to_md_ai,
))
register(ConversionFormat(
    key="3", name="Plain Text",
    description="Raw text only, no formatting.",
    ext="txt", source_ext=".pdf", convert=_pdf_to_txt,
))
register(ConversionFormat(
    key="4", name="Structured JSON",
    description="JSON: list of pages with text and separate image paths.",
    ext="json", source_ext=".pdf", convert=_pdf_to_json,
))
register(ConversionFormat(
    key="5", name="HTML with embedded images",
    description="HTML with inline base64 images. Openable in a browser.",
    ext="html", source_ext=".pdf", convert=_pdf_to_html,
))
register(ConversionFormat(
    key="6", name="Markdown + separate image files",
    description="Page images saved as files, referenced by path. No base64 — ideal for large scanned books.",
    ext="md", source_ext=".pdf", convert=_pdf_to_md_linked,
))
```

- [ ] **Step 2: Verify the module imports cleanly and format 7 is NOT registered by it**

```bash
cd /Users/giuseppecalvello/Documents/PdfReader && venv/bin/python3 -c "
import converters.pdf_to_formats as m
from converters.base import _registry
keys = sorted(_registry.keys())
print('Registered by pdf_to_formats:', keys)
assert '7' not in keys or 'ocr_pipeline' in str(type(list(_registry.values())[0]).__module__), 'format 7 still in pdf_to_formats'
print('OK')
"
```

Expected: prints registered keys (should NOT include 7 at this point, since `__init__.py` hasn't been updated yet — that's fine).

- [ ] **Step 3: Commit**

```bash
git add converters/pdf_to_formats.py
git commit -m "refactor: trim pdf_to_formats.py to formats 1-6; remove math/OCR code"
```

---

### Task 4: Update `converters/__init__.py` to import `ocr_pipeline`

The `__init__.py` triggers self-registration at import time. Format 7 now lives in `ocr_pipeline`, so it must be imported here.

**Files:**
- Modify: `converters/__init__.py`

- [ ] **Step 1: Replace the file content**

```python
from . import pdf_to_formats  # noqa: F401 — registers PDF → * formats (keys 1–6)
from . import ocr_pipeline    # noqa: F401 — registers PDF → OCR markdown (key 7)
from . import md_to_pdf       # noqa: F401 — registers MD → PDF format  (key 8)
```

- [ ] **Step 2: Verify all 8 formats register correctly**

```bash
cd /Users/giuseppecalvello/Documents/PdfReader && venv/bin/python3 -c "
import converters  # triggers all registrations
from converters.base import all_formats
fmts = all_formats()
keys = sorted(f.key for f in fmts)
print('Registered keys:', keys)
assert keys == ['1','2','3','4','5','6','7','8'], f'Expected 1-8, got {keys}'
print('All 8 formats registered correctly')
"
```

Expected output:
```
Registered keys: ['1', '2', '3', '4', '5', '6', '7', '8']
All 8 formats registered correctly
```

- [ ] **Step 3: Run format 1 (simple, no deps) to confirm the full pipeline works**

```bash
printf "1\n" | venv/bin/python3 main.py input_pdfs/9-Support_Vector_Machines.pdf 2>&1 | tail -3
```

Expected: line containing `✓  9-Support_Vector_Machines.pdf →`

- [ ] **Step 4: Run format 7 without pix2tex to confirm OCR pipeline still works**

```bash
printf "7\n\nn\n" | venv/bin/python3 main.py input_pdfs/9-Support_Vector_Machines.pdf 2>&1 | tail -3
```

Expected: line containing `✓  9-Support_Vector_Machines.pdf → 9-Support_Vector_Machines_ocr.md`

- [ ] **Step 5: Spot-check the output for no regressions (no ctrl chars on page 48)**

```bash
venv/bin/python3 -c "
import re
text = open('input_pdfs/output/9-Support_Vector_Machines_ocr.md').read()
pages = re.split(r'## Page \d+', text)
p = pages[48]
ctrl = [hex(ord(c)) for c in p if ord(c) < 0x20 and c not in '\t\n\r ']
pua  = [hex(ord(c)) for c in p if 0xf800 <= ord(c) <= 0xf8ff]
print(f'Page 48: ctrl={ctrl[:3]}, pua={pua[:3]}')
assert not ctrl and not pua, 'Regression: garbage chars found'
print('Clean')
"
```

Expected: `Page 48: ctrl=[], pua=[]` and `Clean`

- [ ] **Step 6: Commit**

```bash
git add converters/__init__.py
git commit -m "refactor: wire ocr_pipeline into __init__.py for format 7 registration"
```

---

### Task 5: Update `ARCHITECTURE.md`

Reflect the new three-module structure, updated single-responsibility table, and new dependency graph.

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Replace the file with updated content**

```markdown
# Architecture — File Converter

## Purpose

CLI tool that converts files (single file or folder) between formats. Designed as an **open, extensible conversion platform**: adding a new format requires writing one function and one `register()` call, touching zero existing files.

---

## Directory Layout

```text
PdfReader/
├── main.py                     # Entry point: wires menu → paths → converter
├── config/
│   └── config.py               # Global constants (DPI, fitz matrices)
├── converters/
│   ├── __init__.py             # Side-effect imports: triggers registration of all built-ins
│   ├── base.py                 # ConversionFormat dataclass + global registry
│   ├── pdf_to_formats.py       # Built-in PDF → * formats (keys 1–6): text, JSON, HTML, images
│   ├── math_helpers.py         # Math detection primitives: font sets, char filters, pix2tex wrapper
│   ├── ocr_pipeline.py         # OCR pipeline (format 7): text extraction + pix2tex integration
│   └── md_to_pdf.py            # Built-in MD → PDF format (key 8)
├── core/
│   └── core.py                 # convert_one() / convert_folder() — pure orchestration
├── menu/
│   └── menu.py                 # CLI menu, reads dynamically from registry
└── utils/
    └── utils.py                # progress() display + extract_images_b64()
```

---

## Design Principles

### Open/Closed Principle (OCP)

The system is **open for extension, closed for modification**.
Adding a new output format means:

1. Write a converter function.
2. Call `register(ConversionFormat(...))`.
3. Done — menu, dispatch, and folder-batch all pick it up automatically.

No existing file needs to change.

### Single Responsibility

| Module | Responsibility |
| --- | --- |
| `main.py` | Wires together menu, path resolution, and converter call |
| `converters/base.py` | Owns the registry contract and data structure |
| `converters/pdf_to_formats.py` | Implements and registers simple PDF → * formats (1–6): text, JSON, HTML, image links |
| `converters/math_helpers.py` | Low-level math detection: CM font recognition, CMEX char filtering, LaTeX validation, pix2tex wrapping |
| `converters/ocr_pipeline.py` | OCR pipeline: text block reconstruction, formula region detection, vector-page extraction; registers format 7 |
| `converters/md_to_pdf.py` | Implements and registers MD → PDF format (key 8) |
| `core/core.py` | Opens source files, dispatches to registry, writes output |
| `menu/menu.py` | Reads registry, renders menu, collects user input |
| `utils/utils.py` | Shared I/O helpers (progress bar, image extraction) |
| `config/config.py` | Rendering constants, fitz availability gate |

### Dependency Direction

```text
main.py
  ├── menu/menu.py      → converters/base.py (read registry)
  ├── core/core.py      → converters/base.py (get_format)
  │                     → utils/utils.py
  └── converters/
        ├── pdf_to_formats.py  → converters/base.py, config/config.py, utils/utils.py
        ├── math_helpers.py    → (no internal imports — leaf module)
        ├── ocr_pipeline.py    → converters/base.py, converters/math_helpers.py,
        │                         config/config.py, utils/utils.py
        └── md_to_pdf.py       → converters/base.py
```

`menu` and `core` depend only on `base` (the abstraction), never on concrete converter implementations. `math_helpers` is a pure leaf — it imports nothing from this project. `ocr_pipeline` imports from `math_helpers` but not from `pdf_to_formats`.

---

## Key Abstraction: `ConversionFormat`

Defined in `converters/base.py`:

```python
@dataclass
class ConversionFormat:
    key: str                                      # menu key (e.g. "1", "8")
    name: str                                     # display label
    description: str                              # one-line description shown in menu
    ext: str                                      # output file extension
    source_ext: str                               # input file extension (e.g. ".pdf", ".md")
    convert: Callable[..., tuple[str | bytes, str]]  # see contract below
    extra_args: Optional[Callable[[], dict]]      # optional: prompts user, returns kwargs
```

### Converter Function Contract

```python
def my_converter(
    doc,            # fitz.Document for .pdf sources; None for all other sources
    stem: str,      # source filename without extension
    out_dir: Path,  # directory where output should be written
    *,
    source_path: Path,  # always provided — original source file path
    **kwargs,           # extra args from extra_args()
) -> tuple[str | bytes, str]:
    ...
    return content, output_filename
```

| Parameter | Type | Description |
| --- | --- | --- |
| `doc` | `fitz.Document \| None` | Opened PDF doc, or `None` for non-PDF sources |
| `stem` | `str` | Source filename without extension |
| `out_dir` | `Path` | Directory where output files should be written |
| `source_path` | `Path` | Full path to source file (always passed as kwarg) |
| `**kwargs` | `dict` | Extra arguments collected by `extra_args()` |
| **Returns** | `(str \| bytes, str)` | `(file content, output filename)` |

`content` must be `str` for text formats and `bytes` for binary formats (e.g. PDF output). The orchestrator calls `write_text` or `write_bytes` accordingly.

The function may write auxiliary files (images, sub-dirs) as side effects. The returned content is always written to `out_dir / output_filename` by the orchestrator.

### `extra_args` Contract

```python
def my_extra_args() -> dict:
    value = input("Prompt user: ").strip()
    return {"my_kwarg": value}
```

Return a dict that will be unpacked as `**kwargs` into the converter call. Return `None` (default) if no extra input is needed.

---

## Design Patterns

### Registry Pattern

`_registry: dict[str, ConversionFormat]` in `converters/base.py` is a global map from format key to format descriptor. Converters self-register at import time via `register()`. The menu and orchestrator query it at runtime — neither hard-codes format keys.

### Strategy Pattern

`ConversionFormat.convert` is a strategy: a pluggable function that encapsulates one algorithm for producing output. `convert_one()` selects and invokes the strategy without knowing its internals.

### Plugin / Self-Registration

Each format registers itself when its module is imported. `converters/__init__.py` imports all built-in modules, firing their `register()` calls. Third-party formats follow the same pattern: write a module, import it before `show_menu()`, it appears in the menu.

---

## Adding a New Format (AI Instructions)

**Step 1** — Write the converter function in a new file (e.g. `converters/my_format.py`):

```python
from pathlib import Path
from converters.base import ConversionFormat, register

def _to_my_format(doc, stem: str, out_dir: Path, *, source_path: Path, **kwargs) -> tuple[str, str]:
    # doc is fitz.Document if source_ext=".pdf", else None
    # use source_path to read the source file for non-PDF inputs
    ...
    return content, f"{stem}.myext"

register(ConversionFormat(
    key="9",               # next available key
    name="My Format",
    description="One-line description shown in the menu.",
    ext="myext",
    source_ext=".pdf",     # or ".md", ".txt", etc.
    convert=_to_my_format,
    # extra_args=_my_extra_args,  # add if user input needed
))
```

**Step 2** — Register it by adding one line to `converters/__init__.py`:

```python
from . import my_format  # noqa: F401
```

**That's all.** No changes to `core/`, `menu/`, `config/`, or any existing converter.

If your format needs math detection or LaTeX conversion, import from `converters/math_helpers.py`:

```python
from converters.math_helpers import _is_math_font, _has_formula_chars, _try_latex
```

### Rules to maintain OCP

- Never add `if choice == "N":` branches anywhere.
- Never hardcode format keys or source extensions in `menu.py` or `core/core.py`.
- If a converter needs user input, use `extra_args` — do not special-case it in `menu.py`.
- For binary output (e.g. PDF), return `bytes` — the orchestrator handles `write_bytes` automatically.
- For non-PDF sources, use `source_path` to read the file; `doc` will be `None`.

---

## Dependencies

| Package | Used for |
| --- | --- |
| `pymupdf` (`fitz`) | PDF parsing, page rendering, image extraction, PDF generation |
| `tqdm` | Progress bars (graceful fallback if absent) |
| `markdown` | Markdown → HTML conversion (format 8) |
| `pytesseract` | OCR — format 7 only, optional |
| `Pillow` (`PIL`) | Image I/O for OCR pipeline — format 7 only, optional |
| `pix2tex` | Math formula OCR (LaTeX output) — format 7 math mode only, optional |

---

## Data Flow

```text
main.py
  │
  ├─ show_menu()          → returns (choice, extra_kwargs)
  ├─ get_format(choice)   → ConversionFormat (for source_ext validation)
  ├─ get_input_path()     → returns Path
  │
  └─ convert_one(source_path, out_dir, choice, **extra_kwargs)
       │
       ├─ get_format(choice)                                      → ConversionFormat
       ├─ fitz.open(source_path) if .pdf else None               → doc
       ├─ fmt.convert(doc, stem, out_dir, source_path=…, **kwargs) → (content, filename)
       └─ out_file.write_bytes(content)  OR  write_text(content)
```
```

- [ ] **Step 2: Verify the file looks correct (no broken markdown fences)**

```bash
grep -c "^```" /Users/giuseppecalvello/Documents/PdfReader/ARCHITECTURE.md
```

Expected: even number (every opening fence has a closing fence). Count should be 16 or 18.

- [ ] **Step 3: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs: update ARCHITECTURE.md for math_helpers/ocr_pipeline split"
```

---

### Task 6: Final smoke-test and push

Confirm the full system still works end-to-end after all four structural changes.

**Files:** none modified

- [ ] **Step 1: Confirm all 8 formats register**

```bash
cd /Users/giuseppecalvello/Documents/PdfReader && venv/bin/python3 -c "
import converters
from converters.base import all_formats
keys = sorted(f.key for f in all_formats())
assert keys == ['1','2','3','4','5','6','7','8'], f'Missing formats: {keys}'
print('All 8 formats present:', keys)
"
```

- [ ] **Step 2: Run format 7 without pix2tex, spot-check page 48 clean**

```bash
printf "7\n\nn\n" | venv/bin/python3 main.py input_pdfs/9-Support_Vector_Machines.pdf 2>&1 | tail -2

venv/bin/python3 -c "
import re
text = open('input_pdfs/output/9-Support_Vector_Machines_ocr.md').read()
pages = re.split(r'## Page \d+', text)
p = pages[48]
ctrl = [hex(ord(c)) for c in p if ord(c) < 0x20 and c not in '\t\n\r ']
pua  = [hex(ord(c)) for c in p if 0xf800 <= ord(c) <= 0xf8ff]
assert not ctrl and not pua, f'Regression: ctrl={ctrl} pua={pua}'
print('Page 48: CLEAN')
"
```

- [ ] **Step 3: Push**

```bash
git push
```

- [ ] **Step 4: Confirm push succeeded**

```bash
git log --oneline -6
```

Expected: top 4–5 commits are the refactor commits from this plan.

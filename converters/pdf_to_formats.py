"""converters/pdf_to_formats.py — built-in PDF → * formats, registered at import time"""

import json
import sys
from pathlib import Path

from config.config import _RENDER_MAT, _OCR_MAT
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


def _pdf_ocr_extra_args() -> dict:
    raw = input("OCR language (e.g. eng, ita, ita+eng) [default: ita+eng]: ").strip()
    lang = raw if raw else "ita+eng"
    print(f"→ OCR language: {lang}\n")

    math_raw = input("Enable math formula recognition via pix2tex? [y/N]: ").strip().lower()
    math_ocr = math_raw in ("y", "yes")
    if math_ocr:
        print("→ Math OCR enabled (requires: pip install pix2tex)\n")

    return {"lang": lang, "math_ocr": math_ocr}


_MATH_FONTS = {"CMEX", "CMMI", "CMSY", "MSAM", "MSBM", "EUFM", "RSFS", "STIX"}

_FORMULA_RENDER_MAT = None  # lazily init at 3× for pix2tex quality


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
    """True if text contains CMEX control chars or private-use-area bracket glyphs."""
    return any(
        (ord(c) < 0x20 and c not in '\t\n\r ')
        or (0xf800 <= ord(c) <= 0xf8ff)
        for c in text
    )


def _span_chars(span) -> str:
    return "".join(c["c"] for c in span.get("chars", []))


def _looks_like_formula(pil_img) -> bool:
    """Heuristic for raster-embedded formula images."""
    w, h = pil_img.size
    if w < 20 or h < 20:
        return False
    if w * h > 4_000_000:
        return False
    return 0.3 < w / h < 20


def _reconstruct_block_text(block) -> str:
    """
    Join a block's lines into text, reconstructing inline fractions.

    Detects fraction numerators by non-monotonic y0 in text-stream order:
    a short line (≤6 chars, no spaces) whose y0 < previous line's y0 is
    positioned above the baseline → it's a numerator; the following line
    is the denominator.  E.g. ['where C =', '1', 'nλ'] → 'where C = 1/nλ'.
    """
    import re as _re
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
            and not _re.search(r"[\s\x00-\x1f]", text)  # no spaces or control chars
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


def _is_valid_latex(latex: str) -> bool:
    """Reject outputs that are clearly garbage (excessive spacing commands)."""
    import re
    if not latex or not any(c in latex for c in r"\^_{}"):
        return False
    commands = re.findall(r"\\[a-zA-Z]+", latex)
    quad_count = sum(1 for c in commands if c in (r"\quad", r"\qquad"))
    return quad_count / max(1, len(commands)) < 0.4


def _try_latex(latex_model, pil_img) -> str | None:
    try:
        latex = latex_model(pil_img)
        if latex and _is_valid_latex(latex.strip()):
            return latex.strip()
    except Exception:
        pass
    return None


def _extract_vector_formula_regions(page, pad_h=8, pad_v=4, gap=25,
                                    max_chars=80, min_math_frac=0.10):
    """
    Detect display-formula regions in vector/text PDFs (e.g. LaTeX-compiled).

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
    """
    Convert a vector (text-based) PDF page to markdown.

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
                    # Place at vertical midpoint of bounding box for sorting
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
            for fy0, fy1, _ in formula_slots  # formula_slots only has valid LaTeX entries
        )
        if in_formula:
            continue
        import re as _re
        # Skip very small blocks (chart axis labels, stray annotations)
        bw = block["bbox"][2] - block["bbox"][0]
        bh = block["bbox"][3] - block["bbox"][1]
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
            and _re.search(r'[—–]', block_text)
            and _re.search(r'=\s*[\d.]', block_text)
        ):
            continue
        # Skip slide page-counter blocks like "3/64", "12/64"
        if _re.fullmatch(r"\d+/\d+", block_text.strip()):
            continue
        # Skip purely-numeric blocks (chart axis tick labels)
        block_lines_text = [
            "".join(s.get("text", "") for s in line["spans"]).strip()
            for line in block["lines"]
        ]
        if block_lines_text and all(
            _re.fullmatch(r"[-−]?\d+\.?\d*", t) for t in block_lines_text if t
        ):
            continue
        items.append((by0, block_text))

    # Add formula slots as items
    for fy0, fy1, latex in formula_slots:
        items.append((fy0, f"\n$$\n{latex}\n$$\n"))

    items.sort(key=lambda x: x[0])

    # Merge consecutive text items that are vertically close (same line / inline split)
    # When prev ends with math symbol and curr starts with digit, join with "/" (cross-block fraction).
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
register(ConversionFormat(
    key="7", name="Markdown + OCR text (pytesseract + optional math)",
    description="OCR via pytesseract; optionally adds LaTeX math via pix2tex. Requires: pip install pytesseract pillow + Tesseract binary. Math: pip install pix2tex.",
    ext="md", source_ext=".pdf", convert=_pdf_to_md_ocr, extra_args=_pdf_ocr_extra_args,
))

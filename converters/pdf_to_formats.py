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
    return {"lang": lang}


def _pdf_to_md_ocr(doc, stem: str, out_dir: Path, lang: str = "ita+eng", **_) -> tuple[str, str]:
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
    lines = [f"# {stem}\n"]
    pages = list(enumerate(doc, start=1))
    for i, page in progress(pages, desc="OCR", unit="pg", position=1, leave=False):
        pix = page.get_pixmap(matrix=_OCR_MAT)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang=lang).strip()
        if text:
            lines.append(f"\n---\n\n## Page {i}\n\n{text}\n")
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
    key="7", name="Markdown + OCR text (pytesseract)",
    description="OCR via pytesseract: extracts text from scanned pages. Requires: pip install pytesseract pillow + Tesseract binary.",
    ext="md", source_ext=".pdf", convert=_pdf_to_md_ocr, extra_args=_pdf_ocr_extra_args,
))

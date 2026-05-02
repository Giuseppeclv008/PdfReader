#!/usr/bin/env python3
"""pdf_converter.py — convert PDF(s) to multiple formats"""

import sys
import json
import base64
from pathlib import Path

try:
    import fitz  # pymupdf
except ImportError:
    sys.exit("Install: pip install pymupdf")

try:
    from tqdm import tqdm as _tqdm
    def _progress(iterable, position=0, leave=True, **kw):
        return _tqdm(iterable, position=position, leave=leave, **kw)
except ImportError:
    def _progress(iterable, desc="", leave=True, **_):
        items = list(iterable)
        for i, item in enumerate(items, start=1):
            print(f"  {desc} {i}/{len(items)}", end="\r", flush=True)
            yield item
        if leave:
            print()


FORMATS = {
    "1": ("Markdown — text only",                    "md"),
    "2": ("Markdown + embedded images (AI-ready)",   "md"),
    "3": ("Plain Text",                               "txt"),
    "4": ("Structured JSON",                          "json"),
    "5": ("HTML with embedded images",               "html"),
    "6": ("Markdown + separate image files",         "md"),
    "7": ("Markdown + OCR text (pytesseract)",       "md"),
}

FORMAT_DESCRIPTIONS = {
    "1": "Extracted text, structured by page. Fast, compact.",
    "2": "Text + images as inline base64. Single file, but large for scanned books.",
    "3": "Raw text only, no formatting.",
    "4": "JSON: list of pages with text and separate image paths.",
    "5": "HTML with inline base64 images. Openable in a browser.",
    "6": "Page images saved as separate files, referenced by path in markdown. No base64 — ideal for large scanned books.",
    "7": "OCR via pytesseract: extracts text from scanned pages. Pure text, minimal tokens. Requires: pip install pytesseract pillow + Tesseract binary.",
}

# DPI used when rendering pages to images (formats 6 and 7)
_RENDER_DPI = 150
_OCR_DPI    = 200
_RENDER_MAT = fitz.Matrix(_RENDER_DPI / 72, _RENDER_DPI / 72)
_OCR_MAT    = fitz.Matrix(_OCR_DPI / 72,    _OCR_DPI / 72)


def show_menu() -> tuple[str, str, str | None]:
    print("\n" + "=" * 55)
    print("            PDF CONVERTER — Choose format")
    print("=" * 55)
    for key, (name, ext) in FORMATS.items():
        print(f"  {key}. {name}")
        print(f"     └─ {FORMAT_DESCRIPTIONS[key]}")
    print("=" * 55)

    while True:
        choice = input("Choice [1-7]: ").strip()
        if choice in FORMATS:
            name, ext = FORMATS[choice]
            print(f"\n→ Format: {name}\n")
            ocr_lang = None
            if choice == "7":
                raw = input("OCR language (e.g. eng, ita, ita+eng) [default: ita+eng]: ").strip()
                ocr_lang = raw if raw else "ita+eng"
                print(f"→ OCR language: {ocr_lang}\n")
            return choice, ext, ocr_lang
        print("  Enter a number between 1 and 7.")


def get_input_path() -> Path:
    while True:
        raw = input("Path to PDF file or folder: ").strip().strip("'\"")
        p = Path(raw).expanduser()
        if p.exists():
            return p
        print(f"  Not found: {p}")


def extract_images_b64(page) -> list[str]:
    images = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            base_image = page.parent.extract_image(xref)
            img_bytes = base_image["image"]
            ext = base_image.get("ext", "png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(f"data:image/{ext};base64,{b64}")
        except Exception:
            pass
    return images


# ── converters ──────────────────────────────────────────────────────────────

def to_md_text(doc, stem: str) -> str:
    lines = [f"# {stem}\n"]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            lines.append(f"\n---\n\n## Page {i}\n\n{text}\n")
    return "\n".join(lines)


def to_md_ai(doc, stem: str) -> str:
    lines = [f"# {stem}\n"]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        images = extract_images_b64(page)
        lines.append(f"\n---\n\n## Page {i}\n")
        if text:
            lines.append(f"\n{text}\n")
        for j, data_uri in enumerate(images, start=1):
            lines.append(f"\n![Page {i} — Image {j}]({data_uri})\n")
    return "\n".join(lines)


def to_txt(doc) -> str:
    parts = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            parts.append(f"[Page {i}]\n{text}")
    return "\n\n".join(parts)


def to_json(doc, stem: str, out_dir: Path) -> str:
    pages = []
    img_dir = out_dir / f"{stem}_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        img_paths = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                ext = base_image.get("ext", "png")
                img_file = img_dir / f"p{i}_img{len(img_paths)+1}.{ext}"
                img_file.write_bytes(base_image["image"])
                img_paths.append(str(img_file))
            except Exception:
                pass
        pages.append({"page": i, "text": text, "images": img_paths})
    return json.dumps({"document": stem, "pages": pages}, ensure_ascii=False, indent=2)


def to_html(doc, stem: str) -> str:
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
    return "\n".join(parts)


def to_md_linked(doc, stem: str, out_dir: Path) -> str:
    """Render each page as a JPEG file, reference by relative path — no base64."""
    img_dir = out_dir / f"{stem}_pages"
    img_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}\n"]
    pages = list(enumerate(doc, start=1))
    for i, page in _progress(pages, desc="Rendering", unit="pg", position=1, leave=False):
        pix = page.get_pixmap(matrix=_RENDER_MAT)
        img_file = img_dir / f"page_{i:04d}.jpg"
        pix.save(str(img_file))
        rel = f"{stem}_pages/page_{i:04d}.jpg"
        lines.append(f"\n---\n\n## Page {i}\n\n![Page {i}]({rel})\n")
    return "\n".join(lines)


def to_md_ocr(doc, stem: str, lang: str) -> str:
    """OCR each page with pytesseract and write extracted text to markdown."""
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        sys.exit(
            "Format 7 requires extra packages:\n"
            "  pip install pytesseract pillow\n"
            "  + install Tesseract binary: https://tesseract-ocr.github.io/tessdoc/Installation.html"
        )

    lines = [f"# {stem}\n"]
    pages = list(enumerate(doc, start=1))
    for i, page in _progress(pages, desc="OCR", unit="pg", position=1, leave=False):
        pix = page.get_pixmap(matrix=_OCR_MAT)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang=lang).strip()
        if text:
            lines.append(f"\n---\n\n## Page {i}\n\n{text}\n")
    return "\n".join(lines)


# ── core convert ─────────────────────────────────────────────────────────────

def convert_one(pdf_path: Path, out_dir: Path, choice: str, ext: str, ocr_lang: str | None = None) -> None:
    doc = fitz.open(str(pdf_path))
    stem = pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    if choice == "1":
        content = to_md_text(doc, stem)
        out_file = out_dir / f"{stem}.{ext}"
        out_file.write_text(content, encoding="utf-8")

    elif choice == "2":
        content = to_md_ai(doc, stem)
        out_file = out_dir / f"{stem}_ai.{ext}"
        out_file.write_text(content, encoding="utf-8")

    elif choice == "3":
        content = to_txt(doc)
        out_file = out_dir / f"{stem}.{ext}"
        out_file.write_text(content, encoding="utf-8")

    elif choice == "4":
        content = to_json(doc, stem, out_dir)
        out_file = out_dir / f"{stem}.{ext}"
        out_file.write_text(content, encoding="utf-8")

    elif choice == "5":
        content = to_html(doc, stem)
        out_file = out_dir / f"{stem}.{ext}"
        out_file.write_text(content, encoding="utf-8")

    elif choice == "6":
        content = to_md_linked(doc, stem, out_dir)
        out_file = out_dir / f"{stem}_linked.{ext}"
        out_file.write_text(content, encoding="utf-8")

    elif choice == "7":
        content = to_md_ocr(doc, stem, ocr_lang)
        out_file = out_dir / f"{stem}_ocr.{ext}"
        out_file.write_text(content, encoding="utf-8")

    doc.close()
    print(f"  ✓  {pdf_path.name} → {out_file.name}")


def convert_folder(folder: Path, out_dir: Path, choice: str, ext: str, ocr_lang: str | None = None) -> None:
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {folder}")
    print(f"Found {len(pdfs)} PDF(s) — output in: {out_dir}\n")
    errors = 0
    for pdf in _progress(pdfs, desc="Files", unit="pdf", position=0, leave=True):
        try:
            convert_one(pdf, out_dir, choice, ext, ocr_lang)
        except Exception as e:
            print(f"  ✗  {pdf.name}: {e}")
            errors += 1
    print(f"\nDone. {len(pdfs) - errors}/{len(pdfs)} converted.")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    choice, ext, ocr_lang = show_menu()

    # input path: from args or interactive prompt
    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1]).expanduser()
        if not input_path.exists():
            sys.exit(f"Not found: {input_path}")
    else:
        input_path = get_input_path()

    # output dir: from args, or default next to input
    if len(sys.argv) >= 3:
        out_dir = Path(sys.argv[2]).expanduser()
    else:
        if input_path.is_dir():
            out_dir = input_path.parent / f"{input_path.name}_output"
        else:
            out_dir = input_path.parent / "output"

    if input_path.is_dir():
        convert_folder(input_path, out_dir, choice, ext, ocr_lang)
    elif input_path.suffix.lower() == ".pdf":
        convert_one(input_path, out_dir, choice, ext, ocr_lang)
    else:
        sys.exit(f"Invalid input (expected .pdf file or folder): {input_path}")

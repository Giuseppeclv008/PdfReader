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


FORMATS = {
    "1": ("Markdown — text only",                    "md"),
    "2": ("Markdown + immagini embedded (AI-ready)", "md"),
    "3": ("Plain Text",                               "txt"),
    "4": ("JSON strutturato",                         "json"),
    "5": ("HTML con immagini embedded",               "html"),
}

FORMAT_DESCRIPTIONS = {
    "1": "Testo estratto, struttura per pagine. Veloce, compatto.",
    "2": "Testo + immagini come base64 inline. AI legge tutto in un file senza pre-processing.",
    "3": "Solo testo grezzo, nessuna formattazione.",
    "4": "JSON: lista pagine con testo e path immagini separate.",
    "5": "HTML con immagini base64 inline. Apribile su browser.",
}


def show_menu() -> tuple[str, str]:
    print("\n" + "=" * 45)
    print("         PDF CONVERTER — Scegli formato")
    print("=" * 45)
    for key, (name, ext) in FORMATS.items():
        print(f"  {key}. {name}")
        print(f"     └─ {FORMAT_DESCRIPTIONS[key]}")
    print("=" * 45)

    while True:
        choice = input("Scelta [1-5]: ").strip()
        if choice in FORMATS:
            name, ext = FORMATS[choice]
            print(f"\n→ Formato: {name}\n")
            return choice, ext
        print("  Inserisci un numero tra 1 e 5.")


def get_input_path() -> Path:
    while True:
        raw = input("Percorso file PDF o cartella: ").strip().strip("'\"")
        p = Path(raw).expanduser()
        if p.exists():
            return p
        print(f"  Non trovato: {p}")


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
            lines.append(f"\n---\n\n## Pagina {i}\n\n{text}\n")
    return "\n".join(lines)


def to_md_ai(doc, stem: str) -> str:
    lines = [f"# {stem}\n"]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        images = extract_images_b64(page)
        lines.append(f"\n---\n\n## Pagina {i}\n")
        if text:
            lines.append(f"\n{text}\n")
        for j, data_uri in enumerate(images, start=1):
            lines.append(f"\n![Pagina {i} — Immagine {j}]({data_uri})\n")
    return "\n".join(lines)


def to_txt(doc) -> str:
    parts = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            parts.append(f"[Pagina {i}]\n{text}")
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
        parts.append(f"<hr><h2>Pagina {i}</h2>")
        if text:
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append(f"<pre>{escaped}</pre>")
        for data_uri in images:
            parts.append(f"<img src='{data_uri}' alt='Pagina {i}'>")
    parts.append("</body></html>")
    return "\n".join(parts)


# ── core convert ─────────────────────────────────────────────────────────────

def convert_one(pdf_path: Path, out_dir: Path, choice: str, ext: str) -> None:
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

    doc.close()
    print(f"  ✓  {pdf_path.name} → {out_file.name}")


def convert_folder(folder: Path, out_dir: Path, choice: str, ext: str) -> None:
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"Nessun PDF in {folder}")
    print(f"Trovati {len(pdfs)} PDF — output in: {out_dir}\n")
    errors = 0
    for pdf in pdfs:
        try:
            convert_one(pdf, out_dir, choice, ext)
        except Exception as e:
            print(f"  ✗  {pdf.name}: {e}")
            errors += 1
    print(f"\nFine. {len(pdfs) - errors}/{len(pdfs)} convertiti.")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    choice, ext = show_menu()

    # input path: da args o prompt
    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1]).expanduser()
        if not input_path.exists():
            sys.exit(f"Non trovato: {input_path}")
    else:
        input_path = get_input_path()

    # output dir: da args, o default accanto all'input
    if len(sys.argv) >= 3:
        out_dir = Path(sys.argv[2]).expanduser()
    else:
        if input_path.is_dir():
            out_dir = input_path.parent / f"{input_path.name}_output"
        else:
            out_dir = input_path.parent / "output"

    if input_path.is_dir():
        convert_folder(input_path, out_dir, choice, ext)
    elif input_path.suffix.lower() == ".pdf":
        convert_one(input_path, out_dir, choice, ext)
    else:
        sys.exit(f"Input non valido (serve .pdf o cartella): {input_path}")

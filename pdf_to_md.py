#!/usr/bin/env python3
"""pdf_to_md.py — convert PDF(s) to Markdown"""

import sys
from pathlib import Path

try:
    import fitz  # pymupdf
except ImportError:
    sys.exit("Install: pip install pymupdf")


def pdf_to_md(pdf_path: Path, output_path: Path = None) -> None:
    if not pdf_path.exists():
        sys.exit(f"File not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        sys.exit(f"Not a PDF: {pdf_path}")

    if output_path is None:
        md_path = pdf_path.with_suffix(".md")
    else:
        output_path.mkdir(parents=True, exist_ok=True)
        md_path = output_path / f"{pdf_path.stem}.md"

    doc = fitz.open(str(pdf_path))
    lines = [f"# {pdf_path.stem}\n"]

    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            lines.append(f"\n---\n\n## Page {i}\n\n{text}\n")

    doc.close()

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ {pdf_path.name} → {md_path.name}")


def convert_folder(input_folder: str, output_folder: str) -> None:
    src = Path(input_folder)
    dst = Path(output_folder)

    if not src.exists() or not src.is_dir():
        sys.exit(f"Folder not found: {input_folder}")

    pdfs = list(src.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs in {input_folder}")

    dst.mkdir(parents=True, exist_ok=True)
    print(f"Converting {len(pdfs)} PDF(s) → {output_folder}\n")

    for pdf in sorted(pdfs):
        try:
            pdf_to_md(pdf, dst)
        except Exception as e:
            print(f"✗ {pdf.name}: {e}")

    print(f"\nDone. {len(pdfs)} file(s) converted.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(
            "Usage:\n"
            "  Single file:  python3 pdf_to_md.py <file.pdf>\n"
            "  Folder:       python3 pdf_to_md.py <input_folder> <output_folder>"
        )

    if len(sys.argv) == 2:
        pdf_to_md(Path(sys.argv[1]))
    else:
        convert_folder(sys.argv[1], sys.argv[2])

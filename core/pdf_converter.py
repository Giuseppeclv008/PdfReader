"""core/pdf_converter.py — orchestrate single-file and folder conversions"""

import sys
from pathlib import Path

import fitz

from converters.base import get_format
from utils.utils import progress


def convert_one(pdf_path: Path, out_dir: Path, choice: str, **kwargs) -> None:
    fmt = get_format(choice)
    doc = fitz.open(str(pdf_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    content, filename = fmt.convert(doc, pdf_path.stem, out_dir, **kwargs)
    out_file = out_dir / filename
    out_file.write_text(content, encoding="utf-8")
    doc.close()
    print(f"  ✓  {pdf_path.name} → {filename}")


def convert_folder(folder: Path, out_dir: Path, choice: str, **kwargs) -> None:
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {folder}")
    print(f"Found {len(pdfs)} PDF(s) — output in: {out_dir}\n")
    errors = 0
    for pdf in progress(pdfs, desc="Files", unit="pdf", position=0, leave=True):
        try:
            convert_one(pdf, out_dir, choice, **kwargs)
        except Exception as e:
            print(f"  ✗  {pdf.name}: {e}")
            errors += 1
    print(f"\nDone. {len(pdfs) - errors}/{len(pdfs)} converted.")

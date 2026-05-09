"""core/core.py — orchestrate single-file and folder conversions"""

import sys
import traceback
from pathlib import Path

import fitz

from converters.base import get_format
from utils.utils import progress

# Text-based formats that need extractable text in the source PDF.
# Format 7 (OCR) handles scanned PDFs natively, so it's excluded.
_TEXT_DEPENDENT_FORMATS = {"1", "2", "3", "4", "5", "6"}


def _pdf_is_scanned(doc) -> bool:
    """True if no page in the PDF has extractable text (image-only / scanned)."""
    return not any(page.get_text("text").strip() for page in doc)


def _diagnose_pdf(doc, choice: str) -> str | None:
    """Return a human-readable warning if the PDF + chosen format are incompatible."""
    if doc is None:
        return None
    if choice in _TEXT_DEPENDENT_FORMATS and _pdf_is_scanned(doc):
        return (
            "scanned PDF (no extractable text) — "
            "format will produce empty/imageless output. Use format 7 (OCR) instead."
        )
    return None


def convert_one(source_path: Path, out_dir: Path, choice: str, **kwargs) -> None:
    """Convert a single file and save the output."""
    fmt = get_format(choice)
    doc = fitz.open(str(source_path)) if source_path.suffix.lower() == ".pdf" else None
    out_dir.mkdir(parents=True, exist_ok=True)

    warning = _diagnose_pdf(doc, choice)
    if warning:
        print(f"  ⚠  {source_path.name}: {warning}")

    content, filename = fmt.convert(doc, source_path.stem, out_dir, source_path=source_path, **kwargs)
    if doc is not None:
        doc.close()
    out_file = out_dir / filename
    if isinstance(content, bytes):
        out_file.write_bytes(content)
    else:
        out_file.write_text(content, encoding="utf-8")
    print(f"  ✓  {source_path.name} → {filename}")


def convert_folder(folder: Path, out_dir: Path, choice: str, **kwargs) -> None:
    """Convert all files of the chosen format in the given folder."""
    fmt = get_format(choice)
    files = sorted(folder.glob(f"*{fmt.source_ext}"))
    if not files:
        sys.exit(f"No {fmt.source_ext} files found in {folder}")
    print(f"Found {len(files)} {fmt.source_ext} file(s) — output in: {out_dir}\n")
    errors: list[tuple[str, str]] = []
    for f in progress(files, desc="Files", unit="file", position=0, leave=True):
        try:
            convert_one(f, out_dir, choice, **kwargs)
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            print(f"  ✗  {f.name}: {reason}")
            traceback.print_exc(file=sys.stderr)
            errors.append((f.name, reason))

    print(f"\nDone. {len(files) - len(errors)}/{len(files)} converted.")
    if errors:
        print("\nFailed files:")
        for name, reason in errors:
            print(f"  - {name}: {reason}")

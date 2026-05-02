"""core/core.py — orchestrate single-file and folder conversions"""

import sys
from pathlib import Path

import fitz

from converters.base import get_format
from utils.utils import progress


def convert_one(source_path: Path, out_dir: Path, choice: str, **kwargs) -> None:
    fmt = get_format(choice)
    doc = fitz.open(str(source_path)) if source_path.suffix.lower() == ".pdf" else None
    out_dir.mkdir(parents=True, exist_ok=True)
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
    fmt = get_format(choice)
    files = sorted(folder.glob(f"*{fmt.source_ext}"))
    if not files:
        sys.exit(f"No {fmt.source_ext} files found in {folder}")
    print(f"Found {len(files)} {fmt.source_ext} file(s) — output in: {out_dir}\n")
    errors = 0
    for f in progress(files, desc="Files", unit="file", position=0, leave=True):
        try:
            convert_one(f, out_dir, choice, **kwargs)
        except Exception as e:
            print(f"  ✗  {f.name}: {e}")
            errors += 1
    print(f"\nDone. {len(files) - errors}/{len(files)} converted.")

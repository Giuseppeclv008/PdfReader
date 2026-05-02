"""converters/md_to_pdf.py — Markdown → PDF via fitz.Story + markdown library"""

import io
import sys
from pathlib import Path

import fitz

from converters.base import ConversionFormat, register

try:
    import markdown as _markdown
    _MD_AVAILABLE = True
except ImportError:
    _MD_AVAILABLE = False


def _md_to_pdf(doc, stem: str, out_dir: Path, source_path: Path, **_) -> tuple[bytes, str]:
    if not _MD_AVAILABLE:
        sys.exit("Format 8 requires: pip install markdown")

    md_text = source_path.read_text(encoding="utf-8")
    html = _markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )

    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    story = fitz.Story(html=f"<html><body>{html}</body></html>")
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (50, 50, -50, -50)  # 50pt margins

    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()

    writer.close()
    return buf.getvalue(), f"{stem}.pdf"


register(ConversionFormat(
    key="8",
    name="Markdown → PDF",
    description="Convert a Markdown file to a formatted A4 PDF. Requires: pip install markdown",
    ext="pdf",
    source_ext=".md",
    convert=_md_to_pdf,
))

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

# Stylesheet applied to every page — preserves all common Markdown elements.
# fitz.Story supports a subset of CSS; properties below are all supported.
_CSS = """
body       { font-family: sans-serif; font-size: 11pt; line-height: 1.6; }

h1         { font-size: 22pt; font-weight: bold;   margin-top: 18pt; margin-bottom: 6pt; }
h2         { font-size: 17pt; font-weight: bold;   margin-top: 14pt; margin-bottom: 4pt; }
h3         { font-size: 13pt; font-weight: bold;   margin-top: 10pt; margin-bottom: 3pt; }
h4         { font-size: 11pt; font-weight: bold;   margin-top:  8pt; margin-bottom: 2pt; }

pre        { font-family: monospace; font-size: 9pt; background-color: #f5f5f5;
             padding: 8pt; margin: 6pt 0; border-left: 3pt solid #999;
             white-space: pre-wrap; }
code       { font-family: monospace; font-size: 9pt; background-color: #f5f5f5;
             padding: 1pt 3pt; }

blockquote { margin-left: 12pt; padding-left: 8pt; border-left: 3pt solid #cccccc;
             color: #555555; font-style: italic; }

table      { border-collapse: collapse; margin: 8pt 0; width: 100%; }
th         { background-color: #eeeeee; font-weight: bold;
             border: 1pt solid #bbbbbb; padding: 4pt 8pt; }
td         { border: 1pt solid #bbbbbb; padding: 4pt 8pt; }

ul, ol     { margin-left: 16pt; margin-top: 4pt; margin-bottom: 4pt; }
li         { margin-bottom: 2pt; }

hr         { border-top: 1pt solid #cccccc; margin: 10pt 0; }

strong     { font-weight: bold; }
em         { font-style: italic; }
"""


def _md_to_pdf(doc, stem: str, out_dir: Path, source_path: Path, **_) -> tuple[bytes, str]:
    if not _MD_AVAILABLE:
        sys.exit("Format 8 requires: pip install markdown")

    md_text = source_path.read_text(encoding="utf-8")
    html_body = _markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br", "def_list", "attr_list"],
    )

    full_html = f"<html><head><style>{_CSS}</style></head><body>{html_body}</body></html>"

    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    story = fitz.Story(html=full_html)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (50, 50, -50, -50)  # 50pt margins on all sides

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
    description="Convert a Markdown file to a formatted A4 PDF. Preserves code blocks, tables, headings, lists. Requires: pip install markdown",
    ext="pdf",
    source_ext=".md",
    convert=_md_to_pdf,
))

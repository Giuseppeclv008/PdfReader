"""converters/table_helpers.py — table detection on scanned pages via img2table.

Optional dependency: `pip install img2table`. Detects ruled and borderless
tables in a rendered page image, returns markdown pipe tables plus the
pixel bboxes so the caller can mask those regions before flat-page OCR.
"""

import io
import sys

_POLARS_PATCHED = False


def _patch_polars_dicts_kwarg() -> None:
    """img2table 0.0.12 calls `pl.from_dicts(dicts=...)`; polars renamed it to `data=`.

    Wrap from_dicts so the legacy kwarg keeps working without forking img2table.
    Idempotent — safe to call repeatedly.
    """
    global _POLARS_PATCHED
    if _POLARS_PATCHED:
        return
    try:
        import polars as pl
    except ImportError:
        return
    orig = pl.from_dicts

    def _shim(*args, **kwargs):
        if "dicts" in kwargs and "data" not in kwargs:
            kwargs["data"] = kwargs.pop("dicts")
        return orig(*args, **kwargs)

    pl.from_dicts = _shim
    _POLARS_PATCHED = True


def extract_tables_md(pil_img, lang: str, min_confidence: int = 50):
    """Detect tables in `pil_img`; return (md_strings, pixel_bboxes).

    Both lists are aligned by index. md_strings are markdown pipe tables.
    pixel_bboxes are (x0, y0, x1, y1) in `pil_img` coordinates so the
    caller can paint them out before running flat-page OCR.

    Returns ([], []) silently if img2table isn't installed or detection fails.
    """
    try:
        _patch_polars_dicts_kwarg()
        from img2table.document import Image as TableImage
        from img2table.ocr import TesseractOCR
    except ImportError:
        print(
            "[warn] table extraction requires `pip install img2table` — skipping",
            file=sys.stderr,
        )
        return [], []

    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)

    try:
        ocr = TesseractOCR(lang=lang)
        doc = TableImage(src=buf)
        tables = doc.extract_tables(
            ocr=ocr, implicit_rows=True, min_confidence=min_confidence
        )
    except Exception as e:
        print(
            f"[warn] table detection failed ({type(e).__name__}: {e})",
            file=sys.stderr,
        )
        return [], []

    md_tables: list[str] = []
    bboxes: list[tuple[int, int, int, int]] = []
    for t in tables:
        md = _df_to_markdown(t.df)
        if not md:
            continue
        md_tables.append(md)
        bboxes.append((t.bbox.x1, t.bbox.y1, t.bbox.x2, t.bbox.y2))
    return md_tables, bboxes


def _df_to_markdown(df) -> str:
    """Render a pandas DataFrame as a markdown pipe table.

    Treats the first row as the header. Empty/None cells become "".
    Pipe characters in cell text are escaped; embedded newlines collapsed.
    """
    if df is None or df.empty:
        return ""

    rows = df.fillna("").astype(str).values.tolist()
    if not rows:
        return ""

    def clean(s: str) -> str:
        return s.replace("\n", " ").replace("|", "\\|").strip()

    header = [clean(c) for c in rows[0]]
    body = [[clean(c) for c in row] for row in rows[1:]]

    if not any(header):
        return ""

    header_md = "| " + " | ".join(header) + " |"
    sep_md = "| " + " | ".join("---" for _ in header) + " |"
    if not body:
        return f"{header_md}\n{sep_md}"
    body_md = "\n".join("| " + " | ".join(row) + " |" for row in body)
    return f"{header_md}\n{sep_md}\n{body_md}"


def mask_regions(pil_img, bboxes):
    """Return a copy of `pil_img` with each bbox painted white.

    Lets the caller run flat OCR on everything that isn't a table without
    duplicating cell text in both the prose and the table output.
    """
    if not bboxes:
        return pil_img
    from PIL import ImageDraw

    out = pil_img.copy()
    draw = ImageDraw.Draw(out)
    fill = 255 if out.mode == "L" else (255, 255, 255)
    for x0, y0, x1, y1 in bboxes:
        draw.rectangle([x0, y0, x1, y1], fill=fill)
    return out

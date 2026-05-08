# Hybrid Text+Image Markdown (Format 9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add format 9 — a block-level hybrid markdown converter that emits readable text for clean blocks and a PNG crop + warning callout for formula/image blocks, saving crops to `<stem>_blocks/`.

**Architecture:** Single new file `converters/hybrid_pipeline.py` implements all logic and self-registers as format 9. Classification reuses `_has_formula_chars` and `_is_math_font` from `math_helpers.py`. One import line added to `converters/__init__.py`. No other existing files modified.

**Tech Stack:** PyMuPDF (fitz, already installed), pytest (new dev dependency for tests)

---

### Task 1: Test infrastructure + unit tests for `_block_should_skip`

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_hybrid_pipeline.py`

- [ ] **Step 1: Install pytest**

```bash
source venv/bin/activate && pip install pytest
```

Expected: `Successfully installed pytest-...` (or "already satisfied")

- [ ] **Step 2: Create test infrastructure**

Create `tests/__init__.py` — empty file.

Create `tests/conftest.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 3: Write failing tests for `_block_should_skip`**

Create `tests/test_hybrid_pipeline.py`:
```python
import pytest
from converters.hybrid_pipeline import (
    _block_should_skip,
    _block_is_legible,
    _math_font_fraction,
    _render_block_png,
    _pdf_to_md_hybrid,
)


def test_skip_pure_numeric_block():
    assert _block_should_skip("0\n1\n2\n3") is True


def test_skip_negative_numeric_block():
    assert _block_should_skip("-1.5\n0.0\n1.5") is True


def test_skip_page_counter():
    assert _block_should_skip("3/64") is True


def test_skip_chart_legend():
    assert _block_should_skip("Model A — param = 0.5") is True


def test_no_skip_normal_text():
    assert _block_should_skip("Il teorema di Bayes afferma che") is False


def test_no_skip_mixed_text():
    assert _block_should_skip("Capitolo 3: Analisi dei risultati") is False
```

- [ ] **Step 4: Run tests, verify they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError: No module named 'converters.hybrid_pipeline'`

---

### Task 2: Create `hybrid_pipeline.py` + implement `_block_should_skip`

**Files:**
- Create: `converters/hybrid_pipeline.py`

- [ ] **Step 1: Create `converters/hybrid_pipeline.py`**

```python
"""converters/hybrid_pipeline.py — Hybrid text+image markdown converter (format 9).

Per-block strategy:
- Good text blocks  → plain markdown text
- Bad blocks (formula garbage, dominant math fonts) → warning callout + text + PNG crop
- Image blocks (type 1) → PNG crop only
- Chart noise (axis labels, legends, page counters) → skipped entirely
- Scanned pages (no extractable text) → full-page PNG
"""

import re
import sys
from pathlib import Path

from converters.math_helpers import _has_formula_chars, _is_math_font
from converters.base import ConversionFormat, register
from utils.utils import progress


def _block_should_skip(block_text: str) -> bool:
    """True if block is chart noise — axis labels, legends, or page counters."""
    lines = [line.strip() for line in block_text.splitlines() if line.strip()]
    # Pure numeric lines (chart axis tick labels)
    if lines and all(re.fullmatch(r"[-−]?\d+\.?\d*", t) for t in lines):
        return True
    # Chart legend: single short line with em-dash and "= value"
    if (
        len(lines) == 1
        and len(block_text.strip()) <= 60
        and re.search(r'[—–]', block_text)
        and re.search(r'=\s*[\d.]', block_text)
    ):
        return True
    # Slide page counter "3/64"
    if re.fullmatch(r"\d+/\d+", block_text.strip()):
        return True
    return False
```

- [ ] **Step 2: Run tests, verify `_block_should_skip` tests pass**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py -k "skip" -v
```

Expected: 4 PASSED (skip tests), remaining tests still fail with ImportError (functions not yet defined)

- [ ] **Step 3: Commit**

```bash
git add converters/hybrid_pipeline.py tests/__init__.py tests/conftest.py tests/test_hybrid_pipeline.py
git commit -m "feat: scaffold hybrid_pipeline with _block_should_skip + unit tests"
```

---

### Task 3: Implement `_math_font_fraction` and `_block_is_legible`

**Files:**
- Modify: `converters/hybrid_pipeline.py`
- Modify: `tests/test_hybrid_pipeline.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_hybrid_pipeline.py`:
```python


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_block(text, font="Helvetica", bbox=(0.0, 0.0, 200.0, 20.0)):
    return {
        "type": 0,
        "bbox": bbox,
        "lines": [{
            "bbox": bbox,
            "spans": [{
                "text": text,
                "font": font,
                "bbox": bbox,
                "chars": [{"c": c} for c in text],
            }]
        }]
    }


def test_math_font_fraction_zero_for_normal_font():
    block = _make_block("hello world", font="Helvetica")
    assert _math_font_fraction(block) == 0.0


def test_math_font_fraction_one_for_cmmi():
    block = _make_block("abc", font="CMMI10")
    assert _math_font_fraction(block) == 1.0


def test_legible_normal_text():
    block = _make_block("Questo è un testo normale.")
    assert _block_is_legible(block, "Questo è un testo normale.") is True


def test_not_legible_cmex_chars():
    text = "abc\x00def"
    block = _make_block(text)
    assert _block_is_legible(block, text) is False


def test_not_legible_math_font_dominant():
    block = _make_block("abcde", font="CMMI10")
    assert _block_is_legible(block, "abcde") is False
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py -k "math_font or legible" -v 2>&1 | head -20
```

Expected: errors (functions not yet defined)

- [ ] **Step 3: Append `_math_font_fraction` and `_block_is_legible` to `converters/hybrid_pipeline.py`**

```python


def _math_font_fraction(block) -> float:
    """Fraction of chars in block rendered with math fonts (CM, STIX, etc.)."""
    total = math_chars = 0
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = span.get("text", "")
            total += len(t)
            if _is_math_font(span.get("font", "")):
                math_chars += len(t)
    return math_chars / total if total > 0 else 0.0


def _block_is_legible(block, block_text: str) -> bool:
    """True if block text is human-readable (no CMEX garbage, no dominant math fonts)."""
    if _has_formula_chars(block_text):
        return False
    if _math_font_fraction(block) > 0.30:
        return False
    return True
```

- [ ] **Step 4: Run all tests, verify pass**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py -v
```

Expected: 11 PASSED (skip tests + math_font + legible tests), remaining import errors only for `_render_block_png` and `_pdf_to_md_hybrid`

- [ ] **Step 5: Commit**

```bash
git add converters/hybrid_pipeline.py tests/test_hybrid_pipeline.py
git commit -m "feat: add _math_font_fraction and _block_is_legible with tests"
```

---

### Task 4: Implement `_render_block_png`

**Files:**
- Modify: `converters/hybrid_pipeline.py`
- Modify: `tests/test_hybrid_pipeline.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_hybrid_pipeline.py`:
```python


def test_render_block_png_creates_file(tmp_path):
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((10, 50), "Hello", fontsize=12)
    mat = fitz.Matrix(2, 2)
    block = {"bbox": (0.0, 0.0, 200.0, 100.0), "type": 0}
    out = tmp_path / "block.png"
    result = _render_block_png(page, block, mat, out)
    assert result is True
    assert out.exists()


def test_render_block_png_skips_tiny_bbox(tmp_path):
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    mat = fitz.Matrix(2, 2)
    block = {"bbox": (0.0, 0.0, 3.0, 3.0), "type": 0}
    out = tmp_path / "tiny.png"
    result = _render_block_png(page, block, mat, out)
    assert result is False
    assert not out.exists()
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py -k "render_block" -v 2>&1 | head -20
```

Expected: errors (function not yet defined)

- [ ] **Step 3: Append `_render_block_png` to `converters/hybrid_pipeline.py`**

```python


def _render_block_png(page, block, mat, out_path: Path) -> bool:
    """Render a block bounding box to PNG at 2× resolution. Returns True on success."""
    import fitz
    bbox = block["bbox"]
    if bbox[2] - bbox[0] < 5 or bbox[3] - bbox[1] < 5:
        return False
    try:
        pix = page.get_pixmap(matrix=mat, clip=fitz.Rect(bbox))
        pix.save(str(out_path))
        return True
    except Exception:
        print(f"[warn] skip block crop {out_path.name}", file=sys.stderr)
        return False
```

- [ ] **Step 4: Run all tests, verify pass**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py -v
```

Expected: 13 PASSED, only `_pdf_to_md_hybrid` still missing

- [ ] **Step 5: Commit**

```bash
git add converters/hybrid_pipeline.py tests/test_hybrid_pipeline.py
git commit -m "feat: add _render_block_png with tests"
```

---

### Task 5: Implement `_pdf_to_md_hybrid` + integration test

**Files:**
- Modify: `converters/hybrid_pipeline.py`
- Modify: `tests/test_hybrid_pipeline.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_hybrid_pipeline.py`:
```python


_INPUT_DIR = Path("input_pdfs")


def test_hybrid_output_structure(tmp_path):
    import fitz
    pdfs = list(_INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        pytest.skip("No PDFs in input_pdfs/")
    doc = fitz.open(str(pdfs[0]))
    stem = pdfs[0].stem
    content, filename = _pdf_to_md_hybrid(doc, stem, tmp_path)
    assert filename == f"{stem}_hybrid.md"
    assert f"# {stem}" in content
    assert "## Page 1" in content
```

Also update the import at the top of `tests/test_hybrid_pipeline.py` — replace the existing import block with:
```python
import pytest
from pathlib import Path
from converters.hybrid_pipeline import (
    _block_should_skip,
    _block_is_legible,
    _math_font_fraction,
    _render_block_png,
    _pdf_to_md_hybrid,
)
```

- [ ] **Step 2: Run integration test, verify it fails**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py::test_hybrid_output_structure -v 2>&1 | head -20
```

Expected: `ImportError` (function not yet defined)

- [ ] **Step 3: Append `_extract_block_text` and `_pdf_to_md_hybrid` to `converters/hybrid_pipeline.py`**

```python


def _extract_block_text(block) -> str:
    """Concatenate all span texts in a block into a single string."""
    lines = []
    for line in block.get("lines", []):
        line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
        if line_text:
            lines.append(line_text)
    return " ".join(lines)


def _pdf_to_md_hybrid(doc, stem: str, out_dir: Path, **_) -> tuple[str, str]:
    import fitz

    blocks_dir = out_dir / f"{stem}_blocks"
    mat = fitz.Matrix(2, 2)
    blocks_dir_created = False

    def ensure_blocks_dir():
        nonlocal blocks_dir_created
        if not blocks_dir_created:
            blocks_dir.mkdir(exist_ok=True)
            blocks_dir_created = True

    lines = [f"# {stem}\n"]
    pages = list(enumerate(doc, start=1))

    for page_num, page in progress(pages, desc="Hybrid", unit="pg", position=1, leave=False):
        lines.append(f"\n---\n\n## Page {page_num}\n")

        # Scanned page: no extractable text → full-page PNG
        if not page.get_text("text").strip():
            ensure_blocks_dir()
            out_path = blocks_dir / f"p{page_num}_full.png"
            try:
                pix = page.get_pixmap(matrix=mat)
                pix.save(str(out_path))
                lines.append(f"\n![]({stem}_blocks/p{page_num}_full.png)\n")
            except Exception:
                print(f"[warn] skip scanned page {page_num}", file=sys.stderr)
            continue

        d = page.get_text("dict")
        blocks = sorted(d.get("blocks", []), key=lambda b: b["bbox"][1])

        for block_idx, block in enumerate(blocks):
            block_type = block.get("type", 0)

            if block_type == 1:
                # Raster image embedded in PDF
                ensure_blocks_dir()
                out_path = blocks_dir / f"p{page_num}_b{block_idx}.png"
                if _render_block_png(page, block, mat, out_path):
                    lines.append(f"\n![]({stem}_blocks/p{page_num}_b{block_idx}.png)\n")
                continue

            if block_type != 0:
                continue

            block_text = _extract_block_text(block)
            if not block_text:
                continue

            if _block_should_skip(block_text):
                continue

            if _block_is_legible(block, block_text):
                lines.append(f"\n{block_text}\n")
            else:
                ensure_blocks_dir()
                out_path = blocks_dir / f"p{page_num}_b{block_idx}.png"
                quoted = "\n> ".join(block_text.splitlines())
                lines.append(
                    f"\n> ⚠️ Testo estratto (potrebbe essere impreciso):\n> {quoted}\n"
                )
                if _render_block_png(page, block, mat, out_path):
                    lines.append(f"\n![]({stem}_blocks/p{page_num}_b{block_idx}.png)\n")

    return "\n".join(lines), f"{stem}_hybrid.md"
```

- [ ] **Step 4: Run all tests, verify pass**

```bash
source venv/bin/activate && python -m pytest tests/test_hybrid_pipeline.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add converters/hybrid_pipeline.py tests/test_hybrid_pipeline.py
git commit -m "feat: implement _pdf_to_md_hybrid with integration test"
```

---

### Task 6: Register format 9 + wire into `__init__.py`

**Files:**
- Modify: `converters/hybrid_pipeline.py`
- Modify: `converters/__init__.py`

- [ ] **Step 1: Append registration to `converters/hybrid_pipeline.py`**

```python


# ── registration ──────────────────────────────────────────────────────────────

register(ConversionFormat(
    key="9",
    name="Markdown ibrido testo+immagine",
    description=(
        "Testo per blocchi leggibili; callout ⚠️ + PNG per formule/grafici. "
        "Output: _hybrid.md + <nome>_blocks/."
    ),
    ext="md",
    source_ext=".pdf",
    convert=_pdf_to_md_hybrid,
    extra_args=None,
))
```

- [ ] **Step 2: Add import to `converters/__init__.py`**

Append to the end of `converters/__init__.py`:
```python
from . import hybrid_pipeline  # noqa: F401 — registers format 9
```

After edit, the file should read:
```python
from . import pdf_to_formats  # noqa: F401 — registers PDF → * formats (keys 1–6)
from . import ocr_pipeline    # noqa: F401 — registers PDF → OCR markdown (key 7)
from . import md_to_pdf       # noqa: F401 — registers MD → PDF format  (key 8)
from . import hybrid_pipeline  # noqa: F401 — registers format 9
```

- [ ] **Step 3: Run full test suite**

```bash
source venv/bin/activate && python -m pytest tests/ -v
```

Expected: all PASSED

- [ ] **Step 4: Verify format 9 appears in registry**

```bash
source venv/bin/activate && python -c "
from converters import *
from converters.base import _registry
for k, v in sorted(_registry.items()):
    print(f'{k}: {v.name}')
"
```

Expected output includes:
```
9: Markdown ibrido testo+immagine
```

- [ ] **Step 5: Smoke test — run format 9 on a PDF**

```bash
source venv/bin/activate && python main.py input_pdfs/9-Support_Vector_Machines.pdf output/
# When prompted for format, enter: 9
```

Check:
- `output/9-Support_Vector_Machines_hybrid.md` exists and is readable
- `output/9-Support_Vector_Machines_blocks/` contains PNGs for formula/image blocks
- Formula blocks show `> ⚠️` callout in the .md
- Text blocks render as plain markdown

- [ ] **Step 6: Commit**

```bash
git add converters/hybrid_pipeline.py converters/__init__.py
git commit -m "feat: register format 9 hybrid markdown — block-level text + image fallback"
```

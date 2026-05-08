import pytest
from pathlib import Path
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

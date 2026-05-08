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

"""converters/base.py — ConversionFormat contract + global registry"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class ConversionFormat:
    """Describes one conversion format and how to produce it.

    convert(doc, stem, out_dir, *, source_path, **kwargs) -> (content, filename)
      content  : str (text formats) or bytes (binary formats such as PDF)
      doc      : fitz.Document for PDF sources; None for non-PDF sources
      source_path passed as kwarg — use it when doc is None

    extra_args() -> dict   (optional; prompts user for extra kwargs)
    """
    key: str
    name: str
    description: str
    ext: str
    source_ext: str
    convert: Callable[..., tuple[str | bytes, str]]
    extra_args: Optional[Callable[[], dict]] = field(default=None, repr=False)
    
# Global registry of formats, keyed by their unique 'key' field.
# Each format module will call register() at import time to add itself to this registry.
_registry: dict[str, ConversionFormat] = {}


def register(fmt: ConversionFormat) -> None:
    """Register a new conversion format. Called by each format module at import time."""
    _registry[fmt.key] = fmt


def get_format(key: str) -> ConversionFormat:
    """Retrieve a registered format by its key."""
    if key not in _registry:
        raise KeyError(f"Unknown format key: {key!r}")
    return _registry[key]


def all_formats() -> dict[str, ConversionFormat]:
    """Return a copy of the entire format registry."""
    return dict(_registry)

"""converters/base.py — ConversionFormat contract + global registry"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class ConversionFormat:
    """Describes one output format and how to produce it.

    convert(doc, stem, out_dir, **kwargs) -> (content: str, filename: str)
    extra_args()                           -> dict  (optional; prompts user)
    """
    key: str
    name: str
    description: str
    ext: str
    convert: Callable[..., tuple[str, str]]
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

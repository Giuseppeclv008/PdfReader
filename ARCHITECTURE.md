# Architecture — File Converter

## Purpose

CLI tool that converts files (single file or folder) between formats. Designed as an **open, extensible conversion platform**: adding a new format requires writing one function and one `register()` call, touching zero existing files.

---

## Directory Layout

```text
PdfReader/
├── main.py                     # Entry point: wires menu → paths → converter
├── config/
│   └── config.py               # Global constants (DPI, fitz matrices)
├── converters/
│   ├── __init__.py             # Side-effect imports: triggers registration of all built-ins
│   ├── base.py                 # ConversionFormat dataclass + global registry
│   ├── pdf_to_formats.py       # Built-in PDF → * formats (keys 1–7)
│   └── md_to_pdf.py            # Built-in MD → PDF format (key 8)
├── core/
│   └── core.py                 # convert_one() / convert_folder() — pure orchestration
├── menu/
│   └── menu.py                 # CLI menu, reads dynamically from registry
└── utils/
    └── utils.py                # progress() display + extract_images_b64()
```

---

## Design Principles

### Open/Closed Principle (OCP)

The system is **open for extension, closed for modification**.
Adding a new output format means:

1. Write a converter function.
2. Call `register(ConversionFormat(...))`.
3. Done — menu, dispatch, and folder-batch all pick it up automatically.

No existing file needs to change.

### Single Responsibility

| Module | Responsibility |
| --- | --- |
| `main.py` | Wires together menu, path resolution, and converter call |
| `converters/base.py` | Owns the registry contract and data structure |
| `converters/pdf_to_formats.py` | Implements and registers built-in PDF → * formats |
| `converters/md_to_pdf.py` | Implements and registers MD → PDF format |
| `core/core.py` | Opens source files, dispatches to registry, writes output |
| `menu/menu.py` | Reads registry, renders menu, collects user input |
| `utils/utils.py` | Shared I/O helpers (progress bar, image extraction) |
| `config/config.py` | Rendering constants, fitz availability gate |

### Dependency Direction

```text
main.py
  ├── menu/menu.py   → converters/base.py (read registry)
  ├── core/core.py   → converters/base.py (get_format)
  │                  → utils/utils.py
  └── converters/    → converters/base.py (register)
                     → config/config.py   (PDF formats only)
                     → utils/utils.py     (PDF formats only)
```

`menu` and `core` depend only on `base` (the abstraction), never on concrete converter implementations. Converters do not depend on menu or core.

---

## Key Abstraction: `ConversionFormat`

Defined in `converters/base.py`:

```python
@dataclass
class ConversionFormat:
    key: str                                      # menu key (e.g. "1", "8")
    name: str                                     # display label
    description: str                              # one-line description shown in menu
    ext: str                                      # output file extension
    source_ext: str                               # input file extension (e.g. ".pdf", ".md")
    convert: Callable[..., tuple[str | bytes, str]]  # see contract below
    extra_args: Optional[Callable[[], dict]]      # optional: prompts user, returns kwargs
```

### Converter Function Contract

```python
def my_converter(
    doc,            # fitz.Document for .pdf sources; None for all other sources
    stem: str,      # source filename without extension
    out_dir: Path,  # directory where output should be written
    *,
    source_path: Path,  # always provided — original source file path
    **kwargs,           # extra args from extra_args()
) -> tuple[str | bytes, str]:
    ...
    return content, output_filename
```

| Parameter | Type | Description |
| --- | --- | --- |
| `doc` | `fitz.Document \| None` | Opened PDF doc, or `None` for non-PDF sources |
| `stem` | `str` | Source filename without extension |
| `out_dir` | `Path` | Directory where output files should be written |
| `source_path` | `Path` | Full path to source file (always passed as kwarg) |
| `**kwargs` | `dict` | Extra arguments collected by `extra_args()` |
| **Returns** | `(str \| bytes, str)` | `(file content, output filename)` |

`content` must be `str` for text formats and `bytes` for binary formats (e.g. PDF output). The orchestrator calls `write_text` or `write_bytes` accordingly.

The function may write auxiliary files (images, sub-dirs) as side effects. The returned content is always written to `out_dir / output_filename` by the orchestrator.

### `extra_args` Contract

```python
def my_extra_args() -> dict:
    value = input("Prompt user: ").strip()
    return {"my_kwarg": value}
```

Return a dict that will be unpacked as `**kwargs` into the converter call. Return `None` (default) if no extra input is needed.

---

## Design Patterns

### Registry Pattern

`_registry: dict[str, ConversionFormat]` in `converters/base.py` is a global map from format key to format descriptor. Converters self-register at import time via `register()`. The menu and orchestrator query it at runtime — neither hard-codes format keys.

### Strategy Pattern

`ConversionFormat.convert` is a strategy: a pluggable function that encapsulates one algorithm for producing output. `convert_one()` selects and invokes the strategy without knowing its internals.

### Plugin / Self-Registration

Each format registers itself when its module is imported. `converters/__init__.py` imports all built-in modules, firing their `register()` calls. Third-party formats follow the same pattern: write a module, import it before `show_menu()`, it appears in the menu.

---

## Adding a New Format (AI Instructions)

**Step 1** — Write the converter function in a new file (e.g. `converters/my_format.py`):

```python
from pathlib import Path
from converters.base import ConversionFormat, register

def _to_my_format(doc, stem: str, out_dir: Path, *, source_path: Path, **kwargs) -> tuple[str, str]:
    # doc is fitz.Document if source_ext=".pdf", else None
    # use source_path to read the source file for non-PDF inputs
    ...
    return content, f"{stem}.myext"

register(ConversionFormat(
    key="9",               # next available key
    name="My Format",
    description="One-line description shown in the menu.",
    ext="myext",
    source_ext=".pdf",     # or ".md", ".txt", etc.
    convert=_to_my_format,
    # extra_args=_my_extra_args,  # add if user input needed
))
```

**Step 2** — Register it by adding one line to `converters/__init__.py`:

```python
from . import my_format  # noqa: F401
```

**That's all.** No changes to `core/`, `menu/`, `config/`, or any existing converter.

### Rules to maintain OCP

- Never add `if choice == "N":` branches anywhere.
- Never hardcode format keys or source extensions in `menu.py` or `core/core.py`.
- If a converter needs user input, use `extra_args` — do not special-case it in `menu.py`.
- For binary output (e.g. PDF), return `bytes` — the orchestrator handles `write_bytes` automatically.
- For non-PDF sources, use `source_path` to read the file; `doc` will be `None`.

---

## Dependencies

| Package | Used for |
| --- | --- |
| `pymupdf` (`fitz`) | PDF parsing, page rendering, image extraction, PDF generation |
| `tqdm` | Progress bars (graceful fallback if absent) |
| `markdown` | Markdown → HTML conversion (format 8) |
| `pytesseract` | OCR — format 7 only, optional |
| `Pillow` (`PIL`) | Image I/O for OCR pipeline — format 7 only, optional |

---

## Data Flow

```text
main.py
  │
  ├─ show_menu()          → returns (choice, extra_kwargs)
  ├─ get_format(choice)   → ConversionFormat (for source_ext validation)
  ├─ get_input_path()     → returns Path
  │
  └─ convert_one(source_path, out_dir, choice, **extra_kwargs)
       │
       ├─ get_format(choice)                                      → ConversionFormat
       ├─ fitz.open(source_path) if .pdf else None               → doc
       ├─ fmt.convert(doc, stem, out_dir, source_path=…, **kwargs) → (content, filename)
       └─ out_file.write_bytes(content)  OR  write_text(content)
```

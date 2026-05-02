# Architecture — File Converter

## Purpose

CLI tool that converts PDF files (single file or folder) to multiple output formats. Designed as an **open, extensible conversion platform**: adding a new format requires writing one function and one `register()` call, touching zero existing files.

---

## Directory Layout

```text
PdfReader/
├── main.py                     # Entry point: wires menu → paths → converter
├── config/
│   └── config.py               # Global constants (DPI, fitz matrices)
├── converters/
│   ├── __init__.py             # Side-effect import: triggers registration of built-ins
│   ├── base.py                 # ConversionFormat dataclass + global registry
│   └── converters.py           # 7 built-in formats, each registered at module load
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
| `converters/converters.py` | Implements and registers built-in formats |
| `core/core.py` | Opens documents, dispatches to registry, writes output |
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
                     → config/config.py
                     → utils/utils.py
```

`menu` and `core` depend only on `base` (the abstraction), never on concrete converter implementations. Converters do not depend on menu or core.

---

## Key Abstraction: `ConversionFormat`

Defined in `converters/base.py`:

```python
@dataclass
class ConversionFormat:
    key: str                                 # menu key (e.g. "1", "8")
    name: str                                # display label
    description: str                         # one-line description shown in menu
    ext: str                                 # output file extension
    convert: Callable[..., tuple[str, str]]  # see contract below
    extra_args: Optional[Callable[[], dict]] # optional: prompts user, returns kwargs
```

### Converter Function Contract

```python
def my_converter(doc, stem: str, out_dir: Path, **kwargs) -> tuple[str, str]:
    ...
    return content, output_filename
```

| Parameter | Type | Description |
| --- | --- | --- |
| `doc` | `fitz.Document` | Opened PDF document |
| `stem` | `str` | PDF filename without extension (use as title/prefix) |
| `out_dir` | `Path` | Directory where output files should be written |
| `**kwargs` | `dict` | Extra arguments collected by `extra_args()` |
| **Returns** | `(str, str)` | `(file content, output filename)` |

The function may write auxiliary files (images, sub-dirs) as side effects. The returned string is always written to `out_dir / output_filename` by the orchestrator.

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

`ConversionFormat.convert` is a strategy: a pluggable function that encapsulates one algorithm for producing output from a PDF. `convert_one()` selects and invokes the strategy without knowing its internals.

### Plugin / Self-Registration

Each format registers itself when its module is imported. `converters/__init__.py` imports the built-ins module, which fires all `register()` calls. Third-party formats follow the same pattern: write a module, import it before `show_menu()`, it appears in the menu.

---

## Adding a New Format (AI Instructions)

**Step 1** — Write the converter function in a new file (e.g. `converters/my_format.py`):

```python
from pathlib import Path
from converters.base import ConversionFormat, register

def _to_my_format(doc, stem: str, out_dir: Path, **kwargs) -> tuple[str, str]:
    # ... produce content string ...
    return content, f"{stem}.myext"

register(ConversionFormat(
    key="8",               # next available key
    name="My Format",
    description="One-line description shown in the menu.",
    ext="myext",
    convert=_to_my_format,
    # extra_args=_my_extra_args,  # add if user input needed
))
```

**Step 2** — Import it before `show_menu()` is called. Two options:

- **Built-in**: add `from . import my_format` in `converters/__init__.py`.
- **External plugin**: add `import converters.my_format` in `main.py` before `show_menu()`.

**That's all.** No changes to `core/`, `menu/`, `config/`, or any existing converter.

### Rules to maintain OCP

- Never add `if choice == "N":` branches anywhere.
- Never hardcode format keys in `menu.py` or `core/core.py`.
- If a converter needs user input, use `extra_args` — do not special-case it in `menu.py`.
- Keep converter functions pure w.r.t. the registry: no `register()` calls inside `convert`.

---

## Dependencies

| Package | Used for |
| --- | --- |
| `pymupdf` (`fitz`) | PDF parsing, page rendering, image extraction |
| `tqdm` | Progress bars (graceful fallback if absent) |
| `pytesseract` | OCR — format 7 only, optional |
| `Pillow` (`PIL`) | Image I/O for OCR pipeline — format 7 only, optional |

---

## Data Flow

```text
main.py
  │
  ├─ show_menu()          → returns (choice, ext, extra_kwargs)
  ├─ get_input_path()     → returns Path
  │
  └─ convert_one(pdf_path, out_dir, choice, **extra_kwargs)
       │
       ├─ get_format(choice)                               → ConversionFormat from registry
       ├─ fitz.open(pdf_path)                              → doc
       ├─ fmt.convert(doc, stem, out_dir, **extra_kwargs)  → (content, filename)
       └─ out_file.write_text(content)
```

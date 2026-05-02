# PDF Converter

Extensible CLI tool that converts PDF files (single file or folder) to multiple formats using [PyMuPDF](https://pymupdf.readthedocs.io/). New output formats can be added without touching existing code — see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows
pip install -r requirements.txt

```

---

## Usage

```bash
python3 main.py [file.pdf | folder] [output_dir]
```

All arguments are **optional**: if omitted, the script prompts for the path interactively.

### Examples

```bash
# Interactive menu, then enter the path
python3 main.py

# Single file — output in ./output/
python3 main.py doc.pdf

# Whole folder — output in ./output/
python3 main.py input_pdfs output_folder
```

At startup the **format selection menu** is always shown.

---

## Output formats

| # | Format | Extension | Notes |
| --- | --- | --- | --- |
| 1 | **Markdown — text only** | `.md` | Extracted text, structured by page |
| 2 | **Markdown AI-ready** | `_ai.md` | Text + base64 embedded images. Single file — can be large for scanned books |
| 3 | **Plain Text** | `.txt` | Raw text, no formatting |
| 4 | **Structured JSON** | `.json` | List of pages with text and image paths saved in `<name>_images/` |
| 5 | **HTML embedded** | `.html` | Text + base64 inline images, openable in a browser |
| 6 | **Markdown + separate images** | `_linked.md` | Page images saved as files in `<name>_pages/`, referenced by path. No base64 — ideal for large scanned books |
| 7 | **Markdown + OCR** | `_ocr.md` | Text extracted via Tesseract OCR. Pure text output, minimal tokens. Requires pytesseract + Tesseract binary |

### Choosing the right format for scanned books

| Scenario | Recommended format |
| --- | --- |
| Scanned book, AI tool with file access | **6** — images as separate files, no token bloat |
| Scanned book, need text only | **7** — OCR extracts readable text, minimal tokens |
| Small PDF with a few images | **2** — single self-contained file |
| Text-based PDF (not scanned) | **1** or **3** |

---

## Output directory

| Input | Default output |
| --- | --- |
| `file.pdf` | `./output/` next to the file |
| `folder/` | `./folder_output/` |

---

## Deactivate venv

```bash
deactivate
```

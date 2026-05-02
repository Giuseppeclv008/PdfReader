# PDF Converter

Convert PDF files (single file or folder) to multiple formats using [PyMuPDF](https://pymupdf.readthedocs.io/).

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
python3 pdf_converter.py [file.pdf | folder] [output_dir]
```

All arguments are **optional**: if omitted, the script prompts for the path interactively.

### Examples

```bash
# Interactive menu, then enter the path
python3 pdf_converter.py

# Single file — output in ./output/
python3 pdf_converter.py doc.pdf

# Whole folder — output in ./output/
python3 pdf_converter.py input_pdfs output_folder
```

At startup the **format selection menu** is always shown.

---

## Output formats

| # | Format | Extension | Notes |
| --- | --- | --- | --- |
| 1 | **Markdown — text only** | `.md` | Extracted text, structured by page |
| 2 | **Markdown AI-ready** | `_ai.md` | Text + base64 embedded images. Single file, readable directly by AI tools without pre-processing |
| 3 | **Plain Text** | `.txt` | Raw text, no formatting |
| 4 | **Structured JSON** | `.json` | List of pages with text and image paths saved in `<name>_images/` |
| 5 | **HTML embedded** | `.html` | Text + base64 inline images, openable in a browser |

> **For image-heavy PDFs intended for AI tools**: use format **2 (Markdown AI-ready)**. Images are embedded as data URIs — the AI sees both text and images in a single file with no intermediate steps.

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

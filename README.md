# pdf_to_md

Convert PDF files to Markdown using [PyMuPDF](https://pymupdf.readthedocs.io/).

---

## Setup

### 1. Create virtual environment

```bash
python3 -m venv venv
```

### 2. Activate it

**macOS / Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```cmd
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Usage

### Single file

```bash
python3 pdf_to_md.py path/to/file.pdf
```

Output: `path/to/file.md` (same directory as input)

### Batch folder

```bash
python3 pdf_to_md.py path/to/input_folder path/to/output_folder
```

Converts all `.pdf` files in `input_folder` and writes `.md` files to `output_folder`.

---

## Output format

Each PDF becomes one Markdown file:

```
# filename

---

## Page 1

<text content>

---

## Page 2

<text content>
```

---

## Deactivate venv

```bash
deactivate
```

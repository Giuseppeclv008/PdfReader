# CMEX Garbage Fix — Verify & Commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify the three CMEX/legend fixes already applied to `converters/pdf_to_formats.py`, compare converter output against reference Spiegazione.md files for all 7 SLIDES PDFs, then commit and push.

**Architecture:** The fixes are already in place (28 additions to `converters/pdf_to_formats.py`). This plan is purely verification + commit. No new code changes expected unless regressions are found.

**Tech Stack:** Python 3, PyMuPDF (fitz), pix2tex (LatexOCR), git

---

## What Was Already Fixed

Three changes to `converters/pdf_to_formats.py`:

1. **`_has_formula_chars(text)`** — new helper, returns True if text contains ASCII ctrl chars 0x00-0x1F (excl. tab/newline/CR/space) or CMEX private-use-area 0xF800-0xF8FF. Deliberately excludes U+FB01 (fi ligature).

2. **`_extract_vector_formula_regions`** — two changes:
   - Ctrl-char blocks no longer added to `prose_yranges` (so they don't block formula detection)
   - Ctrl-char blocks with `mc > 0` force-included as formula candidates even if `frac < 0.10`

3. **`_vector_page_to_md`** — two new prose filters:
   - Skip blocks where `_has_formula_chars(block_text)` is True
   - Skip single-line blocks with `bh <= 11` matching chart-legend pattern (`[—–]` + `= digit`)

---

## Files

- Modify (already done): `converters/pdf_to_formats.py`
- Read: `/Users/giuseppecalvello/Downloads/SLIDES/*.pdf` (7 PDFs)
- Read: `/Users/giuseppecalvello/Downloads/SLIDES/*_Spiegazione.md` (7 reference files)
- Output: `/Users/giuseppecalvello/Downloads/SLIDES/output/*_ocr.md` (generated per run)

---

### Task 1: Quick Sanity Check — SVM Pages 48/49/50

Confirm the fixes produce clean output on the pages that prompted this work.

- [ ] **Step 1: Check the already-generated SVM output (no re-run needed)**

```bash
python3 -c "
import re
text = open('input_pdfs/output/9-Support_Vector_Machines_ocr.md').read()
pages = re.split(r'## Page \d+', text)
for idx in [48, 49, 50]:
    p = pages[idx]
    ctrl = [hex(ord(c)) for c in p if ord(c) < 0x20 and c not in '\t\n\r ']
    pua  = [hex(ord(c)) for c in p if 0xf800 <= ord(c) <= 0xf8ff]
    poly = 'Poly' in p and '—' in p and '=' in p
    print(f'Page {idx}: ctrl={ctrl[:3]}, pua={pua[:3]}, poly_legend={poly}')
    print(f'  preview: {repr(p[:200])}')
"
```

Expected output:
```
Page 48: ctrl=[], pua=[], poly_legend=False
  preview: '... Support Vector Machines ...'
Page 49: ctrl=[], pua=[], poly_legend=False
Page 50: ctrl=[], pua=[], poly_legend=False
```

- [ ] **Step 2: Confirm page 48 has LaTeX formula (not garbled text)**

```bash
python3 -c "
import re
text = open('input_pdfs/output/9-Support_Vector_Machines_ocr.md').read()
pages = re.split(r'## Page \d+', text)
p48 = pages[48]
has_latex = '\$\$' in p48
print('Has LaTeX block:', has_latex)
"
```

Expected: `Has LaTeX block: True`

---

### Task 2: Run SLIDES PDFs Without pix2tex

Run format 7 (no pix2tex) on all 7 SLIDES PDFs to check ctrl-char cleanup is general.

- [ ] **Step 1: Run all 7 SLIDES PDFs**

```bash
for pdf in "/Users/giuseppecalvello/Downloads/SLIDES/"*.pdf; do
    printf "7\n\nn\n" | venv/bin/python3 main.py "$pdf" 2>&1 | tail -1
done
```

Expected: Each line shows `✓  <name>.pdf → <name>_ocr.md`

- [ ] **Step 2: Check known-bad pages in three problem PDFs**

```bash
python3 -c "
import re, glob
problem_pages = {
    '3-MLPR_Intro_ocr.md': [15, 16],
    '5-Probability_ocr.md': [7, 19],
    '8-Logistic_Regression_ocr.md': [12, 18, 20],
}
outdir = '/Users/giuseppecalvello/Downloads/SLIDES/output/'
for fname, bad_pages in problem_pages.items():
    text = open(outdir + fname).read()
    pages = re.split(r'## Page \d+', text)
    for idx in bad_pages:
        if idx >= len(pages):
            print(f'{fname} page {idx}: MISSING')
            continue
        p = pages[idx]
        ctrl = [hex(ord(c)) for c in p if ord(c) < 0x20 and c not in chr(9)+chr(10)+chr(13)+' ']
        pua  = [hex(ord(c)) for c in p if 0xf800 <= ord(c) <= 0xf8ff]
        status = 'CLEAN' if not ctrl and not pua else 'DIRTY'
        print(f'{fname} page {idx}: {status} ctrl={ctrl[:3]} pua={pua[:3]}')
"
```

Expected: All lines show `CLEAN`.

---

### Task 3: Compare SLIDES Output with Spiegazione.md References

The `*_Spiegazione.md` files are Italian study guides covering the slide content. They serve as a content-coverage check — the converter output should contain the same topics, not necessarily word-for-word.

- [ ] **Step 1: Extract topic headings from each Spiegazione.md**

```bash
python3 -c "
import glob, re, os
spieg_dir = '/Users/giuseppecalvello/Downloads/SLIDES/'
for f in sorted(glob.glob(spieg_dir + '*_Spiegazione.md')):
    text = open(f).read()
    headings = re.findall(r'^#{1,3} .+', text, re.MULTILINE)
    print(os.path.basename(f), '—', len(headings), 'headings')
    for h in headings[:5]:
        print('  ', h)
    print()
"
```

- [ ] **Step 2: Check converter output covers same topics**

For each PDF, compare the top-level keywords from Spiegazione.md against what's in the ocr output. The goal is to confirm no entire slide sections went missing.

```bash
python3 -c "
import glob, re, os

outdir = '/Users/giuseppecalvello/Downloads/SLIDES/output/'
spieg_dir = '/Users/giuseppecalvello/Downloads/SLIDES/'

for spieg_file in sorted(glob.glob(spieg_dir + '*_Spiegazione.md')):
    basename = os.path.basename(spieg_file).replace('_Spiegazione.md', '')
    ocr_file = outdir + basename + '_ocr.md'
    if not os.path.exists(ocr_file):
        print(f'{basename}: OCR output missing!')
        continue

    spieg = open(spieg_file).read().lower()
    ocr   = open(ocr_file).read().lower()

    # Extract key nouns from Spiegazione headings
    headings = re.findall(r'^#{1,3} (.+)', open(spieg_file).read(), re.MULTILINE)
    missing = []
    for h in headings:
        keyword = re.sub(r'[^\w ]', '', h).strip().lower()
        words = [w for w in keyword.split() if len(w) > 4]
        if words and not any(w in ocr for w in words[:2]):
            missing.append(h)

    if missing:
        print(f'{basename}: possible gaps — {missing[:3]}')
    else:
        print(f'{basename}: OK ({len(headings)} headings checked)')
"
```

Expected: All lines show `OK` or only minor gaps (short/ambiguous headings). Any `possible gaps` line requires manual inspection of that PDF's OCR output.

- [ ] **Step 3: Manual spot-check one section per PDF if any gaps found**

If step 2 reports `possible gaps`, open the relevant `*_ocr.md` and search for context around the missing heading's topic. Determine if the content is actually present under different wording (acceptable) or genuinely missing (regression — investigate and fix before committing).

---

### Task 4: Regression Check — Good Pages

Confirm the fixes didn't break pages that were already working correctly.

- [ ] **Step 1: Check SVM pages 3, 11, 20 (fraction reconstruction, Lagrangian)**

```bash
python3 -c "
import re
text = open('input_pdfs/output/9-Support_Vector_Machines_ocr.md').read()
pages = re.split(r'## Page \d+', text)
for idx in [3, 11, 20]:
    p = pages[idx]
    print(f'--- Page {idx} ---')
    print(p[:400])
    print()
"
```

Expected: Readable prose, inline fractions preserved (e.g., `w/||w||`), no garbled chars.

---

### Task 5: Commit and Push

- [ ] **Step 1: Stage the changed file**

```bash
git add converters/pdf_to_formats.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
fix: filter CMEX garbage chars and chart legend labels from OCR output

Add _has_formula_chars() to detect CMEX bracket glyphs (ASCII ctrl
0x00-0x1F and private-use-area 0xF800-0xF8FF). Use it in three places:
- _extract_vector_formula_regions: force-include ctrl-char blocks as
  formula candidates; exclude them from prose_yranges to avoid blocking
  formula detection for adjacent regions.
- _vector_page_to_md: skip CMEX delimiter fragments from prose output;
  skip chart legend labels (single-line, h<=11, dash + '= digit' pattern).

Fixes garbled output on SVM pp. 48-49 and Logistic Regression pp. 12/18/20.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push**

```bash
git push
```

- [ ] **Step 4: Confirm push succeeded**

```bash
git log --oneline -3
```

Expected: top commit matches the message above.

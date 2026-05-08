# Design: Formato 9 — Markdown Ibrido Testo+Immagine

**Data:** 2026-05-08  
**Stato:** Approvato

---

## Problema

I formati esistenti falliscono su PDF con formule o grafici:
- Formule → testo storpiato (caratteri CMEX, glifi CM font)
- Grafici → nessun testo estratto, o labels asse lette come formule

## Soluzione

Nuovo formato 9 a livello blocco: ogni blocco viene classificato come "good" (testo leggibile) o "bad" (formula/grafico/garbage). I blocchi bad mostrano il testo estratto con callout di avviso + PNG crop del blocco per supporto visivo. L'umano decide se il testo è sufficiente o se serve l'immagine.

---

## Architettura

### File

- **Nuovo:** `converters/hybrid_pipeline.py` — implementazione formato 9 + registrazione
- **Modificato:** `converters/__init__.py` — aggiunge import di `hybrid_pipeline` (una riga)
- Nessun altro file esistente modificato (rispetta OCP)

### Output

- `<stem>_hybrid.md` — documento principale
- `<stem>_blocks/` — PNG dei blocchi problematici (creata solo se almeno un blocco bad)
  - Naming: `p{page_num}_b{block_idx}.png`

### Dipendenze

- `fitz` (PyMuPDF) — già presente
- `Pillow` — già usato in formato 7
- Zero nuove dipendenze obbligatorie

---

## Classificazione Blocchi

### Blocco testo (type 0)

| Condizione | Azione |
|---|---|
| `_has_formula_chars(text)` → True | **bad** |
| Math font fraction > 30% del blocco | **bad** |
| Solo numeri/labels asse | **skip** (irrilevante) |
| Pattern legend grafico | **skip** (irrilevante) |
| Nessuna delle sopra | **good** |

Math font fraction: proporzione di caratteri in span con font CM/STIX/MSAM/etc. (via `_is_math_font` esistente).

### Blocco immagine (type 1)

Sempre trattato come immagine → PNG crop della bbox.  
Se `_looks_like_formula(img)` e pix2tex disponibile → tenta LaTeX, usa `$$...$$` invece del PNG.

---

## Data Flow

Per ogni pagina:

1. `page.get_text("dict")` → lista blocchi ordinati per `bbox[1]` (y0)
2. Per ogni blocco in ordine:
   - `type == 1` → render crop PNG → salva → `![](...)` nel .md
   - `type == 0` → `_reconstruct_block_text()` → classifica:
     - skip → niente
     - good → testo nel .md
     - bad → callout `> ⚠️` + testo + render crop PNG + `![](...)` nel .md
3. Separatore `---` tra pagine

Render crop (2× per qualità):
```python
mat = fitz.Matrix(2, 2)
clip = fitz.Rect(block["bbox"])
pix = page.get_pixmap(matrix=mat, clip=clip)
pix.save(blocks_dir / f"p{page_num}_b{block_idx}.png")
```

### Output per blocco bad

```markdown
> ⚠️ Testo estratto (potrebbe essere impreciso):
> C = 1nλ ∑ ω_i ℱ

![](nome_blocks/p3_b2.png)
```

### Output per blocco good

```markdown
Il teorema di Bayes afferma che...
```

### Output per image block

```markdown
![](nome_blocks/p3_b5.png)
```

---

## Edge Cases

| Caso | Comportamento |
|---|---|
| Pagina vuota | Solo separatore `---`, nessun PNG |
| Bbox < 5px width/height | Skip (stray glyph) |
| Cartella `_blocks/` esiste già | `mkdir(exist_ok=True)`, sovrascrive |
| Pixmap fallisce (PDF corrotto) | Log `[warn]` su stderr, continua |
| PDF scansionato (no testo estraibile) | Intera pagina → PNG singolo |
| Nessun blocco bad nell'intero PDF | Cartella `_blocks/` non creata |

---

## Extra Args al Lancio

Nessuno. Il formato funziona stand-alone senza input aggiuntivi dall'utente.

---

## Testing

Tutti i test su PDF in `input_pdfs/`:

| Test case | Verifica |
|---|---|
| PDF testo puro | Nessun PNG generato, solo testo nel .md |
| PDF con formule LaTeX | Blocchi formula → PNG + callout |
| PDF con grafici | Image blocks → PNG, axis labels skippati |
| PDF scansionato | Pagina intera come PNG singolo |
| PDF misto (testo + formula + grafico) | Mix corretto testo/callout/immagine |

Segnale di successo: `.md` leggibile da umano, PNG presenti solo dove servono, nessun crash.

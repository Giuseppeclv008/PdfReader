"""converters/ai_helpers.py — Local LLM helpers via Ollama for OCR cleanup.

Optional dependency: `pip install ollama` + a running Ollama daemon.
Default model picked via env var AI_MODEL (fallback: gemma3:4b).
"""

import os
import sys

_DEFAULT_MODEL = os.environ.get("AI_MODEL", "qwen2.5:3b")

_OCR_CLEANUP_SYSTEM = """You are an OCR text cleanup tool for Italian and English text.
Your ONLY task is to fix obvious OCR character-recognition errors.

Strict rules:
- Restore missing accents in Italian (attivita -> attività, universita -> università, e -> è)
- Fix obviously garbled letters using surrounding context
- DO NOT add, remove, or paraphrase content
- DO NOT add commentary, headers, code fences, or markdown formatting
- DO NOT change correct words, numbers, dates, addresses, or proper names
- Preserve line breaks and paragraph structure exactly
- If a word is too garbled to recognize, leave it as-is
- Output only the cleaned text, nothing else"""


def clean_ocr_text(text: str, model: str = _DEFAULT_MODEL) -> str:
    """Pass OCR text through a local LLM to fix character errors.

    Returns cleaned text on success, original text on any failure (never raises).
    """
    if not text.strip():
        return text
    try:
        import ollama
    except ImportError:
        print(
            "[warn] AI cleanup requires `pip install ollama` — skipping",
            file=sys.stderr,
        )
        return text
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": _OCR_CLEANUP_SYSTEM},
                {"role": "user", "content": text},
            ],
            options={
                "temperature": 0.1,
                "num_predict": -1,   # unlimited output length
                "num_ctx": 4096,
            },
        )
        cleaned = response["message"]["content"].strip()
        # Strip accidental markdown code fences if the model adds them
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned or text
    except Exception as e:
        print(f"[warn] AI cleanup failed ({type(e).__name__}: {e}) — using raw OCR",
              file=sys.stderr)
        return text

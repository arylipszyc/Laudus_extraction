"""Spike 9.5e — replicar prompt literal de Ary en web.

Hipótesis: el prompt minimalista funciona mejor pidiendo labels exactos
(monto facturado anterior) en vez de listas de alternativas.

Output: _bmad-output/coordination/9-5e-web-prompt-spike-{ts}/
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Prompt literal de Ary en Gemini web (replica exacta).
PROMPT_WEB = """por favor dame un CSV con las transacciones de esta tarjeta de credito.
Dime de que periodo es, en que moneda esta, monto facturado anterior y monto facturado del periodo"""


PDFS = [
    "estado-de-cuenta (26).pdf",
    "bci-visa-202604.pdf",
    "santander-mastercard-202604.pdf",
]
SAMPLES_DIR = Path("samples")
TS = datetime.now().strftime("%Y-%m-%d-%H%M%S")
OUT_DIR = Path("_bmad-output/coordination") / f"9-5e-web-prompt-spike-{TS}"


def call_gemini(prompt: str, pdf_bytes: bytes, model: str) -> tuple[str, float, int]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        temperature=0.0,
        thinking_config=types.ThinkingConfig(thinking_budget=-1),
    )
    start = time.monotonic()
    resp = client.models.generate_content(
        model=model,
        contents=[prompt, pdf_part],
        config=config,
    )
    latency = time.monotonic() - start
    thoughts = 0
    try:
        thoughts = resp.usage_metadata.thoughts_token_count or 0
    except (AttributeError, TypeError):
        pass
    return resp.text or "", latency, thoughts


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "prompt-web.txt").write_text(PROMPT_WEB, encoding="utf-8")

    print(f"Prompt web replica — model=gemini-2.5-flash, thinking auto")
    print(f"Output: {OUT_DIR}")
    print(f"Prompt size: {len(PROMPT_WEB.encode('utf-8'))} bytes")
    print()

    summary = []
    for pdf_name in PDFS:
        pdf_path = SAMPLES_DIR / pdf_name
        if not pdf_path.exists():
            print(f"SKIP {pdf_name}")
            continue
        pdf_bytes = pdf_path.read_bytes()
        print(f"PDF: {pdf_name}")
        try:
            raw, latency, thoughts = call_gemini(PROMPT_WEB, pdf_bytes, "gemini-2.5-flash")
            run_dir = OUT_DIR / pdf_name.replace("/", "_")
            run_dir.mkdir(exist_ok=True)
            (run_dir / "raw.txt").write_text(raw, encoding="utf-8")
            summary.append({
                "pdf": pdf_name,
                "latency_s": round(latency, 2),
                "raw_bytes": len(raw.encode("utf-8")),
                "thoughts_tokens": thoughts,
            })
            print(f"  {latency:.1f}s  {len(raw)}b  thoughts={thoughts}t")
            print(f"  First 500 chars of response:")
            print("  " + raw[:500].replace("\n", "\n  "))
            print()
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            summary.append({"pdf": pdf_name, "error": f"{type(exc).__name__}: {exc}"})

    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

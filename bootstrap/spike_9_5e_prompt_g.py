"""Spike 9.5e Task 0 — pase 7 (final): Variación G.

Combina lo mejor de E y F:
  - Orden de F (lenguaje natural primero, formato después) — arregló Estado-26.
  - Wording "tarjeta de crédito chilena" de E (ayudó BCI/Santander) pero
    inclusivo ("o estado de cuenta similar") para no excluir Estado-26.

ÚLTIMO pase. Si no llega a ≥7/9 verde, cierro con el mejor prompt.

Output: _bmad-output/coordination/9-5e-prompt-spike-g-{ts}/
"""
from __future__ import annotations

import csv as csv_mod
import json
import os
import re
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


PROMPT_G = """Por favor extraé de esta cartola de tarjeta de crédito chilena (o estado de cuenta similar):
- Período (fechas inicio y fin)
- Moneda
- Monto Facturado Anterior
- Monto Facturado del Periodo
- Todas las transacciones del período

Devolvé EXACTAMENTE este formato y nada más:

<header JSON en una línea>
---
<CSV con delimitador `|`>

Header JSON:
{"period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "currency": "CLP|USD|EUR", "opening_balance": <Monto Facturado Anterior como número>, "closing_balance": <Monto Facturado del Periodo como número>}

CSV — primera línea exactamente: date|description|amount|currency
Luego una fila por transacción.

Reglas para amount:
- Signo TAL CUAL aparece en el PDF.
- Para CLP, los amounts son SIEMPRE enteros sin decimales (sin punto, sin coma): "1234567" no "1.234.567" ni "1234.567".
- Para USD/EUR, punto como decimal si lo necesita (ej "12.50").

Otras reglas:
- date: YYYY-MM-DD.
- description: texto crudo del PDF; reemplazá `|` interno por espacio.
- Incluí cuotas pre-existentes X/N con X≥1 (description + " (cuota X/N)", amount = valor de la cuota mensual con su signo).
- NO incluyas subtotales/totales ni cuotas futuras (00/N).

Sin markdown, sin explicaciones, sin texto fuera del formato.
"""

REPR_PDFS = [
    "bci-visa-202604.pdf",
    "santander-mastercard-202604.pdf",
    "estado-de-cuenta (26).pdf",
]

RUNS = 3
SAMPLES_DIR = Path("samples")
TOLERANCE = Decimal("100")

TS = datetime.now().strftime("%Y-%m-%d-%H%M%S")
OUT_DIR = Path("_bmad-output/coordination") / f"9-5e-prompt-spike-g-{TS}"


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


def _strip_fence(s: str) -> str:
    s = re.sub(r"^```(?:json|csv|text)?\s*\n?", "", s.strip())
    s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def _parse_amount(raw: str) -> Decimal:
    s = raw.strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        idx = s.rfind(",")
        if len(s) - idx - 1 == 3 and "." not in s[idx:]:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    if s.count(".") > 1:
        s = s.replace(".", "")
    val = Decimal(s)
    return -val if neg else val


def parse_response(raw: str) -> dict:
    out = {"ok": False, "error": None, "n_tx": 0,
           "opening": None, "closing": None, "sum_amounts": None, "diff": None}
    parts = raw.split("---", 1)
    if len(parts) != 2:
        out["error"] = "no '---' separator"
        return out
    header_str = _strip_fence(parts[0])
    body_str = _strip_fence(parts[1])
    try:
        header = json.loads(header_str)
    except json.JSONDecodeError as exc:
        out["error"] = f"header JSON parse: {exc}"
        return out
    try:
        opening = _parse_amount(str(header["opening_balance"]))
        closing = _parse_amount(str(header["closing_balance"]))
    except (KeyError, InvalidOperation) as exc:
        out["error"] = f"balance parse: {exc}"
        return out
    out["opening"] = opening
    out["closing"] = closing

    reader = csv_mod.DictReader(StringIO(body_str), delimiter="|")
    cols = set(reader.fieldnames or [])
    if cols != {"date", "description", "amount", "currency"}:
        out["error"] = f"csv cols mismatch: {sorted(cols)}"
        return out
    sum_amounts = Decimal("0")
    n_tx = 0
    bad = 0
    for row in reader:
        n_tx += 1
        try:
            sum_amounts += _parse_amount(row["amount"])
        except (InvalidOperation, KeyError):
            bad += 1
    out["n_tx"] = n_tx
    out["sum_amounts"] = sum_amounts
    out["diff"] = (closing - opening) - sum_amounts
    out["ok"] = bad == 0
    if bad:
        out["error"] = f"{bad} amount-unparseable rows"
    return out


def classify(p: dict) -> str:
    if not p["ok"] or p["n_tx"] == 0:
        return "rojo"
    if p["diff"] is not None and abs(p["diff"]) > TOLERANCE:
        return "rojo"
    return "verde"


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bytes_len = len(PROMPT_G.encode("utf-8"))
    print(f"Spike 9.5e pase 7 (final) — model=gemini-2.5-flash, thinking auto")
    print(f"Variation G: {bytes_len} bytes")
    print(f"Output: {OUT_DIR}")
    print(f"Plan:   1 variación × {len(REPR_PDFS)} PDFs × {RUNS} runs = {len(REPR_PDFS) * RUNS} calls")
    print()

    (OUT_DIR / "prompt-G.txt").write_text(PROMPT_G, encoding="utf-8")
    summary: list[dict] = []

    for pdf_name in REPR_PDFS:
        pdf_path = SAMPLES_DIR / pdf_name
        if not pdf_path.exists():
            print(f"SKIP {pdf_name}")
            continue
        pdf_bytes = pdf_path.read_bytes()
        print(f"PDF: {pdf_name}")

        for i in range(1, RUNS + 1):
            run_dir = OUT_DIR / f"G-{pdf_name.replace('/', '_')}-run{i}"
            run_dir.mkdir(exist_ok=True)
            try:
                raw, latency, thoughts = call_gemini(PROMPT_G, pdf_bytes, "gemini-2.5-flash")
                (run_dir / "raw.txt").write_text(raw, encoding="utf-8")
                parsed = parse_response(raw)
                color = classify(parsed)
                metrics = {
                    "ok": parsed["ok"], "error": parsed["error"],
                    "n_tx": parsed["n_tx"],
                    "opening": str(parsed["opening"]) if parsed["opening"] is not None else None,
                    "closing": str(parsed["closing"]) if parsed["closing"] is not None else None,
                    "sum_amounts": str(parsed["sum_amounts"]) if parsed["sum_amounts"] is not None else None,
                    "diff": str(parsed["diff"]) if parsed["diff"] is not None else None,
                    "latency_s": round(latency, 2),
                    "raw_bytes": len(raw.encode("utf-8")),
                    "thoughts_tokens": thoughts,
                    "color": color,
                }
                (run_dir / "parsed.json").write_text(
                    json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                summary.append({"variation": "G", "pdf": pdf_name, "run": i, **metrics})
                print(f"  run {i}: {color:<8}  n_tx={parsed['n_tx']:>3}  "
                      f"opening={str(parsed['opening'] or 'N/A'):<12} "
                      f"diff={str(parsed['diff'] or 'N/A'):<14}  "
                      f"{latency:.1f}s  thoughts={thoughts}t  {parsed['error'] or ''}")
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
                (run_dir / "error.txt").write_text(err, encoding="utf-8")
                summary.append({"variation": "G", "pdf": pdf_name, "run": i,
                                "ok": False, "error": err, "n_tx": 0, "opening": None,
                                "closing": None, "sum_amounts": None, "diff": None,
                                "latency_s": 0, "raw_bytes": 0, "thoughts_tokens": 0,
                                "color": "rojo"})
                print(f"  run {i}: ERROR {err}")

    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print("=== Aggregated ===")
    n_verde = sum(1 for s in summary if s["color"] == "verde")
    avg_lat = sum(s["latency_s"] for s in summary) / max(len(summary), 1)
    avg_bytes = sum(s["raw_bytes"] for s in summary) / max(len(summary), 1)
    print(f"  G: {n_verde}/{len(summary)} verde  avg_latency={avg_lat:.1f}s  avg_bytes={avg_bytes:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Spike 9.5e Task 0 — pase 2: Variación C (pipe-delimiter + header row obligatorio).

Aplica los 2 fixes del diagnóstico del pase 1:
  1. Delimitador `|` en vez de `,` para evitar ambigüedad de commas embedded
     (descripciones `TASA INT. 2,44%`, decimales chilenos).
  2. Header row CSV OBLIGATORIO y explícito.

Output: _bmad-output/coordination/9-5e-prompt-spike-c-{ts}/
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


PROMPT_C = """Eres un extractor de cartolas bancarias chilenas.

Lee este PDF y devuelve EXACTAMENTE este formato:

<header JSON en una línea>
---
<CSV>

Header JSON con estos campos exactos:
{"period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "currency": "CLP|USD|EUR", "opening_balance": <number>, "closing_balance": <number>}

CSV — delimitador `|` (pipe). La PRIMERA LÍNEA del CSV DEBE ser exactamente esta fila de encabezado:
date|description|amount|currency

Luego una fila por transacción del período, con los mismos 4 campos en ese orden separados por `|`.

Reglas:
- date en formato YYYY-MM-DD.
- amount con el signo TAL CUAL aparece en el PDF; no inviertas signos, no infieras convención bancaria. Usa punto como separador decimal si hay decimales (`1234.56`); sin separador de miles (`1234567` no `1.234.567`).
- description: texto crudo, puede contener cualquier carácter excepto `|`. Reemplazá `|` interno por espacio.
- currency por línea (típicamente coincide con header).

NO incluyas: subtotales, totales, cuotas futuras (00/N o X=0), explicaciones, markdown, ni texto fuera del formato.

Devuelve SOLO el formato indicado.
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
OUT_DIR = Path("_bmad-output/coordination") / f"9-5e-prompt-spike-c-{TS}"


def call_gemini(prompt: str, pdf_bytes: bytes, model: str) -> tuple[str, float]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        temperature=0.0,
    )
    start = time.monotonic()
    resp = client.models.generate_content(
        model=model,
        contents=[prompt, pdf_part],
        config=config,
    )
    return resp.text or "", time.monotonic() - start


def _strip_fence(s: str) -> str:
    s = re.sub(r"^```(?:json|csv|text)?\s*\n?", "", s.strip())
    s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def _parse_amount(raw: str) -> Decimal:
    """Pipe-delimited spec: punto como decimal, sin separador de miles. Pero tolerante."""
    s = raw.strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    # Acepta también 1.234,56 (CL) o 1,234.56 (US) por si Gemini ignora la regla
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
    out = {"ok": False, "error": None, "header": None, "n_tx": 0,
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
    out["header"] = header

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
    expected = {"date", "description", "amount", "currency"}
    if cols != expected:
        out["error"] = f"csv cols mismatch: got={sorted(cols)} expected={sorted(expected)}"
        return out

    sum_amounts = Decimal("0")
    n_tx = 0
    bad_rows = 0
    bad_details: list[str] = []
    for row in reader:
        n_tx += 1
        try:
            sum_amounts += _parse_amount(row["amount"])
        except (InvalidOperation, KeyError) as exc:
            bad_rows += 1
            if len(bad_details) < 3:
                bad_details.append(f"row {n_tx}: {row.get('amount', '?')!r} ({exc})")

    out["n_tx"] = n_tx
    out["sum_amounts"] = sum_amounts
    out["diff"] = (closing - opening) - sum_amounts
    out["ok"] = bad_rows == 0
    if bad_rows:
        out["error"] = f"{bad_rows} amount-unparseable rows ({'; '.join(bad_details)})"
    return out


def classify(parsed: dict) -> str:
    if not parsed["ok"]:
        return "rojo"
    if parsed["n_tx"] == 0:
        return "rojo"
    if parsed["diff"] is not None and abs(parsed["diff"]) > TOLERANCE:
        return "rojo"
    return "verde"


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 2

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bytes_len = len(PROMPT_C.encode("utf-8"))
    print(f"Spike 9.5e pase 2 — model={model}")
    print(f"Variation C: {bytes_len} bytes")
    print(f"Output: {OUT_DIR}")
    print(f"Plan:   1 variación × {len(REPR_PDFS)} PDFs × {RUNS} runs = {len(REPR_PDFS) * RUNS} calls")
    print()

    (OUT_DIR / "prompt-C.txt").write_text(PROMPT_C, encoding="utf-8")
    summary: list[dict] = []

    for pdf_name in REPR_PDFS:
        pdf_path = SAMPLES_DIR / pdf_name
        if not pdf_path.exists():
            print(f"  SKIP {pdf_name} — not found")
            continue
        pdf_bytes = pdf_path.read_bytes()
        print(f"PDF: {pdf_name}")

        for i in range(1, RUNS + 1):
            run_dir = OUT_DIR / f"C-{pdf_name.replace('/', '_')}-run{i}"
            run_dir.mkdir(exist_ok=True)
            try:
                raw, latency = call_gemini(PROMPT_C, pdf_bytes, model)
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
                    "color": color,
                }
                (run_dir / "parsed.json").write_text(
                    json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                summary.append({"variation": "C", "pdf": pdf_name, "run": i, **metrics})
                print(f"  run {i}: {color:<8}  n_tx={parsed['n_tx']:>3}  "
                      f"diff={str(parsed['diff'] or 'N/A'):<14}  "
                      f"{latency:.1f}s  {len(raw)}b  {parsed['error'] or ''}")
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
                (run_dir / "error.txt").write_text(err, encoding="utf-8")
                summary.append({"variation": "C", "pdf": pdf_name, "run": i,
                                "ok": False, "error": err, "n_tx": 0, "opening": None,
                                "closing": None, "sum_amounts": None, "diff": None,
                                "latency_s": 0, "raw_bytes": 0, "color": "rojo"})
                print(f"  run {i}: ERROR {err}")

    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print("=== Aggregated ===")
    n_verde = sum(1 for s in summary if s["color"] == "verde")
    avg_lat = sum(s["latency_s"] for s in summary) / max(len(summary), 1)
    avg_bytes = sum(s["raw_bytes"] for s in summary) / max(len(summary), 1)
    print(f"  C: {n_verde}/{len(summary)} verde  avg_latency={avg_lat:.1f}s  avg_bytes={avg_bytes:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Spike 9.5e — diagnóstico thinking_budget.

Hipótesis: Gemini web flash tiene thinking habilitado por default; API SDK no.
Test: mismo PDF (Estado-26, peor caso), mismo prompt (Variación D), 3 configs.

Output: _bmad-output/coordination/9-5e-thinking-spike-{ts}/
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


# Variación D (mismo prompt que el pase 3)
PROMPT_D = """Eres un extractor de cartolas bancarias chilenas.

Lee este PDF y devuelve EXACTAMENTE este formato:

<header JSON en una línea>
---
<CSV>

Header JSON con estos campos exactos:
{"period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "currency": "CLP|USD|EUR", "opening_balance": <number>, "closing_balance": <number>}

opening_balance = saldo/deuda del PERÍODO ANTERIOR. Labels típicos en el PDF: "SALDO ANTERIOR", "MONTO FACTURADO ANTERIOR", "DEUDA ANTERIOR", "SALDO PERIODO ANTERIOR". Si no encontrás label explícito, usá 0.
closing_balance = saldo/deuda al CIERRE del período. Labels típicos: "MONTO FACTURADO A PAGAR", "NUEVO SALDO", "SALDO ACTUAL", "DEUDA TOTAL".

CSV — delimitador `|` (pipe). La PRIMERA LÍNEA del CSV DEBE ser exactamente esta fila de encabezado:
date|description|amount|currency

Luego una fila por transacción del período, con los mismos 4 campos en ese orden separados por `|`.

Reglas:
- date en formato YYYY-MM-DD.
- amount con el signo TAL CUAL aparece en el PDF; no inviertas signos, no infieras convención bancaria. Punto como separador decimal si hay decimales (`1234.56`); sin separador de miles (`1234567` no `1.234.567`).
- description: texto crudo, puede contener cualquier carácter excepto `|`. Reemplazá `|` interno por espacio.
- currency por línea (típicamente coincide con header).

INCLUÍ como transacciones:
- Todas las operaciones del período (compras, cargos, abonos, pagos, comisiones, impuestos, intereses).
- Cuotas pre-existentes que se cobran este mes (X/N con X≥1): date = fecha de operación original (o primer día del período si no aparece); description = descripción + " (cuota X/N)"; amount = valor de la cuota mensual con su signo.

NO incluyas: subtotales/totales (TOTAL TARJETA, MONTO FACTURADO A PAGAR como línea, etc.), cuotas futuras (00/N o X=0), explicaciones, markdown, ni texto fuera del formato.

Devuelve SOLO el formato indicado.
"""

PDF_NAME = "estado-de-cuenta (26).pdf"
SAMPLES_DIR = Path("samples")
TOLERANCE = Decimal("100")

TS = datetime.now().strftime("%Y-%m-%d-%H%M%S")
OUT_DIR = Path("_bmad-output/coordination") / f"9-5e-thinking-spike-{TS}"


def call_gemini(prompt: str, pdf_bytes: bytes, model: str, thinking_budget: int | None) -> tuple[str, float, int]:
    """Returns (raw_text, latency, thoughts_tokens)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

    config_kwargs = {
        "response_mime_type": "text/plain",
        "temperature": 0.0,
    }
    if thinking_budget is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=thinking_budget,
        )
    config = types.GenerateContentConfig(**config_kwargs)

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


CONFIGS = [
    ("flash-no-thinking-explicit", "gemini-2.5-flash", 0),
    ("flash-thinking-auto", "gemini-2.5-flash", -1),
    ("flash-thinking-max", "gemini-2.5-flash", 8192),
]


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = SAMPLES_DIR / PDF_NAME
    pdf_bytes = pdf_path.read_bytes()

    print(f"Thinking diagnostic — PDF: {PDF_NAME}")
    print(f"Output: {OUT_DIR}\n")

    summary = []
    for label, model, budget in CONFIGS:
        print(f"=== {label} (model={model}, thinking_budget={budget}) ===")
        try:
            raw, latency, thoughts = call_gemini(PROMPT_D, pdf_bytes, model, budget)
            run_dir = OUT_DIR / label
            run_dir.mkdir(exist_ok=True)
            (run_dir / "raw.txt").write_text(raw, encoding="utf-8")
            parsed = parse_response(raw)
            color = classify(parsed)
            metrics = {
                "label": label, "model": model, "thinking_budget": budget,
                "color": color, "n_tx": parsed["n_tx"],
                "opening": str(parsed["opening"]) if parsed["opening"] is not None else None,
                "closing": str(parsed["closing"]) if parsed["closing"] is not None else None,
                "diff": str(parsed["diff"]) if parsed["diff"] is not None else None,
                "latency_s": round(latency, 2),
                "raw_bytes": len(raw.encode("utf-8")),
                "thoughts_tokens": thoughts,
                "error": parsed["error"],
            }
            (run_dir / "parsed.json").write_text(
                json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            summary.append(metrics)
            print(f"  {color:<8}  n_tx={parsed['n_tx']:>3}  "
                  f"opening={str(parsed['opening'] or 'N/A'):<10} "
                  f"diff={str(parsed['diff'] or 'N/A'):<14}  "
                  f"{latency:.1f}s  thoughts={thoughts}t  {parsed['error'] or ''}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            summary.append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
        print()

    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

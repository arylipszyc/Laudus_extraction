"""Spike 9.5e Task 0 — prompt discovery (THROWAWAY, no cablea producción).

Corre 2 variaciones del prompt liviano contra 3 PDFs × 3 runs cada uno = 18 calls.
Captura raw responses + balance metrics. Decide el prompt ganador empíricamente.

Output: _bmad-output/coordination/9-5e-prompt-spike-{ts}/
  prompt-A.txt, prompt-B.txt     — texto exacto de cada variación
  {var}-{pdf}-run{i}/raw.txt     — response cruda de Gemini
  {var}-{pdf}-run{i}/parsed.json — métricas
  summary.json                   — agregado
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


# ── Variación A — minimalista pura ──────────────────────────────────────
PROMPT_A = """Eres un extractor de cartolas bancarias chilenas.

Lee este PDF y devuelve EXACTAMENTE este formato:

<header JSON en una línea>
---
<CSV>

Header JSON con estos campos exactos:
{"period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "currency": "CLP|USD|EUR", "opening_balance": <number>, "closing_balance": <number>}

CSV con estas columnas exactas en este orden:
date,description,amount,currency

Reglas:
- Una fila por transacción del período.
- date en formato YYYY-MM-DD.
- amount con el signo TAL CUAL aparece en el PDF; no inviertas signos, no infieras convención bancaria.
- currency por línea (típicamente coincide con header).

NO incluyas: subtotales, totales, cuotas futuras (00/N o X=0), explicaciones, markdown, comillas en strings que no las requieran, ni texto fuera del formato.

Devuelve SOLO el formato indicado.
"""

# ── Variación B — A + hint sobre cuotas pre-existentes ───────────────────
PROMPT_B = PROMPT_A + """
SÍ incluye: cuotas pre-existentes que se cobran este mes (X/N con X≥1). Para cada cuota:
- date = fecha de operación original; si el PDF no la muestra, usa el primer día del período.
- description = descripción del comercio + sufijo " (cuota X/N)".
- amount = valor de la cuota mensual (con su signo del PDF).
"""

VARIATIONS = {"A": PROMPT_A, "B": PROMPT_B}

REPR_PDFS = [
    "bci-visa-202604.pdf",
    "santander-mastercard-202604.pdf",
    "estado-de-cuenta (26).pdf",
]

RUNS = 3
SAMPLES_DIR = Path("samples")
TOLERANCE = Decimal("100")  # mismo umbral que BALANCE_MISMATCH_TOLERANCE_CLP

TS = datetime.now().strftime("%Y-%m-%d-%H%M%S")
OUT_DIR = Path("_bmad-output/coordination") / f"9-5e-prompt-spike-{TS}"


# ── Gemini call ─────────────────────────────────────────────────────────


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


# ── Parsing & metrics ────────────────────────────────────────────────────


def _strip_fence(s: str) -> str:
    s = re.sub(r"^```(?:json|csv|text)?\s*\n?", "", s.strip())
    s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def _parse_amount(raw: str) -> Decimal:
    """Acepta `1234.56`, `1.234,56` (CL), `1,234.56` (US), `-50000`, `(50000)`."""
    s = raw.strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # 1.234,56 CL
            s = s.replace(".", "").replace(",", ".")
        else:  # 1,234.56 US
            s = s.replace(",", "")
    elif "," in s:
        # ambiguo: si pinta como miles (1,234) no decimal; heurística: si después de ',' hay 3 dígitos exactos → miles
        idx = s.rfind(",")
        if len(s) - idx - 1 == 3 and not "." in s[idx:]:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    # else: dot separator only — tratar tal cual (puede ser miles CL o decimal US)
    # heurística adicional: si hay 2+ puntos, son miles CL
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

    reader = csv_mod.DictReader(StringIO(body_str))
    cols = set(reader.fieldnames or [])
    expected = {"date", "description", "amount", "currency"}
    if cols != expected:
        out["error"] = f"csv cols mismatch: got={sorted(cols)} expected={sorted(expected)}"
        return out

    sum_amounts = Decimal("0")
    n_tx = 0
    bad_rows = 0
    for row in reader:
        n_tx += 1
        try:
            sum_amounts += _parse_amount(row["amount"])
        except (InvalidOperation, KeyError):
            bad_rows += 1

    out["n_tx"] = n_tx
    out["sum_amounts"] = sum_amounts
    out["diff"] = (closing - opening) - sum_amounts
    out["ok"] = bad_rows == 0
    if bad_rows:
        out["error"] = f"{bad_rows} amount-unparseable rows"
    return out


def classify(parsed: dict) -> str:
    if not parsed["ok"]:
        return "rojo"
    if parsed["n_tx"] == 0:
        return "rojo"
    if parsed["diff"] is not None and abs(parsed["diff"]) > TOLERANCE:
        return "rojo"
    return "verde"


# ── Main ────────────────────────────────────────────────────────────────


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set (check .env)", file=sys.stderr)
        return 2

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Spike 9.5e — model={model}")
    print(f"Output:  {OUT_DIR}")
    print(f"Plan:    {len(VARIATIONS)} variaciones × {len(REPR_PDFS)} PDFs × {RUNS} runs = "
          f"{len(VARIATIONS) * len(REPR_PDFS) * RUNS} calls")
    print()

    summary: list[dict] = []
    for var_name, prompt in VARIATIONS.items():
        bytes_len = len(prompt.encode("utf-8"))
        (OUT_DIR / f"prompt-{var_name}.txt").write_text(prompt, encoding="utf-8")
        print(f"=== Variation {var_name} ({bytes_len} bytes) ===")

        for pdf_name in REPR_PDFS:
            pdf_path = SAMPLES_DIR / pdf_name
            if not pdf_path.exists():
                print(f"  SKIP {pdf_name} — not found")
                continue
            pdf_bytes = pdf_path.read_bytes()
            print(f"  PDF: {pdf_name}")

            for i in range(1, RUNS + 1):
                run_label = f"{var_name}-{pdf_name.replace('/', '_')}-run{i}"
                run_dir = OUT_DIR / run_label
                run_dir.mkdir(exist_ok=True)
                try:
                    raw, latency = call_gemini(prompt, pdf_bytes, model)
                    (run_dir / "raw.txt").write_text(raw, encoding="utf-8")
                    parsed = parse_response(raw)
                    color = classify(parsed)
                    metrics = {
                        "ok": parsed["ok"],
                        "error": parsed["error"],
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
                    summary.append({
                        "variation": var_name, "pdf": pdf_name, "run": i, **metrics,
                    })
                    print(f"    run {i}: {color:<8}  n_tx={parsed['n_tx']:>3}  "
                          f"diff={str(parsed['diff'] or 'N/A'):<14}  "
                          f"{latency:.1f}s  {len(raw)}b  {parsed['error'] or ''}")
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}: {exc}"
                    (run_dir / "error.txt").write_text(err, encoding="utf-8")
                    summary.append({
                        "variation": var_name, "pdf": pdf_name, "run": i,
                        "ok": False, "error": err, "n_tx": 0, "opening": None,
                        "closing": None, "sum_amounts": None, "diff": None,
                        "latency_s": 0, "raw_bytes": 0, "color": "rojo",
                    })
                    print(f"    run {i}: ERROR {err}")

    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print("=== Aggregated ===")
    for var_name in VARIATIONS:
        rs = [s for s in summary if s["variation"] == var_name]
        n_verde = sum(1 for s in rs if s["color"] == "verde")
        avg_lat = sum(s["latency_s"] for s in rs) / max(len(rs), 1)
        avg_bytes = sum(s["raw_bytes"] for s in rs) / max(len(rs), 1)
        print(f"  {var_name}: {n_verde}/{len(rs)} verde  "
              f"avg_latency={avg_lat:.1f}s  avg_bytes={avg_bytes:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

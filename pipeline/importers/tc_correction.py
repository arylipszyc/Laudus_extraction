"""Corrección contable de Tarjetas de Crédito vía cartola — Story 6.2 (flujo de Valentina).

NO toca Laudus. Emite asientos contables estándar al importar la cartola de una TC:

- (a) compra/cuota → `Liabilities:EAG:TC:Real:<x>` (−) / `Expenses:<categoría>` (+)
- abono           → mismo asiento (a) con `amount` firmado (negativo) → se invierte solo
- (b) pago        → `Expenses:EAG:TC:<code>` (−lump) / `Liabilities:EAG:TC:Real:<x>` (+lump)
                    (saca el "gasto" lumpeado que dejó Laudus; el lump CLP lo provee el caller)
- (c) apertura    → `Liabilities:EAG:TC:Real:<x>` (−opening) / `Equity:Apertura:TarjetasSinDetalle` (+)
                    una sola vez por tarjeta (primera cartola)

Para cartolas USD los montos se convierten a CLP con un FX único (`fx`, provisto por el caller —
derivado de la liquidación que salda el estado, ver Story 6.2). CLP nacional → `fx = 1`.

El builder es PURO: recibe `fx`, el lump por pago (`lump_for`) y la categoría (`category_for`) ya
resueltos. La derivación del FX/lump desde Laudus (matching de la liquidación) vive afuera.
"""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable

from beancount.core import data
from beancount.core.amount import Amount

from backend.app.integrations.cartola_schema import CartolaCanonicalV1, CartolaTransaction
from pipeline.importers.categorization.service import CategorizationResult
from pipeline.importers.fx_calculator import TOLERANCE_PCT

OPENING_EQUITY = "Equity:Apertura:TarjetasSinDetalle"
_CLP = "CLP"

# Derivación de la cuenta de pasivo real desde la cuenta-gasto Laudus (AC6, transformación de
# string pura): `Expenses:EAG:TC:<stem>-<code>` → `Liabilities:EAG:TC:Real:<stem>`.
_EXPENSE_TC_PREFIX = "Expenses:EAG:TC:"
_TC_REAL_PREFIX = "Liabilities:EAG:TC:Real:"

# Ventana (días tras el cierre del estado) para buscar el pago que lo salda en Laudus.
_FX_WINDOW_DAYS = 75
# El estado USD se considera "saldado por la glosa" si el USD de la glosa == closing del estado.
_USD_MATCH_TOLERANCE = Decimal("0.01")

# Fallback por monto (pagos consolidados Santander: un asiento paga varias tarjetas, la glosa
# nombra UNA y su USD ≠ el de ESTA tarjeta). El CLP posteado a la cuenta-gasto de cada tarjeta SÍ
# es correcto → `fx = le.amount / total_usd` da el FX sano; BCCh (o banda) solo ELIGE cuál posting,
# nunca se vuelve la tasa (regla §12.1). Banda CLP/USD de plausibilidad cuando no hay BCCh ese mes.
_FX_BAND_LO = Decimal("850")
_FX_BAND_HI = Decimal("1000")

# Glosa del pago Laudus, formato chileno: "USD26.188,93 Visa BCI 1027 Abril" → 26188.93.
_GLOSA_USD_RE = re.compile(r"USD\s*([\d.]*\d,\d{2})")


def parse_glosa_usd(text: str) -> Decimal | None:
    """Extrae el monto USD de la glosa del pago Laudus (formato chileno). None si no aparece."""
    m = _GLOSA_USD_RE.search(text or "")
    if not m:
        return None
    return Decimal(m.group(1).replace(".", "").replace(",", "."))


def _fx_in_gate(fx: Decimal, bcch: Decimal | None) -> bool:
    """¿El FX candidato pasa el gate de selección? (BCCh ±tolerancia si existe, banda si no).

    BCCh/banda NO son la tasa — solo deciden si este posting es el pago plausible de la tarjeta
    (regla §12.1: la tasa siempre es CLP real / USD). `fx` debe ser > 0.
    """
    if fx <= 0:
        return False
    if bcch is not None and bcch != 0:
        return abs(fx - bcch) / bcch * Decimal("100") <= TOLERANCE_PCT
    return _FX_BAND_LO <= fx <= _FX_BAND_HI


def _select_by_amount(candidates: list, total_usd: Decimal, bcch: Decimal | None):
    """Elige el `LaudusEntry` cuyo `amount / total_usd` pasa el gate (pago consolidado, sin glosa).

    Con BCCh: el más cercano al BCCh dentro de tolerancia. Sin BCCh: el más temprano dentro de la
    banda (los `candidates` ya vienen ordenados por fecha). None si ninguno pasa → bloqueante.
    """
    if total_usd == 0:
        return None
    passing = [(le, le.amount / total_usd) for le in candidates]
    passing = [(le, fx) for le, fx in passing if _fx_in_gate(fx, bcch)]
    if not passing:
        return None
    if bcch is not None and bcch != 0:
        return min(passing, key=lambda lf: abs(lf[1] - bcch))[0]
    return passing[0][0]  # más temprano (candidates ordenados por fecha)


def derive_statement_fx(
    model: CartolaCanonicalV1,
    laudus_us_entries: list,
    *,
    window_days: int = _FX_WINDOW_DAYS,
    bcch: Decimal | None = None,
) -> dict:
    """FX único del estado USD desde el pago de Laudus que lo salda (Story 6.2 §FX, regla Ary).

    Busca en `laudus_us_entries` (asientos de la cuenta `...Us`, de `load_laudus_entries`) el pago
    fechado tras el cierre del estado cuya **glosa codifica el mismo USD que el `closing`** del estado.
    `FX = CLP_del_pago / USD_de_la_glosa`. Si ningún pago tiene la glosa (pago consolidado Santander),
    cae al **fallback por monto**: elige el posting a esta cuenta-gasto cuyo `amount / closing` pasa el
    gate BCCh (o banda de plausibilidad si no hay BCCh ese mes) — el CLP real, no una tasa estimada.
    Si ninguno pasa → bloqueante (falta un movimiento o el saldo rodó sin pago), NO se estima FX.

    Devuelve `{status, fx, lump_clp, glosa_usd, payment_date, reason}`. `status ∈ {ok, blocked}`.
    """
    total_usd = abs(model.balances.closing)
    end = model.period.end
    candidates = sorted(
        (le for le in laudus_us_entries if le.date >= end and (le.date - end).days <= window_days),
        key=lambda le: le.date,
    )
    for le in candidates:
        glosa = parse_glosa_usd(le.description)
        if glosa is not None and glosa != 0 and abs(glosa - total_usd) <= _USD_MATCH_TOLERANCE:
            return {"status": "ok", "fx": (le.amount / glosa), "lump_clp": le.amount,
                    "glosa_usd": glosa, "payment_date": le.date, "reason": None}
    # Fallback consolidado: la glosa no codifica este USD → elige el posting por monto (gate BCCh/banda).
    le = _select_by_amount(candidates, total_usd, bcch)
    if le is not None:
        return {"status": "ok", "fx": (le.amount / total_usd), "lump_clp": le.amount,
                "glosa_usd": None, "payment_date": le.date, "reason": None}
    return {"status": "blocked", "fx": None, "lump_clp": None, "glosa_usd": None, "payment_date": None,
            "reason": (f"sin pago Laudus que salde el estado (USD {total_usd}) en {window_days}d tras "
                       f"el cierre {end} — ¿falta un movimiento o el estado aún no se pagó?")}

# ── Clasificación de operation_type (§10.1, cierra el drop silencioso) ──
# Toda línea emite asiento (a) contra TC:Real; la contrapartida depende del tipo canónico.
_CONSUMO_OPS = {"compra", "cuota", "abono"}        # → Expenses:<cat> vía categorizador 9.7
_BANK_CHARGE_OPS = {"impuesto", "comision", "interes", "seguro", "mantencion"}  # → cuenta fija
_ADVANCE_OPS = {"avance"}                          # → Caja (NO es gasto)
_PAYMENT_OPS = {"pago"}                            # → asiento (b) reclasificación

BANK_CHARGES_ACCOUNT = "Expenses:EAG:GastosBancarios-430003"
CAJA_CLP = "Assets:EAG:Caja-111001"
CAJA_USD = "Assets:EAG:CajaUs-111003"
SUSPENSE_ACCOUNT = "Expenses:EAG:Suspense"

# ── Recomendación con colores (§10.2, Goal B) ──────────────────────────────────
# 3 colores, sin naranja. El color es advisory: el contador confirma SIEMPRE.
COLOR_GREEN = "green"
COLOR_YELLOW = "yellow"
COLOR_RED = "red"

# Sobre `historical` (confianza = #confirmaciones/30): ≥0.5 (≥15 conf) ya es señal sólida → verde.
_GREEN_CONFIDENCE = 0.5


def color_for(confidence: float, match_source: str) -> str:
    """Mapea (confianza, fuente) → color de la recomendación (§10.2). Función pura.

    🟢 verde    = `historical-30+`, o confianza alta (la glosa ya está muy confirmada).
    🟡 amarillo = `smart_importer` / `historical` con pocas confirmaciones / cargo bancario por
                  keyword (confianza media).
    🔴 rojo     = `pending`/Suspense, adivinanza de Gemini, o tipo no reconocido (confianza baja/nula).
    """
    src = match_source or ""
    if src in ("pending", "gemini"):
        return COLOR_RED
    if src == "historical-30+":
        return COLOR_GREEN
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
    if conf >= _GREEN_CONFIDENCE:
        return COLOR_GREEN
    if conf > 0.0:
        return COLOR_YELLOW
    return COLOR_RED


# Sinónimos sucios de Gemini → tipo canónico (barrido de 304 cartolas, §10.1).
_OP_SYNONYMS = {
    "compras p.a.t.": "compra", "pat": "compra", "compra_automatica": "compra",
    "cargo_automatico": "compra", "nota_credito": "abono",
}
_KNOWN_OPS = _CONSUMO_OPS | _BANK_CHARGE_OPS | _ADVANCE_OPS | _PAYMENT_OPS


def _normalize_op(raw_op: str | None, amount: Decimal) -> str:
    """Normaliza el `operation_type` sucio de Gemini a un tipo canónico (§10.1).

    `None`/vacío → `compra` si el monto es +, `abono` si es − (compras sin taggear; el signo decide).
    Sinónimos PAT/automática → `compra`; `nota_credito` → `abono`. Tipo canónico → pasa igual.
    Cualquier otra cosa → `""` (no reconocido → Suspense + reporte, nunca se descarta).
    """
    key = str(raw_op or "").strip().lower()  # `raw` es dict[str, Any]: un op no-str no debe crashear
    if not key:
        return "compra" if amount > 0 else "abono"
    if key in _OP_SYNONYMS:
        return _OP_SYNONYMS[key]
    if key in _KNOWN_OPS:
        return key
    return ""


def _posting(account: str, number: Decimal) -> data.Posting:
    return data.Posting(account, Amount(number, _CLP), None, None, None, None)


def _meta(*, line_no: int, bank_account_id: str, batch_id: str, op: str, fx: Decimal,
          year_month: str, category: "CategorizationResult | None" = None) -> dict:
    m = data.new_metadata("<tc-correction>", line_no)
    m.update({
        "source": "cartola-tc",
        "bank_account_id": bank_account_id,
        "batch_id": batch_id,
        "line": str(line_no),
        "operation_type": op,
        # Story 6.5b: período del ESTADO DE CUENTA (distinto de `date`, que es la fecha de la compra).
        # Una compra del 28-abr puede pertenecer al estado de mayo por la fecha de cierre/facturación.
        "period": year_month,
    })
    if fx != Decimal(1):
        m["fx"] = str(fx)
    # Goal B (§10.2): preserva la confianza+fuente del categorizador y su color advisory en el
    # asiento (a). El contador confirma SIEMPRE; el color solo le dice de un vistazo dónde fijarse.
    if category is not None:
        m["match_source"] = category.match_source
        m["confidence"] = str(category.confidence)
        m["color"] = color_for(category.confidence, category.match_source)
        # El contador confirma SIEMPRE — nada se auto-confirma. Por eso `suggested`/`pending`, NUNCA
        # `confirmed` (a diferencia del cartola_pdf_importer, que sí cierra en `*`): el color es la
        # señal de revisión, no una compuerta a auto.
        m["category_status"] = "pending" if category.match_source == "pending" else "suggested"
    return m


def build_tc_correction_entries(
    *,
    model: CartolaCanonicalV1,
    tc_real_account: str,
    expense_tc_account: str,
    fx: Decimal,
    lump_for: Callable[[CartolaTransaction], Decimal],
    category_for: Callable[[CartolaTransaction], "str | CategorizationResult"],
    batch_id: str,
    bank_account_id: str,
    emit_opening: bool,
    unmapped: list | None = None,
) -> list:
    """Asientos de corrección de una cartola de TC (flujo Valentina §6). Lista de `data.Transaction`.

    `fx`: CLP/unidad (1 para cartola CLP). `lump_for(tx)`: CLP del lump Laudus que reclasifica el
    pago `tx` (para CLP = magnitud de la línea; para USD = lump matcheado en Laudus). `category_for`:
    cuenta de gasto de una compra. `emit_opening`: True solo en la primera cartola de la tarjeta.
    """
    fx = Decimal(fx)
    year_month = model.period.end.strftime("%Y-%m")  # Story 6.5b: período del estado de cuenta
    entries: list = []

    for tx in model.transactions:
        raw_op = (tx.raw or {}).get("operation_type")
        op = _normalize_op(raw_op, tx.amount)
        category: CategorizationResult | None = None
        if op in _PAYMENT_OPS:
            # (b) reclasificación del pago: saca el gasto falso de la cuenta-gasto Laudus.
            lump = Decimal(lump_for(tx))
            if lump == 0:
                continue
            postings = [_posting(expense_tc_account, -lump), _posting(tc_real_account, lump)]
            meta_op = op
        else:
            # asiento (a): TODA línea (consumo/cargo/avance/abono/desconocido) toca TC:Real por
            # -monto×fx → el pasivo cuadra con el closing SIEMPRE. La contrapartida depende del tipo.
            # Sin redondear (precisión completa): evita el residuo de redondeo per-línea.
            clp = tx.amount * fx
            if clp == 0:
                continue
            if op in _CONSUMO_OPS:
                # abono = compra invertida por el signo del amount. `category_for` puede devolver un
                # `CategorizationResult` (preserva confianza+fuente+color en la meta, Goal B §10.2) o
                # un `str` (compat: solo la cuenta, sin meta de color).
                cat = category_for(tx)
                if isinstance(cat, CategorizationResult):
                    category = cat
                    counterpart = cat.category_account
                else:
                    counterpart = cat
            elif op in _BANK_CHARGE_OPS:
                counterpart = BANK_CHARGES_ACCOUNT     # FIJO, no pasa por el categorizador 9.7
            elif op in _ADVANCE_OPS:
                counterpart = CAJA_USD if tx.currency != _CLP else CAJA_CLP  # avance = plata, no gasto
            else:
                # No reconocido: red de seguridad (§10.1) — Suspense + reportar, NUNCA descartar.
                counterpart = SUSPENSE_ACCOUNT
                if unmapped is not None:
                    unmapped.append({"line": tx.line_no, "op": raw_op, "monto": tx.amount})
            postings = [_posting(tc_real_account, -clp), _posting(counterpart, clp)]
            meta_op = op or (raw_op or "desconocido")
        entries.append(data.Transaction(
            meta=_meta(line_no=tx.line_no, bank_account_id=bank_account_id, batch_id=batch_id,
                       op=meta_op, fx=fx, year_month=year_month, category=category),
            date=tx.date, flag="*", payee=None,
            narration=tx.description or f"line {tx.line_no}",
            tags=frozenset(), links=frozenset(), postings=postings,
        ))

    # (c) apertura — una sola vez por tarjeta. La deuda arrastrada va a Equity (no gasto).
    if emit_opening and model.balances.opening != 0:
        opening_clp = model.balances.opening * fx
        meta = _meta(line_no=0, bank_account_id=bank_account_id, batch_id=batch_id, op="apertura", fx=fx,
                     year_month=year_month)
        entries.append(data.Transaction(
            meta=meta, date=model.period.start, flag="*", payee=None,
            narration=f"Apertura TC {model.source.account_label}",
            tags=frozenset(), links=frozenset(),
            postings=[_posting(tc_real_account, -opening_clp), _posting(OPENING_EQUITY, opening_clp)],
        ))

    return entries


# ── Orquestador: cartola TC staged → asientos de corrección escritos al ledger (AC1-AC7) ──


class TcCorrectionBlocked(Exception):
    """La corrección no se puede emitir aún (falta el pago que da el FX/lump, o descuadre real)."""


def tc_real_account(expense_tc_account: str) -> str:
    """`Expenses:EAG:TC:<stem>-<code>` → `Liabilities:EAG:TC:Real:<stem>` (AC6, string puro).

    El stem copia EXACTO el de la cuenta-gasto Laudus (`...1027` CLP, `...1027Us` USD → cada una su
    propia `TC:Real`). Quita el sufijo `-<code>` del code sintético/Laudus.
    """
    if not expense_tc_account.startswith(_EXPENSE_TC_PREFIX):
        raise TcCorrectionBlocked(
            f"cuenta TC inesperada {expense_tc_account!r} (se esperaba prefijo {_EXPENSE_TC_PREFIX!r})")
    stem = expense_tc_account[len(_EXPENSE_TC_PREFIX):].rsplit("-", 1)[0]
    return _TC_REAL_PREFIX + stem


def _opening_exists(out_dir: Path, tc_real_account: str, *, exclude: Path | None = None) -> bool:
    """¿Ya hay un asiento de apertura para esta `TC:Real` en una cartola previa? (AC4 idempotencia).

    Escanea los `*-tc.beancount` ya escritos y busca una Transaction con `operation_type=apertura`
    que toque la cuenta. Evita repetir la apertura en cartolas siguientes de la misma tarjeta.

    `exclude`: archivo de salida de ESTA corrida — se salta para que re-importar la misma cartola
    (mismo slug → se sobrescribe ese archivo) no detecte su propia apertura previa y la pierda.
    """
    from beancount.core.data import Transaction
    from beancount.parser import parser

    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return False
    exclude = Path(exclude).resolve() if exclude is not None else None
    for path in sorted(out_dir.glob("*-tc.beancount")):
        if exclude is not None and path.resolve() == exclude:
            continue
        entries, _err, _opt = parser.parse_file(str(path))
        for e in entries:
            if (isinstance(e, Transaction) and (e.meta or {}).get("operation_type") == "apertura"
                    and any(p.account == tc_real_account for p in e.postings)):
                return True
    return False


def _resolve_usd_lump(monto_cancelado_usd: Decimal, laudus_payments: list,
                      *, bcch: Decimal | None = None) -> Decimal | None:
    """CLP real del pago Laudus que salda el `MONTO CANCELADO` de la cartola (glosa, luego monto).

    El asiento (b) usa el lump REAL (no `USD × FX_del_estado`): el MONTO CANCELADO se liquidó al FX
    del estado anterior. Glosa primero; si ninguna codifica ese USD (pago consolidado Santander), cae
    al match por monto con el mismo gate BCCh/banda que el FX del estado. None si ninguno → bloqueante.
    """
    for le in laudus_payments:
        glosa = parse_glosa_usd(le.description)
        if glosa is not None and glosa != 0 and abs(glosa - monto_cancelado_usd) <= _USD_MATCH_TOLERANCE:
            return le.amount
    le = _select_by_amount(laudus_payments, monto_cancelado_usd, bcch)
    return le.amount if le is not None else None


def correct_tc_cartola(batch_id: str, importer, ledger_root, *, ts: str) -> dict:
    """Corrige la contabilidad de una TC desde su cartola staged (Story 6.2, flujo Valentina).

    A diferencia de la cuenta corriente (modelo A 6.1, reconcilia-sin-postear), la TC **SÍ postea**:
    Laudus solo tiene el pago lump, no las compras. Emite los asientos (a)/(b)/(c), valida el cuadre y
    los escribe a `imports/cartolas/{slug}-tc.beancount` (lock + bean-check + git, patrón `promote`).

    USD: deriva el FX único del estado desde el pago Laudus que lo salda (glosa USD == closing) y el
    lump de cada `MONTO CANCELADO` por glosa; sin pago que cuadre → bloqueante (no estima). CLP: fx=1,
    lump = magnitud de la línea. Devuelve `{status: corrected|blocked, ...}`.
    """
    from bootstrap.account_mapping import slugify
    from pipeline.importers.cartola_pdf_importer import render_entries
    from pipeline.importers.laudus_run import acquire_lock, bean_check, git_commit_push
    from pipeline.importers.matching_engine import load_laudus_entries

    root = Path(ledger_root)
    staging = root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json"
    out_dir = root / "imports" / "cartolas"
    laudus_dir = root / "imports" / "laudus"
    main_path = root / "main.beancount"
    lock_path = root / ".import.lock"

    model = CartolaCanonicalV1.model_validate_json(staging.read_text(encoding="utf-8"))
    bank_account_id = model.source.bank_account_id
    expense_tc = importer.resolver.resolve(bank_account_id)
    tc_real = tc_real_account(expense_tc)
    is_usd = model.currency != _CLP

    result = {"batch_id": batch_id, "status": "blocked", "currency": model.currency, "fx": None,
              "purchases": 0, "payments": 0, "opening_emitted": False, "unmapped": [],
              "fx_bcch": None, "fx_deviation_pct": None,
              "git_commit_sha": None, "reason": None}

    # Archivo de salida — incluye el stem de la `TC:Real` para que CLP (`<x>`) y USD (`<x>Us`) de la
    # misma tarjeta/mes (mismo banco + last4) no colisionen en el mismo `{slug}-tc.beancount`.
    last4 = importer.resolver.get(bank_account_id).last4 or "xxxx"
    stem = tc_real.rsplit(":", 1)[-1]
    slug = (f"{slugify(model.source.bank_name) or 'Banco'}-{last4}-{stem}-"
            f"{model.period.end.strftime('%Y-%m')}")
    out_file = out_dir / f"{slug}-tc.beancount"

    # FX + lump por pago.
    if is_usd:
        from pipeline.importers.fx_calculator import lookup_bcch
        ym = model.period.end.strftime("%Y-%m")
        bcch = lookup_bcch(root / "_meta" / "fx-bcch-eom.jsonl", ym)
        window = timedelta(days=_FX_WINDOW_DAYS)
        laudus_payments = load_laudus_entries(
            laudus_dir, expense_tc, model.period.start - window, model.period.end + window)
        fx_res = derive_statement_fx(model, laudus_payments, bcch=bcch)
        if fx_res["status"] != "ok":
            result["reason"] = fx_res["reason"]
            return result
        fx = fx_res["fx"]
        settling_lump = fx_res["lump_clp"]
        # Pre-resuelve el lump de cada MONTO CANCELADO (asiento b) por glosa, antes de construir.
        lumps: dict[int, Decimal] = {}
        for tx in model.transactions:
            # Mismo `_normalize_op` que el builder: si no, un `pago` con mayúsculas/espacios se
            # normaliza a pago al construir pero acá no se pre-resuelve → KeyError en `lump_for`.
            if _normalize_op((tx.raw or {}).get("operation_type"), tx.amount) in _PAYMENT_OPS:
                lump = _resolve_usd_lump(abs(tx.amount), laudus_payments, bcch=bcch)
                if lump is None:
                    result["reason"] = (f"sin pago Laudus que matchee el MONTO CANCELADO "
                                        f"USD {abs(tx.amount)} (línea {tx.line_no})")
                    return result
                lumps[tx.line_no] = lump
        def lump_for(tx: CartolaTransaction) -> Decimal:
            return lumps[tx.line_no]
    else:
        fx = Decimal(1)
        settling_lump = None
        def lump_for(tx: CartolaTransaction) -> Decimal:
            return abs(tx.amount)

    predictor = importer.category_predictor

    def category_for(tx: CartolaTransaction) -> CategorizationResult:
        # Goal B (§10.2): preserva confianza+fuente (no solo `[0]`). El `CategorizationService` real
        # expone `categorize()` → `CategorizationResult`; el `NoopCategoryPredictor` solo `predict()`
        # (sin confianza) → se reconstruye un result con confidence=0 (cae a rojo, que es lo correcto:
        # Noop manda todo a Suspense/pending).
        categorize = getattr(predictor, "categorize", None)
        if categorize is not None:
            return categorize(tx.description, tx.amount, bank_account_id)
        account, match_source, _flag = predictor.predict(tx.description, tx.amount, bank_account_id)
        return CategorizationResult(account, match_source, 0.0, _flag)

    emit_opening = not _opening_exists(out_dir, tc_real, exclude=out_file)

    entries = build_tc_correction_entries(
        model=model, tc_real_account=tc_real, expense_tc_account=expense_tc, fx=fx,
        lump_for=lump_for, category_for=category_for, batch_id=batch_id,
        bank_account_id=bank_account_id, emit_opening=emit_opening, unmapped=result["unmapped"])

    # Validación de cordura del FX (solo USD). El FX se deriva del pago que salda el estado
    # (`lump/closing` — regla §12.1: NO se usa BCCh como tasa, eso descuadraría `Σ(compras × fx)`). Acá
    # el dólar observado de cierre (Story 9.10, `_meta/fx-bcch-eom.jsonl`) solo valida que el FX derivado
    # sea plausible: desviación > 5% del BCCh = el lump o el total USD no corresponden → bloqueante. Sin
    # BCCh ese mes → no bloquea (mismo criterio que 9.6b). Supuesto: la TC se paga al contado; un saldo
    # arrastrado se captura aparte en el asiento (c) de apertura y NO descuadra este check (a diferencia
    # del viejo `residuo`, que se prendía con cualquier saldo arrastrado sin validar el lump real).
    if is_usd:
        from pipeline.importers.fx_calculator import calculate_fx
        fx_check = calculate_fx(model.balances.closing, settling_lump, bcch)
        result["fx_bcch"] = str(fx_check.bcch) if fx_check.bcch is not None else None
        result["fx_deviation_pct"] = (float(fx_check.deviation_pct)
                                      if fx_check.deviation_pct is not None else None)
        if fx_check.state in ("fx-out-of-tolerance", "fx-implausible"):
            result["reason"] = (
                f"FX derivado {fx} CLP/USD no cuadra vs BCCh {ym} (bcch={fx_check.bcch}, "
                f"desviación={fx_check.deviation_pct}%, {fx_check.state}) — ¿el lump o el total USD "
                f"no corresponden?")
            return result

    result["fx"] = str(fx)
    result["purchases"] = sum(1 for tx in model.transactions
                              if _normalize_op((tx.raw or {}).get("operation_type"), tx.amount) in _CONSUMO_OPS)
    result["payments"] = sum(1 for tx in model.transactions
                             if _normalize_op((tx.raw or {}).get("operation_type"), tx.amount) in _PAYMENT_OPS)
    result["opening_emitted"] = emit_opening and model.balances.opening != 0

    with acquire_lock(lock_path):
        out_file.write_text(render_entries(entries), encoding="utf-8")
        ok, detail = bean_check(main_path)
        if not ok:
            out_file.unlink(missing_ok=True)
            result["reason"] = f"bean-check failed: {detail}"
            return result
        staging.unlink(missing_ok=True)
        result["git_commit_sha"] = git_commit_push(
            root, [f"ledger/imports/cartolas/{out_file.name}"],
            f"[tc-correction] {slugify(model.source.bank_name)} {model.period.end.strftime('%Y-%m')}: "
            f"{result['purchases']} compra(s), {result['payments']} pago(s)")
        result["status"] = "corrected"
        result["file"] = str(out_file)
        return result

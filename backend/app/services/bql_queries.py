"""BQL query functions for the dashboard endpoints (Story 9.2 AC3/AC4).

Each function takes a `LedgerService` plus the same params the Sheets path
receives and returns a dict shaped identically to the Sheets response
(`{"data": [...], "meta": {"last_sync": ...}}`) so the frontend cannot tell
which engine produced the response (AC2).

Amount semantics here are best-effort double-entry mappings (debit/credit split
by sign); true parity vs. the Laudus-derived Sheets values is validated by the
parity suite once the ledger is fully bootstrapped — see
`tests/README-beancount-parity.md` (AC9).

Account-name convention (from `accounts.beancount`):
    Assets:EAG:Bancos:BancoBci10160175-111005
      → entity   = 2nd path component ("EAG")
      → metadata = Open directive meta: code, laudus_account_name, laudus_categoria1..3
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from beancount.core.data import Open, Transaction

from backend.app.services.ledger_service import LedgerService, tx_id_of

# Roots that make up the balance sheet (AC3).
_BALANCE_SHEET_ROOTS = "Assets|Liabilities|Equity"

# Grupos de consolidación explícitos (Story 11.1, FR45/FR46). Clave = entidad
# consultable que resuelve a un consolidado; el resto de VALID_ENTITIES sigue
# el path per-entity. "EAG" espeja el tab legacy `balance_sheet_eag` de Sheets:
# las hijas son egresos de EAG (971/1077 tx con contraparte en EAG); seleccionar
# una hija en el filtro sigue devolviendo SU slice — la separación por entidad
# no se pierde. "FondoComun"/FFCC/JAB son los labels DEFINITIVOS, fijados por
# la story 11.2 (ratificados por Ary 2026-07-11 vía Excel de clasificación).
CONSOLIDATION_GROUPS: dict[str, frozenset[str]] = {
    "EAG": frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"}),
    "FondoComun": frozenset({"FFCC", "JAB"}),
}

# Namespaces de Equity SIN segmento de entidad — legacy del libro EAG (lista
# congelada; las entidades nuevas deben llevar entidad en el path, ej.
# Equity:FFCC:Apertura, para que la asignación a grupo siga siendo mecánica).
_ENTITYLESS_EQUITY_NAMESPACES = ("Apertura", "Reconciliation")  # → grupo EAG


def _account_meta(entries: list) -> dict[str, dict]:
    """Map full account name → its Open directive metadata."""
    return {e.account: (e.meta or {}) for e in entries if isinstance(e, Open)}


import functools


def _entity_pattern(roots: str, entity: str) -> str:
    """Regex matching `<root>:<entity>:...` for the given roots."""
    return f"^({roots}):{entity}:"


@functools.lru_cache(maxsize=16)
def _compiled_entity_pattern(roots: str, entity: str) -> re.Pattern:
    return re.compile(_entity_pattern(roots, entity))


@functools.lru_cache(maxsize=16)
def _group_pattern(roots: str, group: str) -> str:
    """Regex del consolidado: entidades del grupo como 2º segmento; el grupo EAG
    suma además sus namespaces de Equity sin segmento de entidad (legacy)."""
    members = "|".join(sorted(CONSOLIDATION_GROUPS[group]))
    pattern = f"^({roots}):({members}):"
    if group == "EAG":
        legacy = "|".join(_ENTITYLESS_EQUITY_NAMESPACES)
        pattern += f"|^Equity:({legacy})(:|$)"
    # beanquery evalúa `~` con re.IGNORECASE; el aislamiento de grupo (FR45)
    # debe ser case-sensitive o una entidad case-variante de un miembro se
    # consolidaría en silencio (patch code-review 11.1).
    return f"(?-i:{pattern})"


def _clp(inventory) -> float:
    """Extract the CLP number from a beanquery `sum(position)` Inventory."""
    if inventory is None:
        return 0.0
    amount = inventory.get_currency_units("CLP")
    if amount is None or amount.number is None:
        return 0.0
    return float(amount.number)


def _max_transaction_date(entries: list, pattern: str | None = None) -> str | None:
    """Latest transaction date as ISO string, or None.

    Con `pattern` (regex de cuenta) solo cuentan las transacciones con alguna
    pata en ese universo: la frescura de un grupo no debe avanzar porque OTRO
    libro del ledger tenga datos más nuevos (NFR20, Story 12.4)."""
    rx = re.compile(pattern) if pattern else None
    dates = [
        e.date
        for e in entries
        if isinstance(e, Transaction)
        and (rx is None or any(rx.search(p.account) for p in e.postings))
    ]
    return max(dates).isoformat() if dates else None


# Universo de frescura: TODAS las raíces — un asiento solo-P&L también cuenta
# como movimiento fresco del libro (paridad con el máximo global pre-12.4).
_ALL_ROOTS = "Assets|Liabilities|Equity|Income|Expenses"


def _freshness_pattern(entity: str) -> str:
    """Patrón que define la FRESCURA de `entity`: el universo de su grupo de
    consolidación (= su libro), no la entidad sola — una hija muestra la
    frescura del libro EAG (idéntico al comportamiento pre-12.4, cuando el
    máximo global del ledger era el máximo del libro EAG) y FFCC/JAB la del
    libro RUT2."""
    group = entity if entity in CONSOLIDATION_GROUPS else next(
        (g for g, members in CONSOLIDATION_GROUPS.items() if entity in members),
        None,
    )
    if group is not None:
        return _group_pattern(_ALL_ROOTS, group)
    # Case-sensitive explícito (paridad con _group_pattern): la frescura de una
    # entidad no-grupo no debe absorber una cuenta case-variante (misma decisión
    # que el patch 11.1). Rama inalcanzable vía API hoy (toda VALID_ENTITIES es
    # miembro de un grupo); el `(?-i:)` fija la intención para entidades futuras.
    return f"(?-i:{_entity_pattern(_ALL_ROOTS, entity)})"


def balance_sheet_via_beancount(
    ledger: LedgerService,
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Balance sheet for `entity` as of `date_to` (cumulative), Sheets-shaped.

    `date_from` is accepted for signature parity but does not bound a
    point-in-time balance sheet (AC3 queries `AT date_range.end`).
    """
    entries = ledger.entries()
    meta = _account_meta(entries)
    conn = ledger.connection()

    if entity in CONSOLIDATION_GROUPS:
        # Consolidado: solo las entidades del grupo (Story 11.1 — antes era
        # roots-only = todo el ledger, contaminable por libros ajenos).
        pattern = _group_pattern(_BALANCE_SHEET_ROOTS, entity)
    else:
        pattern = _entity_pattern(_BALANCE_SHEET_ROOTS, entity)
    where = f'account ~ "{pattern}"'
    if date_to:
        where += f" AND date <= {date_to}"
    bql = (
        f"SELECT account, sum(position) AS balance "
        f"WHERE {where} GROUP BY account ORDER BY account"
    )
    cursor = conn.execute(bql)

    query_date = date_to or _max_transaction_date(entries, _freshness_pattern(entity)) or ""
    data = []
    for account, balance in cursor.fetchall():
        amount = _clp(balance)
        m = meta.get(account, {})
        data.append({
            "account_id": None,
            "account_number": str(m.get("code", "")),
            # Path beancount completo (ej. "Assets:Jocelyn:Bancos:..."). El frontend agrupa por la
            # raíz contable (Assets/Liabilities/Equity) en vez del primer dígito del código — así las
            # cuentas de las hijas (consolidadas en EAG, códigos 6/7/8/9) caen en Activos/Pasivos y no
            # en "Otros". El path legacy de Sheets no trae este campo → el frontend cae al código.
            "account": account,
            "account_name": str(m.get("laudus_account_name", account)),
            "debit": 0.0,
            "credit": 0.0,
            "debit_balance": amount if amount >= 0 else 0.0,
            "credit_balance": -amount if amount < 0 else 0.0,
            "query_date": query_date,
            "is_latest": "TRUE",
        })
    return {"data": data, "meta": {"last_sync": query_date or None}}


def ledger_entries_via_beancount(
    ledger: LedgerService,
    entity: str,
    date_from: str | None = None,
    date_to: str | None = None,
    account_number: str | None = None,
) -> dict:
    """Ledger postings for `entity`, optionally filtered by date range/account.

    Returns records keyed by the Sheets column aliases the `LedgerEntryRecord`
    model expects (accountnumber, accountName, Categoria1..3, ...).

    Itera `ledger.entries()` directamente en vez de BQL (Story 7.1b AC1): el BQL entrega
    filas por posting sin acceso a la transacción padre, y cada fila necesita el `tx_id`
    de la TX (el ancla de owner-comments es por transacción, no por pata). Mismo patrón
    que `list_pending` en `transactions/service.py`. Una sola pasada (lección D7).
    """
    entries = ledger.entries()
    meta = _account_meta(entries)

    pattern = _compiled_entity_pattern("Assets|Liabilities|Equity|Income|Expenses", entity)
    try:
        d_from = date.fromisoformat(date_from) if date_from else None
        d_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as e:
        raise ValueError(f"Invalid date format: {e}")

    data = []
    last_sync: str | None = None
    for entry in entries:
        if not isinstance(entry, Transaction):
            continue
        if d_from is not None and entry.date < d_from:
            continue
        if d_to is not None and entry.date > d_to:
            break
        tx_id: str | None = None  # una sola vez por tx, compartido entre sus patas
        for posting in entry.postings:
            if not pattern.match(posting.account):
                continue
            m = meta.get(posting.account, {})
            code = str(m.get("code", ""))
            if account_number is not None and code != account_number:
                continue
            number = posting.units.number if posting.units else None
            currency = posting.units.currency if posting.units else None
            amount = float(number) if number is not None else 0.0
            iso_date = entry.date.isoformat()
            if last_sync is None or iso_date > last_sync:
                last_sync = iso_date
            if tx_id is None:
                tx_id = tx_id_of(entry)
            data.append({
                "journalentryid": None,
                "journalentrynumber": None,
                "date": iso_date,
                "accountnumber": code,
                "lineid": None,
                "description": entry.narration or "",
                "debit": amount if amount >= 0 else 0.0,
                "credit": -amount if amount < 0 else 0.0,
                "currencycode": currency or "CLP",
                "paritytomaincurrency": 1.0,
                "periodo": "",
                "accountName": str(m.get("laudus_account_name", posting.account)),
                "Categoria1": str(m.get("laudus_categoria1", "")),
                "Categoria2": str(m.get("laudus_categoria2", "")),
                "Categoria3": str(m.get("laudus_categoria3", "")),
                "tx_id": tx_id,
            })
    # `ORDER BY date DESC` del BQL saliente; sort estable → orden de archivo intra-día.
    data.sort(key=lambda r: r["date"], reverse=True)
    return {"data": data, "meta": {"last_sync": last_sync}}


def report_rows_via_beancount(
    ledger: LedgerService,
    date_from: str | None = None,
    date_to: str | None = None,
    group: str = "EAG",
) -> list[dict]:
    """Filas estilo `ledger_final` desde Beancount — TODO un grupo de consolidación.

    El reporte de gastos agrega por código de cuenta y categoría sobre todas las
    entidades de un grupo a la vez, así que a diferencia de
    `ledger_entries_via_beancount` no es per-entity: se acota al GRUPO completo
    (Story 11.1 — antes sin filtro de cuenta, es decir todo el ledger; los códigos
    de libros distintos colisionan con los prefijos del builder y contaminarían el
    reporte). `group` default `"EAG"` (reporte de gastos EAG, 0 regresión); la
    Story 13.1 pasa `group="FondoComun"` para el reporte FFCC/JAB. Cada posting del
    rango se mapea a una fila con las claves que `report_builder` consume desde
    `ledger_final` (date, accountnumber, accountName, Categoria1..3, debit, credit)
    MÁS `account` (path beancount completo) para que el builder RUT2 derive la
    entidad del 2º segmento del path (13.1 Task 1). El split debit/credit por signo
    del número es el mismo que el resto del módulo.
    """
    entries = ledger.entries()
    meta = _account_meta(entries)
    conn = ledger.connection()

    pattern = _group_pattern("Assets|Liabilities|Equity|Income|Expenses", group)
    conds = [f'account ~ "{pattern}"']
    if date_from:
        conds.append(f"date >= {date_from}")
    if date_to:
        conds.append(f"date <= {date_to}")
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    bql = f"SELECT date, account, number, currency{where} ORDER BY date"
    cursor = conn.execute(bql)

    rows = []
    for row_date, account, number, currency in cursor.fetchall():
        m = meta.get(account, {})
        amount = float(number) if number is not None else 0.0
        iso_date = row_date.isoformat() if isinstance(row_date, date) else str(row_date)
        rows.append({
            "date": iso_date,
            "account": account,
            "accountnumber": str(m.get("code", "")),
            "accountName": str(m.get("laudus_account_name", account)),
            "Categoria1": str(m.get("laudus_categoria1", "")),
            "Categoria2": str(m.get("laudus_categoria2", "")),
            "Categoria3": str(m.get("laudus_categoria3", "")),
            "debit": amount if amount >= 0 else 0.0,
            "credit": -amount if amount < 0 else 0.0,
        })
    return rows


# ── Story 13.1: cuentas corriente de socios del Fondo Común ──────────────────
# Cuentas por cobrar (categoria3) que son, contablemente, cuenta corriente /
# patrimonio de socios (veredicto Valentina 2026-07-12). Las OPERACIONALES son un
# set chico y estable de cuentas de sistema (existen en EAG/FFCC/JAB con el mismo
# nombre) — NO es una allowlist de personas, es la exclusión de las cuentas que no
# son de un familiar; todo lo demás en el universo CxC del grupo = familiar.
_RECEIVABLE_CAT3 = "CUENTAS POR COBRAR"
_OPERATIONAL_STEMS = frozenset({
    "CuentasCorrientesDelPersonal", "FondoFijo", "FondosPorRendir",
    "FondosPorRendirUs", "DeudoresVarios", "ControlYLiquidacin",
})


def distribution_rows_via_beancount(
    ledger: LedgerService,
    date_from: str | None = None,
    date_to: str | None = None,
    group: str = "FondoComun",
) -> list[dict]:
    """Estado de cuenta corriente por socio del Fondo Común (Story 13.1 AC3).

    Itera las transacciones una sola vez (NO `report_rows_via_beancount`) porque el
    neteo de asientos *wash* (+X/−X a la MISMA cuenta en un mismo asiento =
    reclasificación interna; 265 en el ledger @ 2026-06-30) exige agrupar por
    (asiento, cuenta): las filas por-pata ya split debit/credit inflarían retiros Y
    repartos con ese ruido. Por cuenta devuelve el NETO por asiento repartido en
    flujos del período (retiro si neto ≥ 0, reparto si neto < 0) + saldos
    cumulativos (inicial a `date_from-1`, cierre a `date_to`). Invariante:
    `saldo_inicial + retiros + repartos == saldo_cierre`.

    Universo = cuentas del grupo (case-sensitive, patch 11.1) con
    `laudus_categoria3 == "CUENTAS POR COBRAR"`. `operational` marca las cuentas de
    sistema (ver `_OPERATIONAL_STEMS`); el resto son familiares.
    """
    entries = ledger.entries()
    meta = _account_meta(entries)
    pattern = re.compile(_group_pattern("Assets", group))
    accts = {
        a for a, m in meta.items()
        if pattern.match(a) and str(m.get("laudus_categoria3", "")) == _RECEIVABLE_CAT3
    }
    try:
        d_from = date.fromisoformat(date_from) if date_from else None
        d_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as e:
        raise ValueError(f"Invalid date format: {e}")

    inicial: dict[str, float] = defaultdict(float)
    retiros: dict[str, float] = defaultdict(float)
    repartos: dict[str, float] = defaultdict(float)
    cierre: dict[str, float] = defaultdict(float)
    for entry in entries:
        if not isinstance(entry, Transaction):
            continue
        if d_to is not None and entry.date > d_to:
            continue
        net: dict[str, float] = defaultdict(float)
        for p in entry.postings:
            if p.account in accts and p.units is not None:
                net[p.account] += float(p.units.number)
        for acc, n in net.items():
            cierre[acc] += n
            if d_from is not None and entry.date < d_from:
                inicial[acc] += n
            elif n >= 0:
                retiros[acc] += n
            else:
                repartos[acc] += n

    rows = []
    for acc in accts:
        m = meta.get(acc, {})
        stem = acc.split(":")[-1].rsplit("-", 1)[0]
        rows.append({
            "account": acc,
            "entity": acc.split(":")[1],
            "code": str(m.get("code", "")),
            "name": str(m.get("laudus_account_name", acc)),
            "saldo_inicial": inicial.get(acc, 0.0),
            "retiros": retiros.get(acc, 0.0),
            "repartos": repartos.get(acc, 0.0),  # ≤ 0
            "saldo_cierre": cierre.get(acc, 0.0),
            "operational": stem in _OPERATIONAL_STEMS,
        })
    # Familiares por |saldo| desc; operativas al final (Valentina: separar bloques).
    # Desempate por `account` → orden determinista aunque `accts` sea un set.
    rows.sort(key=lambda x: (x["operational"], -abs(x["saldo_cierre"]), x["account"]))
    return rows

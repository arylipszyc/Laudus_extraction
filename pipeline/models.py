"""
models.py — Fuente única de verdad para esquemas y transformaciones de datos.

Centraliza los headers de cada hoja y las funciones que convierten la respuesta
cruda de la API de Laudus al formato interno del proyecto.
"""

import calendar as _calendar
from datetime import date as _date

# ──────────────────────────────────────────────
# Esquemas de columnas (orden = columnas en Google Sheets)
# ──────────────────────────────────────────────

BALANCE_HEADERS = [
    "account_id", "account_number", "account_name",
    "debit", "credit", "debit_balance", "credit_balance",
    "query_date", "is_latest"
]

LEDGER_HEADERS = [
    "journalentryid", "journalentrynumber", "date",
    "accountnumber", "lineid", "description",
    "debit", "credit", "currencycode",
    "paritytomaincurrency", "periodo"
]


# ──────────────────────────────────────────────
# Funciones de transformación (API → esquema interno)
# ──────────────────────────────────────────────

def map_balance_row(item, query_date, is_latest=False):
    """
    Convierte un registro crudo del endpoint balanceSheet/totals
    al diccionario interno alineado con BALANCE_HEADERS.

    Args:
        item (dict): Registro JSON de la API.
        query_date (date | str): Fecha del corte consultado.
        is_latest (bool): True si este query_date es el más reciente.
    """
    return {
        "account_id":     item["accountId"],
        "account_number": item["accountNumber"],
        "account_name":   item["accountName"],
        "debit":          item["debit"],
        "credit":         item["credit"],
        "debit_balance":  item["debitBalance"],
        "credit_balance": item["creditBalance"],
        "query_date":     str(query_date),
        "is_latest":      str(is_latest).upper(),
    }


def map_ledger_row(item, periodo):
    """
    Convierte un registro crudo del endpoint accounting/ledger
    al diccionario interno alineado con LEDGER_HEADERS.

    Args:
        item (dict): Registro JSON de la API.
        periodo (date | str): Fecha de cierre del período sincronizado.
    """
    return {
        "journalentryid":       item["journalEntryId"],
        "journalentrynumber":   item["journalEntryNumber"],
        "date":                 item["date"],
        "accountnumber":        item["accountNumber"],
        "lineid":               item["lineId"],
        "description":          item.get("description", ""),
        "debit":                item["debit"],
        "credit":               item["credit"],
        "currencycode":         item["currencyCode"],
        "paritytomaincurrency": item["parityToMainCurrency"],
        "periodo":              str(periodo),
    }


# ──────────────────────────────────────────────
# Esquemas de columnas para hojas enriquecidas (_final)
# ──────────────────────────────────────────────

BALANCE_FINAL_HEADERS = BALANCE_HEADERS + [
    "accountName", "Categoria3", "Categoria2", "Categoria1"
]

LEDGER_FINAL_HEADERS = [
    "journalentryid", "journalentrynumber", "date",
    "accountnumber", "lineid", "description",
    "debit", "credit",
    "accountName", "Categoria3", "Categoria2", "Categoria1", "fecha_cierre",
]


# ──────────────────────────────────────────────
# Enriquecimiento con PlanCuentas
# ──────────────────────────────────────────────

def build_plan_cuentas_lookup(records):
    """
    Construye un dict de búsqueda desde los registros de la hoja PlanCuentas.

    Clave: account_number (str).
    Valor: dict con accountName y las tres categorías jerárquicas.
    """
    lookup = {}
    for r in records:
        key = str(r.get("account_number", "")).strip()
        if key:
            lookup[key] = {
                "accountName": r.get("account_name", "Sin Categoría"),
                "Categoria3":  r.get("3\u00b0 Category", "Sin Categoría"),
                "Categoria2":  r.get("2\u00b0 Category", "Sin Categoría"),
                "Categoria1":  r.get("1\u00b0 Category", "Sin Categoría"),
            }
    return lookup


def _eomonth(date_str):
    """Retorna el último día del mes de una fecha como string 'YYYY-MM-DD'."""
    d = str(date_str).split(" ")[0]
    y, m, _ = map(int, d.split("-"))
    last = _calendar.monthrange(y, m)[1]
    return str(_date(y, m, last))


def enrich_balance_row(row, lookup):
    """
    Agrega columnas de jerarquía de cuenta a una fila de balance_sheet.
    Usa account_number como clave de búsqueda en el lookup de PlanCuentas.
    """
    key = str(row.get("account_number", "")).strip()
    cat = lookup.get(key, {})
    return {
        **row,
        "accountName": cat.get("accountName", "Sin Categoría"),
        "Categoria3":  cat.get("Categoria3",  "Sin Categoría"),
        "Categoria2":  cat.get("Categoria2",  "Sin Categoría"),
        "Categoria1":  cat.get("Categoria1",  "Sin Categoría"),
    }


def enrich_ledger_row(row, lookup):
    """
    Construye una fila para ledger_final: 8 columnas base del ledger
    + jerarquía de cuenta + fecha_cierre (último día del mes de la transacción).
    """
    key = str(row.get("accountnumber", "")).strip()
    cat = lookup.get(key, {})
    return {
        "journalentryid":     row["journalentryid"],
        "journalentrynumber": row["journalentrynumber"],
        "date":               row["date"],
        "accountnumber":      row["accountnumber"],
        "lineid":             row["lineid"],
        "description":        row.get("description", ""),
        "debit":              row["debit"],
        "credit":             row["credit"],
        "accountName":        cat.get("accountName", "Sin Categoría"),
        "Categoria3":         cat.get("Categoria3",  "Sin Categoría"),
        "Categoria2":         cat.get("Categoria2",  "Sin Categoría"),
        "Categoria1":         cat.get("Categoria1",  "Sin Categoría"),
        "fecha_cierre":       _eomonth(row["date"]),
    }

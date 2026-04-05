"""
backfill_data.py — Script de carga inicial (ejecutar UNA sola vez).

Carga en Google Sheets:
  - Balance Sheet: balance del último día de cada mes desde BALANCE_START hasta hoy.
  - Ledger: todos los registros desde LEDGER_DATE_FROM hasta hoy.
"""

import logging
import time
from datetime import datetime, date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("backfill.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

from config.laudus_config import get_endpoints, BALANCE_SHEET_URL
from config.gspread_config import get_spreadsheet
from services.balance_sheet_service import fetch_balance_sheet
from services.ledger_service import fetch_ledger
from utils.dates import get_end_of_month_dates
from utils.gspread_utils import upsert_to_sheet
from models import (
    BALANCE_HEADERS, LEDGER_HEADERS, map_balance_row, map_ledger_row,
    BALANCE_FINAL_HEADERS, LEDGER_FINAL_HEADERS,
    build_plan_cuentas_lookup, enrich_balance_row, enrich_ledger_row,
)


# ──────────────────────────────────────────────
# Constantes de configuración
# ──────────────────────────────────────────────
BALANCE_START_YEAR = 2021
BALANCE_START_MONTH = 1

LEDGER_DATE_FROM = date(2021, 1, 1)

API_DELAY_SECONDS = 2  # Pausa entre llamadas para no saturar la API


def backfill():
    logger.info("=" * 50)
    logger.info("BACKFILL — Carga inicial de datos")
    logger.info("=" * 50)

    # 1. Conectar a Google Sheets
    sh = get_spreadsheet()
    if not sh:
        logger.error("No se pudo conectar a Google Sheets.")
        return

    # 1b. Cargar lookup de PlanCuentas para enriquecimiento
    try:
        plan_lookup = build_plan_cuentas_lookup(sh.worksheet("PlanCuentas").get_all_records())
        logger.info("PlanCuentas cargado: %d cuentas.", len(plan_lookup))
    except Exception as e:
        plan_lookup = {}
        logger.warning("No se pudo cargar PlanCuentas: %s. Las hojas _final no se enriquecerán.", e)

    # ──────────────────────────────────────────
    # 2. BALANCE SHEET — último día de cada mes
    # ──────────────────────────────────────────
    today = datetime.now().date()
    month_ends = get_end_of_month_dates(
        BALANCE_START_YEAR, BALANCE_START_MONTH,
        today.year, today.month - 1 if today.month > 1 else 12
    )
    logger.info("Se consultarán %d meses de balance sheet.", len(month_ends))

    # La fecha más reciente es la última de la lista
    latest_query_date = str(month_ends[-1])

    all_balance_data = []

    for i, month_end in enumerate(month_ends):
        query_date_str = str(month_end)
        is_latest = (query_date_str == latest_query_date)
        logger.info("[%d/%d] Consultando balance para %s...", i + 1, len(month_ends), query_date_str)

        try:
            data = fetch_balance_sheet(BALANCE_SHEET_URL, {"dateTo": query_date_str})
            if data:
                for item in data:
                    all_balance_data.append(map_balance_row(item, query_date_str, is_latest))
                logger.info("  %d cuentas obtenidas.", len(data))
            else:
                logger.warning("  Sin datos para %s.", query_date_str)
        except Exception as e:
            logger.error("  Error al consultar %s: %s", query_date_str, e)

        # Pausa entre llamadas
        if i < len(month_ends) - 1:
            time.sleep(API_DELAY_SECONDS)

    # Subir balance sheet a Google Sheets
    if all_balance_data:
        logger.info("Subiendo %d filas de balance sheet...", len(all_balance_data))
        upsert_to_sheet(
            spreadsheet=sh,
            sheet_name="balance_sheet",
            data_list=all_balance_data,
            primary_key_func=lambda x: f"{x.get('account_id', '')}_{x.get('query_date', '')}",
            headers=BALANCE_HEADERS
        )
        logger.info("Balance sheet cargado exitosamente.")

        if plan_lookup:
            enriched_balance = [enrich_balance_row(r, plan_lookup) for r in all_balance_data]
            upsert_to_sheet(
                spreadsheet=sh,
                sheet_name="balance_sheet_final",
                data_list=enriched_balance,
                primary_key_func=lambda x: f"{x.get('account_id', '')}_{x.get('query_date', '')}",
                headers=BALANCE_FINAL_HEADERS,
            )
            logger.info("balance_sheet_final cargado exitosamente.")
    else:
        logger.warning("No se obtuvieron datos de balance sheet.")

    # ──────────────────────────────────────────
    # 3. LEDGER — desde LEDGER_DATE_FROM hasta hoy
    # ──────────────────────────────────────────
    date_to = datetime.now().date()
    logger.info("Consultando ledger desde %s hasta %s...", LEDGER_DATE_FROM, date_to)

    endpoints = get_endpoints(LEDGER_DATE_FROM, date_to)
    ledger_cfg = endpoints["GET_LEDGER"]

    # Usar el número de cuenta mínimo como filtro para garantizar cobertura completa
    account_numbers = [
        str(r["account_number"])
        for r in all_balance_data
        if r.get("account_number") not in (None, "")
    ]
    if account_numbers:
        ledger_cfg["params"]["accountNumberFrom"] = min(account_numbers)
        logger.info("accountNumberFrom fijado en: %s", ledger_cfg["params"]["accountNumberFrom"])

    try:
        ledger_data = fetch_ledger(ledger_cfg["url"], ledger_cfg["params"])
        if ledger_data:
            mapped = [map_ledger_row(item, date_to) for item in ledger_data]
            logger.info("%d registros de ledger obtenidos.", len(mapped))

            upsert_to_sheet(
                spreadsheet=sh,
                sheet_name="ledger",
                data_list=mapped,
                primary_key_func=lambda x: f"{x.get('journalentryid', '')}_{x.get('lineid', '')}",
                headers=LEDGER_HEADERS
            )
            logger.info("Ledger cargado exitosamente.")

            if plan_lookup:
                enriched_ledger = [enrich_ledger_row(r, plan_lookup) for r in mapped]
                upsert_to_sheet(
                    spreadsheet=sh,
                    sheet_name="ledger_final",
                    data_list=enriched_ledger,
                    primary_key_func=lambda x: f"{x.get('journalentryid', '')}_{x.get('lineid', '')}",
                    headers=LEDGER_FINAL_HEADERS,
                )
                logger.info("ledger_final cargado exitosamente.")
        else:
            logger.warning("No se obtuvieron datos de ledger.")
    except Exception as e:
        logger.error("Error al obtener ledger: %s", e, exc_info=True)

    # ──────────────────────────────────────────
    # 4. Registrar fecha sincronizada
    # ──────────────────────────────────────────
    upsert_to_sheet(
        spreadsheet=sh,
        sheet_name="date_range",
        data_list=[{"dateTo": str(date_to), "dateFrom": str(LEDGER_DATE_FROM)}],
        primary_key_func=lambda x: str(x.get("dateTo", "")),
        headers=["dateTo", "dateFrom"]
    )

    logger.info("=" * 50)
    logger.info("BACKFILL COMPLETADO")
    logger.info("=" * 50)


if __name__ == "__main__":
    backfill()

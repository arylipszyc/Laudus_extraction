"""
sync.py — Sincronización recurrente de datos contables desde Laudus API a Google Sheets.

Balance Sheet: trae el balance del último día del mes anterior (si no existe ya en GSheets).
Ledger: trae registros incrementales desde la última fecha sincronizada hasta hoy.
"""

import logging
from datetime import datetime

from utils.dates import get_date_range, get_last_day_of_previous_month
from config.laudus_config import get_endpoints, BALANCE_SHEET_URL
from services.ledger_service import fetch_ledger
from services.balance_sheet_service import fetch_balance_sheet
from config.gspread_config import get_spreadsheet
from utils.gspread_utils import upsert_to_sheet, _cell_value
from models import (
    BALANCE_HEADERS, LEDGER_HEADERS, map_balance_row, map_ledger_row,
    BALANCE_FINAL_HEADERS, LEDGER_FINAL_HEADERS,
    build_plan_cuentas_lookup, enrich_balance_row, enrich_ledger_row,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sync.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def recalculate_is_latest(spreadsheet):
    """
    Recalcula la columna is_latest en la pestaña balance_sheet.
    Marca con TRUE solo las filas cuyo query_date es el máximo.
    """
    try:
        ws = spreadsheet.worksheet("balance_sheet")
    except Exception:
        return  # La pestaña no existe aún

    records = ws.get_all_records()
    if not records:
        return

    # Encontrar el query_date más reciente
    all_dates = [str(r.get("query_date", "")) for r in records if r.get("query_date")]
    if not all_dates:
        return
    max_date = max(all_dates)

    # Reconstruir todas las filas con is_latest recalculado
    updated_rows = [BALANCE_HEADERS]
    for row in records:
        if not any(row.values()):
            continue
        row["is_latest"] = "TRUE" if str(row.get("query_date", "")) == max_date else "FALSE"
        updated_rows.append([_cell_value(row.get(h, "")) for h in BALANCE_HEADERS])

    # Sobreescribir toda la pestaña
    ws.clear()
    ws.update(values=updated_rows, range_name="A1", value_input_option="USER_ENTERED")
    logger.info("is_latest recalculado: %s marcado como balance más reciente.", max_date)


def sync_api():
    """
    Función principal de sincronización recurrente.
    """
    try:
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

        # ──────────────────────────────────────
        # 2. BALANCE SHEET — último día del mes anterior
        # ──────────────────────────────────────
        last_day_prev = get_last_day_of_previous_month()
        target_date_str = str(last_day_prev)
        logger.info("Balance sheet objetivo: %s", target_date_str)

        # Verificar si ya existe en Google Sheets
        balance_already_loaded = False
        try:
            ws_balance = sh.worksheet("balance_sheet")
            existing_records = ws_balance.get_all_records()
            existing_dates = set(
                str(r.get("query_date", "")) for r in existing_records if r.get("query_date")
            )
            balance_already_loaded = target_date_str in existing_dates
        except Exception:
            pass  # La pestaña no existe, se creará al insertar

        if balance_already_loaded:
            logger.info("Balance de %s ya existe en Google Sheets. Saltando.", target_date_str)
        else:
            logger.info("Consultando balance para %s...", target_date_str)
            balance_data = fetch_balance_sheet(BALANCE_SHEET_URL, {"dateTo": target_date_str})

            if balance_data:
                mapped_balance = [map_balance_row(item, target_date_str) for item in balance_data]
                logger.info("%d cuentas obtenidas.", len(mapped_balance))

                upsert_to_sheet(
                    spreadsheet=sh,
                    sheet_name="balance_sheet",
                    data_list=mapped_balance,
                    primary_key_func=lambda x: f"{x.get('account_id', '')}_{x.get('query_date', '')}",
                    headers=BALANCE_HEADERS
                )
            else:
                logger.warning("Sin datos de balance para %s.", target_date_str)

        # Recalcular is_latest siempre (incluso si no se insertó nada nuevo)
        recalculate_is_latest(sh)

        # Rebuild balance_sheet_final con enriquecimiento desde PlanCuentas
        if plan_lookup:
            all_balance = sh.worksheet("balance_sheet").get_all_records()
            enriched_balance = [enrich_balance_row(r, plan_lookup) for r in all_balance]
            upsert_to_sheet(
                spreadsheet=sh,
                sheet_name="balance_sheet_final",
                data_list=enriched_balance,
                primary_key_func=lambda x: f"{x.get('account_id', '')}_{x.get('query_date', '')}",
                headers=BALANCE_FINAL_HEADERS,
            )

        # ──────────────────────────────────────
        # 3. LEDGER — incremental desde última fecha sincronizada
        # ──────────────────────────────────────
        try:
            ws_date = sh.worksheet("date_range")
            records = ws_date.get_all_records()
            if records:
                dates = [str(r.get("dateTo", "")) for r in records if r.get("dateTo")]
                latest_date_to = max(dates) if dates else "2023-01-01"
            else:
                latest_date_to = "2023-01-01"
        except Exception:
            latest_date_to = "2023-01-01"
            logger.warning("No se encontró pestaña date_range. Usando fecha por defecto.")

        logger.info("Ledger — Última fecha sincronizada: %s", latest_date_to)
        date_from, date_to = get_date_range(latest_date_to)

        if date_from > date_to:
            logger.info("No hay nuevas fechas de ledger para sincronizar.")
        else:
            logger.info("Consultando ledger desde %s hasta %s...", date_from, date_to)
            endpoints = get_endpoints(date_from, date_to)
            ledger_cfg = endpoints["GET_LEDGER"]

            # Número de cuenta mínimo como filtro
            try:
                ws_bal = sh.worksheet("balance_sheet")
                bal_records = ws_bal.get_all_records()
                account_numbers = [
                    str(r["account_number"])
                    for r in bal_records
                    if r.get("account_number") not in (None, "")
                ]
                if account_numbers:
                    ledger_cfg["params"]["accountNumberFrom"] = min(account_numbers)
                    logger.info("accountNumberFrom fijado en: %s", ledger_cfg["params"]["accountNumberFrom"])
            except Exception:
                logger.warning("No se pudo leer el balance para determinar accountNumberFrom. Se omite el filtro.")

            ledger_data = fetch_ledger(ledger_cfg["url"], ledger_cfg["params"])

            if ledger_data:
                mapped_ledger = [map_ledger_row(item, date_to) for item in ledger_data]
                logger.info("%d registros de ledger obtenidos.", len(mapped_ledger))

                upsert_to_sheet(
                    spreadsheet=sh,
                    sheet_name="ledger",
                    data_list=mapped_ledger,
                    primary_key_func=lambda x: f"{x.get('journalentryid', '')}_{x.get('lineid', '')}",
                    headers=LEDGER_HEADERS
                )
            else:
                logger.warning("Sin datos nuevos de ledger.")

            # ──────────────────────────────────────
            # 4. Actualizar fecha sincronizada
            # ──────────────────────────────────────
            upsert_to_sheet(
                spreadsheet=sh,
                sheet_name="date_range",
                data_list=[{"dateTo": str(date_to), "dateFrom": str(date_from)}],
                primary_key_func=lambda x: str(x.get("dateTo", "")),
                headers=["dateTo", "dateFrom"]
            )

        # ──────────────────────────────────────
        # 5. Rebuild hojas _final (siempre, con datos actuales)
        # ──────────────────────────────────────
        if plan_lookup:
            all_ledger = sh.worksheet("ledger").get_all_records()
            enriched_ledger = [enrich_ledger_row(r, plan_lookup) for r in all_ledger]
            upsert_to_sheet(
                spreadsheet=sh,
                sheet_name="ledger_final",
                data_list=enriched_ledger,
                primary_key_func=lambda x: f"{x.get('journalentryid', '')}_{x.get('lineid', '')}",
                headers=LEDGER_FINAL_HEADERS,
            )

        logger.info("Sincronización completada.")

    except Exception as e:
        logger.error("Error inesperado: %s", e, exc_info=True)


if __name__ == '__main__':
    sync_api()

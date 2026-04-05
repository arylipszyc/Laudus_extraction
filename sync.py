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
from utils.gspread_utils import upsert_to_sheet, replace_sheet, safe_write, _cell_value
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


def recalculate_is_latest(spreadsheet, records):
    """
    Recalcula la columna is_latest en balance_sheet usando datos ya cargados en memoria.
    Evita releer la pestaña. Protege contra pérdida de datos con restore-on-failure.
    Muta is_latest en los dicts de records (útil para enrichment posterior).
    """
    if not records:
        return

    try:
        ws = spreadsheet.worksheet("balance_sheet")
    except Exception:
        return

    all_dates = [str(r.get("query_date", "")) for r in records if r.get("query_date")]
    if not all_dates:
        return
    max_date = max(all_dates)

    # Backup construido desde records antes de mutar is_latest
    backup_rows = [BALANCE_HEADERS] + [
        [_cell_value(r.get(h, "")) for h in BALANCE_HEADERS]
        for r in records if any(r.values())
    ]

    # Recalcular is_latest en memoria y construir filas actualizadas
    updated_rows = [BALANCE_HEADERS]
    for row in records:
        if not any(row.values()):
            continue
        row["is_latest"] = "TRUE" if str(row.get("query_date", "")) == max_date else "FALSE"
        updated_rows.append([_cell_value(row.get(h, "")) for h in BALANCE_HEADERS])

    safe_write(ws, updated_rows, backup_rows, "balance_sheet")
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

        # Leer balance_sheet una sola vez — se reutiliza para verificación,
        # accountNumberFrom y enriquecimiento _final
        existing_records = []
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

        # merged_balance es el estado actual del balance en memoria
        # Si no hay datos nuevos, equivale a existing_records
        merged_balance = existing_records

        if balance_already_loaded:
            logger.info("Balance de %s ya existe en Google Sheets. Saltando.", target_date_str)
        else:
            logger.info("Consultando balance para %s...", target_date_str)
            balance_data = fetch_balance_sheet(BALANCE_SHEET_URL, {"dateTo": target_date_str})

            if balance_data:
                mapped_balance = [map_balance_row(item, target_date_str) for item in balance_data]
                logger.info("%d cuentas obtenidas.", len(mapped_balance))

                # upsert retorna el merged completo — evita releer el sheet más adelante
                merged_balance = upsert_to_sheet(
                    spreadsheet=sh,
                    sheet_name="balance_sheet",
                    data_list=mapped_balance,
                    primary_key_func=lambda x: f"{x.get('account_id', '')}_{x.get('query_date', '')}",
                    headers=BALANCE_HEADERS,
                )
            else:
                logger.warning("Sin datos de balance para %s.", target_date_str)

        # Recalcular is_latest usando datos en memoria (sin releer el sheet)
        recalculate_is_latest(sh, merged_balance)

        # Rebuild balance_sheet_final con datos ya en memoria (sin releer balance_sheet)
        if plan_lookup and merged_balance:
            enriched_balance = [enrich_balance_row(r, plan_lookup) for r in merged_balance]
            replace_sheet(sh, "balance_sheet_final", enriched_balance, BALANCE_FINAL_HEADERS)

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

        merged_ledger = None

        if date_from > date_to:
            logger.info("No hay nuevas fechas de ledger para sincronizar.")
        else:
            logger.info("Consultando ledger desde %s hasta %s...", date_from, date_to)
            endpoints = get_endpoints(date_from, date_to)
            ledger_cfg = endpoints["GET_LEDGER"]

            # Usar merged_balance ya cargado para obtener accountNumberFrom (sin releer el sheet)
            account_numbers = [
                str(r["account_number"])
                for r in merged_balance
                if r.get("account_number") not in (None, "")
            ]
            if account_numbers:
                ledger_cfg["params"]["accountNumberFrom"] = min(account_numbers)
                logger.info("accountNumberFrom fijado en: %s", ledger_cfg["params"]["accountNumberFrom"])

            ledger_data = fetch_ledger(ledger_cfg["url"], ledger_cfg["params"])

            if ledger_data:
                mapped_ledger = [map_ledger_row(item, date_to) for item in ledger_data]
                logger.info("%d registros de ledger obtenidos.", len(mapped_ledger))

                # upsert retorna el merged completo — evita releer el sheet para _final
                merged_ledger = upsert_to_sheet(
                    spreadsheet=sh,
                    sheet_name="ledger",
                    data_list=mapped_ledger,
                    primary_key_func=lambda x: f"{x.get('journalentryid', '')}_{x.get('lineid', '')}",
                    headers=LEDGER_HEADERS,
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
                headers=["dateTo", "dateFrom"],
            )

        # ──────────────────────────────────────
        # 5. Rebuild ledger_final
        # ──────────────────────────────────────
        if plan_lookup:
            # Si tenemos datos en memoria, usarlos directamente.
            # Si no hubo datos nuevos, leer el sheet (puede haber cambiado PlanCuentas).
            if merged_ledger is not None:
                ledger_for_final = merged_ledger
            else:
                try:
                    ledger_for_final = sh.worksheet("ledger").get_all_records()
                except Exception:
                    ledger_for_final = []

            if ledger_for_final:
                enriched_ledger = [enrich_ledger_row(r, plan_lookup) for r in ledger_for_final]
                replace_sheet(sh, "ledger_final", enriched_ledger, LEDGER_FINAL_HEADERS)

        logger.info("Sincronización completada.")

    except Exception as e:
        logger.error("Error inesperado: %s", e, exc_info=True)


if __name__ == '__main__':
    sync_api()

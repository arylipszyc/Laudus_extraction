import os
from datetime import datetime, date
import calendar
from dateutil.relativedelta import relativedelta

DEFAULT_OVERLAP_WINDOW_MONTHS = 13


def _overlap_window_months():
    """Tamaño (en meses) de la ventana solapada hacia atrás. Configurable por env."""
    raw = os.getenv("SYNC_OVERLAP_WINDOW_MONTHS", str(DEFAULT_OVERLAP_WINDOW_MONTHS))
    try:
        months = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_OVERLAP_WINDOW_MONTHS
    return months if months >= 0 else DEFAULT_OVERLAP_WINDOW_MONTHS


def get_date_range(date_str, today=None, overlap_months=None):
    """
    Rango de fechas a sincronizar para el ledger.

    Combina dos criterios:
    - Watermark forward-only: el día después de la última fecha sincronizada (`date_str`).
    - Ventana solapada hacia atrás: re-pedir los últimos `overlap_months` (≈ año fiscal
      en curso + margen para backdating de cierre del año anterior) para recuperar asientos
      posteados-tarde / con fecha contable retroactiva.

    La ventana solo mueve `date_from` hacia ATRÁS, nunca hacia adelante:
    `date_from = min(watermark+1, inicio_de_ventana)`. Así, si el watermark va atrasado
    respecto a la ventana, no se pierde el histórico ya pedido; si va adelantado (caso
    normal), se retrocede al inicio de ventana para recuperar lo backdateado.

    `today` y `overlap_months` son parámetros para testeo determinista; en producción se
    derivan de `datetime.now()` y `SYNC_OVERLAP_WINDOW_MONTHS`.
    """
    if today is None:
        today = datetime.now().date()
    if overlap_months is None:
        overlap_months = _overlap_window_months()

    last_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    watermark_from = last_date + relativedelta(days=1)
    window_start = today - relativedelta(months=overlap_months)

    date_from = min(watermark_from, window_start)
    date_to = today

    return date_from, date_to


def get_end_of_month_dates(start_year, start_month, end_year, end_month):
    """
    Returns a list of date objects representing the last day of each month
    in the range [start_year/start_month, end_year/end_month].
    """
    dates = []
    current = date(start_year, start_month, 1)
    end = date(end_year, end_month, 1)
    
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        dates.append(date(current.year, current.month, last_day))
        current += relativedelta(months=1)
    
    return dates


def get_last_day_of_previous_month():
    """
    Returns the last day of the month before today as a date object.
    """
    today = datetime.now().date()
    first_of_this_month = today.replace(day=1)
    return first_of_this_month - relativedelta(days=1)

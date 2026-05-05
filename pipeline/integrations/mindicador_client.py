"""Cliente HTTP para mindicador.cl — dólar observado por fecha.

mindicador.cl es un proxy público y gratuito de las series del Banco Central de
Chile. Decisión 2026-05-05 (Ary): preferir mindicador.cl sobre la API oficial
BCCh para evitar registro/credenciales. La diferencia entre el rate publicado
por mindicador y el publicado por BCCh es 0 (mindicador toma el dato
directamente de BCCh).

Uso:
    from datetime import date
    rate = fetch_dolar_observado(date(2026, 4, 30))
    # 950.45  o  None si no hubo publicación ese día
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://mindicador.cl/api/dolar"
_TIMEOUT = 15
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 5


class MindicadorError(RuntimeError):
    """Falla de red, timeout, o schema inesperado tras agotar retries."""


def fetch_dolar_observado(target_date: date) -> Optional[float]:
    """Consulta el dólar observado para `target_date`.

    Returns:
        El rate CLP/USD si mindicador publicó valor para ese día,
        None si la fecha no tiene publicación (sábado/domingo/feriado).

    Raises:
        MindicadorError: si tras 3 retries la API no responde o devuelve
            un schema inesperado.
    """
    url = f"{_BASE_URL}/{target_date.strftime('%d-%m-%Y')}"

    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            return _extract_rate(payload, target_date)
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE_SECONDS * attempt
                logger.warning(
                    "mindicador attempt %d/%d failed for %s: %s — retrying in %ds",
                    attempt, _MAX_RETRIES, target_date.isoformat(), exc, wait,
                )
                time.sleep(wait)

    raise MindicadorError(
        f"mindicador.cl falló tras {_MAX_RETRIES} intentos para {target_date.isoformat()}: {last_exc}"
    )


def _extract_rate(payload: dict, target_date: date) -> Optional[float]:
    """Parsea el payload de mindicador y extrae el rate.

    Shape esperado cuando hay publicación:
        {"version": "...", "serie": [{"fecha": "YYYY-MM-DDT00:00:00.000Z", "valor": 950.45}, ...]}

    Shape cuando no hay publicación:
        {"version": "...", "serie": []}

    mindicador a veces devuelve la serie completa de meses si el día no existe;
    filtramos por fecha exacta para evitar pickear un valor de otro día.
    """
    if not isinstance(payload, dict):
        raise MindicadorError(f"payload no es dict: {type(payload).__name__}")

    serie = payload.get("serie")
    if not isinstance(serie, list):
        raise MindicadorError("payload['serie'] missing or not a list")

    target_iso = target_date.isoformat()
    for entry in serie:
        fecha = entry.get("fecha", "")
        if fecha.startswith(target_iso):
            valor = entry.get("valor")
            if not isinstance(valor, (int, float)):
                raise MindicadorError(f"valor no numérico para {target_iso}: {valor!r}")
            return float(valor)

    return None

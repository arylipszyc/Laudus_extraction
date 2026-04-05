import logging
import requests
from config.laudus_config import LOGIN_URL, default_headers, payload

logger = logging.getLogger(__name__)

_token = None

# Claves que indican que la API está paginando resultados
_PAGINATION_KEYS = {"total", "count", "nextPage", "hasMore", "page", "totalPages", "pageSize", "offset"}
# Claves bajo las que las APIs suelen envolver el array de datos
_DATA_WRAPPER_KEYS = ("data", "items", "records", "results")


def login():
    """
    Autentica con la API de Laudus y obtiene un Bearer token.
    El token queda en caché para las peticiones siguientes.
    """
    global _token
    if _token is None:
        try:
            response = requests.post(LOGIN_URL, json=payload, headers=default_headers)
            response.raise_for_status()
            _token = response.json()["token"]
        except Exception as e:
            logger.error("Error al iniciar sesión: %s", e)
    return _token


def _unwrap_response(data, url):
    """
    Normaliza la respuesta de la API a una lista de registros.

    - Si la respuesta ya es una lista: se retorna sin cambios (caso nominal de Laudus).
    - Si es un dict: se detectan indicadores de paginación y se intenta extraer
      el array de datos de claves wrapper comunes (data, items, records, results).

    Si se detecta paginación, se registra un WARNING porque el sistema actual
    no implementa iteración de páginas: podrían faltar registros si la API
    limita el tamaño de respuesta. Revisar la documentación de Laudus para
    confirmar y, si corresponde, implementar el loop de paginación aquí.
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        detected = _PAGINATION_KEYS & set(data.keys())
        if detected:
            logger.warning(
                "Respuesta paginada detectada en %s (claves: %s). "
                "Si el total supera el límite de la API, pueden faltar registros. "
                "Revisar documentación de Laudus e implementar loop de paginación.",
                url, detected,
            )
        for key in _DATA_WRAPPER_KEYS:
            if key in data and isinstance(data[key], list):
                logger.debug("Datos extraídos de la clave wrapper '%s'.", key)
                return data[key]

    # Respuesta inesperada: se retorna tal cual para no perder datos
    logger.warning("Formato de respuesta no reconocido en %s. Se retorna sin transformar.", url)
    return data


def get_info_API(url, params=None, retry=True):
    """
    Realiza un GET al endpoint indicado usando el token en caché.
    Si recibe 401, limpia el token y reintenta una vez.
    Normaliza la respuesta a lista mediante _unwrap_response().
    """
    global _token
    token = login()
    headers = {**default_headers, "Authorization": f"Bearer {token}"}
    response = None
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return _unwrap_response(response.json(), url)
    except Exception as e:
        if response is not None and response.status_code == 401:
            _token = None
        if retry:
            return get_info_API(url, params, retry=False)
        logger.error("Error al obtener datos de %s: %s", url, e)
        return None
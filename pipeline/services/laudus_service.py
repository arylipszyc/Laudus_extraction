import logging
import requests
from pipeline.config.laudus_config import LOGIN_URL, default_headers, payload

logger = logging.getLogger(__name__)

_token = None
_REQUEST_TIMEOUT = 30  # segundos — evita cuelgues si Laudus no responde

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
            response = requests.post(
                LOGIN_URL, json=payload, headers=default_headers, timeout=_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            _token = response.json()["token"]
        except Exception as e:
            logger.error("Error al iniciar sesión: %s", e)
    return _token


def _extract_page(data, url):
    """
    Extrae la lista de registros de una respuesta y detecta si hay página siguiente.
    Retorna (records, next_page_params | None).
    """
    if isinstance(data, list):
        return data, None

    if isinstance(data, dict):
        # Extraer el array de datos desde claves wrapper comunes
        records = None
        for key in _DATA_WRAPPER_KEYS:
            if key in data and isinstance(data[key], list):
                records = data[key]
                break

        if records is None:
            logger.warning("Formato de respuesta no reconocido en %s. Se retorna sin transformar.", url)
            return data, None

        # Detectar parámetros de página siguiente
        next_params = None
        if data.get("nextPage"):
            next_params = {"page": data["nextPage"]}
        elif "page" in data and "totalPages" in data:
            cur = int(data["page"])
            total = int(data["totalPages"])
            if cur < total:
                next_params = {"page": cur + 1}
        elif data.get("hasMore"):
            cur = int(data.get("page", data.get("offset", 1)))
            next_params = {"page": cur + 1}

        if next_params:
            logger.info("Paginación detectada en %s — descargando página %s...", url, next_params["page"])

        return records, next_params

    logger.warning("Formato de respuesta no reconocido en %s. Se retorna sin transformar.", url)
    return data, None


def get_info_API(url, params=None, retry=True):
    """
    Realiza GET al endpoint indicado con token en caché, timeout de 30s y soporte de paginación.
    Si recibe 401, limpia el token y reintenta una vez.
    Acumula todas las páginas y retorna la lista completa de registros.
    """
    global _token
    token = login()
    if not token:
        logger.error("No hay token disponible. Abortando request a %s.", url)
        return None

    headers = {**default_headers, "Authorization": f"Bearer {token}"}
    current_params = dict(params) if params else {}
    all_records = []
    pages_fetched = 0

    while True:
        response = None
        try:
            response = requests.get(
                url, headers=headers, params=current_params, timeout=_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            records, next_page_params = _extract_page(response.json(), url)

            if isinstance(records, list):
                all_records.extend(records)
            else:
                return records  # Formato inesperado, retornar tal cual

            pages_fetched += 1
            if next_page_params is None:
                break  # No hay más páginas

            current_params.update(next_page_params)

        except Exception as e:
            if response is not None and response.status_code == 401:
                _token = None
                if retry:
                    logger.warning("Token expirado — reintentando con nuevo login...")
                    return get_info_API(url, params, retry=False)
            elif retry:
                logger.warning("Error en request a %s, reintentando: %s", url, e)
                return get_info_API(url, params, retry=False)
            logger.error("Error al obtener datos de %s: %s", url, e)
            return all_records if all_records else None

    if pages_fetched > 1:
        logger.info(
            "Total descargado de %s: %d registros en %d páginas.", url, len(all_records), pages_fetched
        )

    return all_records

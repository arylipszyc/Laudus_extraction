import logging
import requests
from pipeline.config.laudus_config import (
    ACCOUNTS_LIST_URL,
    BookConfig,
    LOGIN_URL,
    default_headers,
    get_book,
    login_payload,
)

logger = logging.getLogger(__name__)

# Token POR LIBRO (Story 12.2): antes era un `_token` global de módulo → estructuralmente
# mono-libro por proceso. Clave = book_id.
_tokens: dict[str, str] = {}
_REQUEST_TIMEOUT = 30  # segundos — evita cuelgues si Laudus no responde
# Tope duro de paginación: una API que repite página (o miente hasMore) no puede
# convertirse en un loop infinito sosteniendo el .import.lock (review 2026-07-06 B8).
_MAX_PAGES = 500


class PaginationError(RuntimeError):
    """La paginación no avanza o superó _MAX_PAGES — abortar la corrida, no reintentar."""

# Claves que indican que la API está paginando resultados
_PAGINATION_KEYS = {"total", "count", "nextPage", "hasMore", "page", "totalPages", "pageSize", "offset"}
# Claves bajo las que las APIs suelen envolver el array de datos
_DATA_WRAPPER_KEYS = ("data", "items", "records", "results")


class BookIdentityError(RuntimeError):
    """La empresa que devuelve la API NO es la esperada para el libro — abortar sin escribir (FR52)."""


def login(book: BookConfig | None = None):
    """
    Autentica con la API de Laudus y obtiene un Bearer token PARA EL LIBRO dado.
    El token queda en caché por libro para las peticiones siguientes.
    `book=None` = libro EAG (compatibilidad con callers legacy: bootstrap, path Sheets).

    Un fallo PROPAGA (review 2026-07-06 B8): antes se tragaba la excepción y el caller
    reportaba el genérico "No hay token" en vez de la causa real (credenciales, red, 5xx).
    """
    cfg = book or get_book("EAG")
    if cfg.book_id not in _tokens:
        response = requests.post(
            LOGIN_URL, json=login_payload(cfg), headers=default_headers,
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        token = response.json().get("token")
        if not token:  # 200 sin token = fallo de auth con otra forma; mejor que un KeyError pelado
            raise RuntimeError(f"Login Laudus devolvió 200 sin token (keys: {list(response.json())})")
        _tokens[cfg.book_id] = token
    return _tokens[cfg.book_id]


def verify_book_identity(book: BookConfig) -> None:
    """Assert de identidad de empresa (FR52) — corre ANTES del primer write de una corrida.

    Laudus NO falla ante un companyVATId equivocado (sonda intake §4): devuelve el libro
    que sea. El login tampoco trae nombre de empresa, así que la vía robusta es el
    fingerprint del plan de cuentas: `POST /accounting/accounts/list` y assert de que la
    cuenta raíz "1" se llama como el libro espera ("ACTIVO EAG" / "ACTIVO FFCC", ambos
    verificados en datos reales). NO valida dígito verificador del RUT (el placeholder
    de RUT2 tiene DV inválido por diseño).
    """
    token = login(book)
    headers = {**default_headers, "Authorization": f"Bearer {token}"}
    response = requests.post(
        ACCOUNTS_LIST_URL, headers=headers,
        json={"fields": ["accountNumber", "name"]}, timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    accounts = response.json()
    if not isinstance(accounts, list):
        raise BookIdentityError(
            f"No pude verificar la identidad del libro {book.book_id}: accounts/list "
            f"devolvió {type(accounts).__name__} en vez de lista — se aborta sin escribir (FR52)"
        )
    root = next(
        (a for a in accounts if str(a.get("accountNumber", "")).strip() == "1"), None)
    name = str((root or {}).get("name", "")).strip()
    if name != book.expected_root_name:
        raise BookIdentityError(
            f"Identidad de empresa NO coincide para el libro {book.book_id}: la cuenta raíz 1 "
            f"se llama {name!r}, esperaba {book.expected_root_name!r} "
            f"(¿companyVATId apunta a otro libro?) — se aborta sin escribir (FR52)"
        )


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


def get_info_API(url, params=None, retry=True, book: BookConfig | None = None):
    """
    Realiza GET al endpoint indicado con token en caché POR LIBRO, timeout de 30s y
    soporte de paginación. Si recibe 401, limpia el token del libro y reintenta una vez.
    Acumula todas las páginas y retorna la lista completa de registros.
    `book=None` = libro EAG (compatibilidad con callers legacy).
    """
    cfg = book or get_book("EAG")
    token = login(cfg)
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
            elif all_records:
                # Formato inesperado en una página >1: devolverlo descartaría lo acumulado
                # (misma clase de bug parcial-como-éxito). Que lo maneje el except de abajo.
                raise ValueError(f"Formato inesperado en página {pages_fetched + 1} de {url}")
            else:
                return records  # Formato inesperado en la primera página, retornar tal cual

            pages_fetched += 1
            if next_page_params is None:
                break  # No hay más páginas
            if pages_fetched >= _MAX_PAGES:
                raise PaginationError(
                    f"Paginación de {url} superó {_MAX_PAGES} páginas — abortando")
            # str() en ambos lados: una API que alterna '2' (str) y 2 (int) no debe
            # burlar el guard por tipo (review batch 3).
            if str(next_page_params.get("page")) == str(current_params.get("page")):
                raise PaginationError(
                    f"Paginación de {url} no avanza (página {next_page_params.get('page')} "
                    f"repetida) — abortando")

            current_params.update(next_page_params)

        except PaginationError:
            raise  # no reintentar: la API está rota, un retry repetiría el loop entero
        except Exception as e:
            if response is not None and response.status_code == 401:
                _tokens.pop(cfg.book_id, None)
                if retry:
                    logger.warning("Token expirado — reintentando con nuevo login...")
                    return get_info_API(url, params, retry=False, book=cfg)
            elif retry:
                logger.warning("Error en request a %s, reintentando: %s", url, e)
                return get_info_API(url, params, retry=False, book=cfg)
            logger.error("Error al obtener datos de %s: %s", url, e)
            # Fallo a mitad de paginación: NUNCA devolver la acumulación parcial como
            # éxito — un backfill con replace=True regeneraría los month files solo con
            # estas filas y borraría en silencio el resto del mes. Mejor que la corrida
            # entera falle (run_import la marca failed) y se reintente completa.
            if all_records:
                raise RuntimeError(
                    f"Descarga parcial de {url}: fallo en la página {pages_fetched + 1} "
                    f"con {len(all_records)} registros acumulados — se descarta el parcial"
                ) from e
            return None

    if pages_fetched > 1:
        logger.info(
            "Total descargado de %s: %d registros en %d páginas.", url, len(all_records), pages_fetched
        )

    return all_records

import os
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

import dotenv

dotenv.load_dotenv()

# ──────────────────────────────────────────────
# URLs base de la API
# ──────────────────────────────────────────────
LOGIN_URL          = "https://api.laudus.cl/security/login"
BALANCE_SHEET_URL  = "https://api.laudus.cl/accounting/balanceSheet/totals"
LEDGER_URL         = "https://api.laudus.cl/accounting/ledger"
ACCOUNTS_LIST_URL  = "https://api.laudus.cl/accounting/accounts/list"

# ──────────────────────────────────────────────
# Autenticación
# ──────────────────────────────────────────────
default_headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# ──────────────────────────────────────────────
# Libros (Story 12.2 — FR50/FR51/FR52)
# ──────────────────────────────────────────────
# Un mismo login de Laudus sirve varios "libros" (empresas): el companyVATId del
# login elige el libro. Antes esto era un dict `payload` de módulo evaluado en
# import-time (mono-libro por proceso); ahora cada corrida recibe un BookConfig
# explícito y el companyVATId se resuelve de env RECIÉN al hacer login.


@dataclass(frozen=True)
class BookConfig:
    """Configuración de UN libro Laudus: identidad, destino y entidades."""

    book_id: str                    # "EAG" | "RUT2"
    vat_env_var: str                # env var con el companyVATId del libro
    expected_root_name: str         # nombre de la cuenta raíz "1" (assert FR52)
    subdir: str                     # ledger/imports/<subdir>/
    pending_file: str               # ledger/imports/<pending_file> (cuarentena)
    entities: frozenset[str]        # 2º segmento de path de las cuentas del libro
    include_entityless: bool        # namespaces legacy sin entidad (solo EAG)
    importer_name: str              # etiqueta en import-log / mensajes de commit
    default_pending_entity: str     # entidad de cuarentena si el code no mapea
    pending_entity_by_root: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({}))

    @property
    def company_vat_id(self) -> str | None:
        return os.environ.get(self.vat_env_var)

    def pending_entity(self, code: str) -> str:
        """Entidad de la cuenta de cuarentena para un code desconocido del libro."""
        if code:
            return self.pending_entity_by_root.get(str(code)[0], self.default_pending_entity)
        return self.default_pending_entity


BOOKS: dict[str, BookConfig] = {
    "EAG": BookConfig(
        book_id="EAG",
        vat_env_var="LAUDUS_COMPANYVATID",
        expected_root_name="ACTIVO EAG",
        subdir="laudus",
        pending_file="_new-accounts-pending.beancount",
        entities=frozenset({"EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"}),
        include_entityless=True,
        importer_name="laudus",
        default_pending_entity="EAG",
    ),
    "RUT2": BookConfig(
        book_id="RUT2",
        vat_env_var="LAUDUS_COMPANYVATID_RUT2",
        expected_root_name="ACTIVO FFCC",
        subdir="laudus-rut2",
        pending_file="_new-accounts-pending-rut2.beancount",
        entities=frozenset({"FFCC", "JAB"}),
        include_entityless=False,
        importer_name="laudus-rut2",
        default_pending_entity="FFCC",
        # Clasificación firmada 2026-07-11: dígito de raíz → entidad (1-4 FFCC, 6-8 JAB).
        pending_entity_by_root=MappingProxyType({
            "1": "FFCC", "2": "FFCC", "3": "FFCC", "4": "FFCC",
            "6": "JAB", "7": "JAB", "8": "JAB",
        }),
    ),
}

# Todos los segmentos de entidad conocidos entre libros — un path cuyo 2º segmento
# NO está acá es "legacy sin entidad" (Equity:Apertura:*, etc.) y pertenece a EAG.
ALL_BOOK_ENTITIES: frozenset[str] = frozenset().union(*(b.entities for b in BOOKS.values()))


def get_book(book_id: str | None) -> BookConfig:
    """Resuelve el libro por id. SIN default: sin libro explícito no hay corrida (FR50)."""
    if not book_id or str(book_id) not in BOOKS:
        raise ValueError(
            f"Libro Laudus requerido y explícito (FR50): recibí {book_id!r}, "
            f"esperaba uno de {sorted(BOOKS)}. Sin libro no se lee ni escribe nada."
        )
    return BOOKS[str(book_id)]


def login_payload(book: BookConfig) -> dict:
    """Payload del login para UN libro. El companyVATId se lee de env acá (no import-time)."""
    vat = book.company_vat_id
    if not vat:
        raise RuntimeError(
            f"companyVATId del libro {book.book_id} no configurado "
            f"(env {book.vat_env_var} vacía) — se aborta antes de abrir sesión Laudus."
        )
    return {
        "userName":     os.environ.get("LAUDUS_USERNAME"),
        "password":     os.environ.get("LAUDUS_PASSWORD"),
        "companyVATId": vat,
    }


def get_endpoints(date_from, date_to):
    """Devuelve URLs y parámetros de los endpoints principales para el rango dado."""
    return {
        "GET_LEDGER": {
            "url":    LEDGER_URL,
            "params": {"dateFrom": str(date_from), "dateTo": str(date_to)},
        },
        "GET_BALANCE_SHEET": {
            "url":    BALANCE_SHEET_URL,
            "params": {"dateTo": str(date_to)},
        },
    }

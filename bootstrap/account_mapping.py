"""Mapeo de cuentas Laudus → Beancount account paths — Story 9.1.

Concentra la lógica pura (sin red, sin filesystem) que convierte una cuenta
Laudus + metadata Supabase en un nombre de cuenta Beancount válido.

Fuentes:
- Spike `_bmad-output/spike-beancount/generate.py:43-58` — slug + ROOT_MAP.
- architecture-c4.md §2.1 (naming convention), §2.3 (mapeo Categoria1 →
  Root, Entity), §2.5 (bank_account_type → Group + Root override).
"""
from __future__ import annotations

import re
from typing import Optional

# ── §2.3 — Categoria1 Laudus → (Beancount Root, Entity) ─────────────────────

MAP_CATEGORIA1_TO_ROOT_ENTITY: dict[str, tuple[str, str]] = {
    "ACTIVO EAG": ("Assets", "EAG"),
    "PASIVO": ("Liabilities", "EAG"),
    "GASTOS - EGRESOS": ("Expenses", "EAG"),
    "INGRESOS": ("Income", "EAG"),
    "DISPONIBLE JOCELYN AVAYU DEUTSCH": ("Assets", "Jocelyn"),
    "EGRESOS JOCELYN AVAYU DEUTSCH": ("Expenses", "Jocelyn"),
    "INGRESOS JOCELYN AVAYU DEUTSCH": ("Income", "Jocelyn"),
    "DISPONIBLE JAEL AVAYU DEUTSCH": ("Assets", "Jael"),
    "EGRESOS JAEL AVAYU DEUTSCH": ("Expenses", "Jael"),
    "INGRESOS JAEL AVAYU DEUTSCH": ("Income", "Jael"),
    "DISPONIBLE JOHANNA AVAYU DEUTSCH": ("Assets", "Johanna"),
    "EGRESOS JOHANNA AVAYU DEUTSCH": ("Expenses", "Johanna"),
    "INGRESOS JOHANNA AVAYU DEUTSCH": ("Income", "Johanna"),
    "DISPONIBLE JEANNETTE AVAYU DEUTSCH": ("Assets", "Jeannette"),
    "EGRESOS JEANNETTE AVAYU DEUTSCH": ("Expenses", "Jeannette"),
    "INGRESOS JEANNETTE AVAYU DEUTSCH": ("Income", "Jeannette"),
    # Resultados financieros de inversiones — confirmado por Ary 2026-05-05.
    "RESULTADOS": ("Income", "EAG"),
    # Cuentas por cobrar por entidad — confirmado por Ary 2026-05-05.
    # No aplica para Jocelyn (no tiene esa cuenta en el plan).
    "CUENTAS POR COBRAR JEANNETTE AVAYU DEUTSCH": ("Assets", "Jeannette"),
    "CUENTAS POR COBRAR JOHANNA AVAYU DEUTSCH": ("Assets", "Johanna"),
    "CUENTAS POR COBRAR JAEL AVAYU DEUTSCH": ("Assets", "Jael"),
}

# ── §2.5 — bank_account_type → (Root override, Group) ──────────────────────
#
# Q7 (corrección semántica): tarjeta_credito y linea_credito pasan a
# Liabilities — independiente de la Categoria1 Laudus (que históricamente
# las clasificaba mal en Activos).

MAP_BANK_TYPE_TO_ROOT_GROUP: dict[str, tuple[str, str]] = {
    "cta_corriente": ("Assets", "Bancos"),
    "cta_inversiones": ("Assets", "Inversiones"),
    "tarjeta_credito": ("Liabilities", "TC"),
    "linea_credito": ("Liabilities", "LineaCredito"),
}


# ── Slugify para componentes de cuenta Beancount ───────────────────────────

def normalize_account_number(s: str) -> str:
    """Pad-right con ceros a 6 dígitos (convención chilena / Supabase).

    Laudus devuelve `accountNumber` con longitud variable según jerarquía
    ("1" raíz, "11" nivel-2, "111" nivel-3, "111005" hoja). Supabase tiene
    todo padded a 6. Esta función normaliza Laudus al formato Supabase para
    que el cross-check sea trivial.

    Ejemplos:
        normalize_account_number("1") -> "100000"
        normalize_account_number("11") -> "110000"
        normalize_account_number("111005") -> "111005"
    """
    return s.ljust(6, "0")


def slugify(name: str) -> str:
    """Convierte un account name Laudus en un componente Beancount válido.

    Reglas Beancount: el componente debe empezar con mayúscula, ser ASCII,
    sin espacios. Esta implementación replica el spike validado.

    Ejemplos:
        slugify("Banco BCI - 10160175") -> "BancoBci10160175"
        slugify("Combustible Vehículos") -> "CombustibleVehculos"
        slugify("VISA Infinity (Eduardo)") -> "VisaInfinityEduardo"
    """
    s = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    parts = [p.capitalize() for p in re.split(r"[\s\-_]+", s) if p]
    out = "".join(parts)
    out = re.sub(r"[^A-Za-z0-9]", "", out)
    if not out or not out[0].isupper():
        out = "X" + out
    return out


# ── Resolución de Root, Entity, Group ──────────────────────────────────────

class UnmappableCategoria1(ValueError):
    """Categoria1 no está en `MAP_CATEGORIA1_TO_ROOT_ENTITY`."""


class UnknownBankAccountType(ValueError):
    """`bank_account_type` no está en `MAP_BANK_TYPE_TO_ROOT_GROUP`."""


def resolve_root_entity_group(
    categoria1: str,
    bank_account_type: Optional[str] = None,
) -> tuple[str, str, Optional[str]]:
    """Resuelve (Root, Entity, Group) según §2.3 + §2.5.

    Args:
        categoria1: literal de `Categoria1` Laudus (case-sensitive).
        bank_account_type: tipo bancario si la cuenta es banca, None
            si no aplica. Cuando se provee, **gana sobre Categoria1 para
            el Root** (Q7 — TC y línea de crédito deben ser Liabilities).

    Returns:
        (root, entity, group) — `group` es None si la cuenta no es bancaria.

    Raises:
        UnmappableCategoria1: si `categoria1` no está en la tabla §2.3.
        UnknownBankAccountType: si `bank_account_type` no está en §2.5.
    """
    if categoria1 not in MAP_CATEGORIA1_TO_ROOT_ENTITY:
        raise UnmappableCategoria1(
            f"Categoria1 no mapeable: {categoria1!r}. Agregar a la tabla §2.3 o "
            "reclasificar la cuenta en Supabase."
        )
    root_from_cat1, entity = MAP_CATEGORIA1_TO_ROOT_ENTITY[categoria1]

    if bank_account_type is None:
        return root_from_cat1, entity, None

    if bank_account_type not in MAP_BANK_TYPE_TO_ROOT_GROUP:
        raise UnknownBankAccountType(
            f"bank_account_type desconocido: {bank_account_type!r}. "
            f"Tipos válidos: {sorted(MAP_BANK_TYPE_TO_ROOT_GROUP)}."
        )
    root_override, group = MAP_BANK_TYPE_TO_ROOT_GROUP[bank_account_type]
    return root_override, entity, group


def build_account_path(
    root: str,
    entity: str,
    account_name: str,
    account_number: str,
    group: Optional[str] = None,
) -> str:
    """Construye el path Beancount completo siguiendo §2.1.

    Patrón sin group: `{Root}:{Entity}:{Slug(name)}-{account_number}`
    Patrón con group: `{Root}:{Entity}:{Group}:{Slug(name)}-{account_number}`
    """
    slug_name = slugify(account_name)
    if group:
        return f"{root}:{entity}:{group}:{slug_name}-{account_number}"
    return f"{root}:{entity}:{slug_name}-{account_number}"

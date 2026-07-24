"""External IDs determinísticos para el loader Odoo (E1.5).

La columna vertebral de la idempotencia: re-correr el loader hace **upsert, no
duplica**, porque cada cuenta / asiento / línea se identifica por un external ID
(XML ID de Odoo) derivado determinísticamente de sus datos Laudus. E1.5 (loader)
y E1.6 (verificador de paridad) dependen de que esta convención sea **estable**.

  → Este formato se CONGELA acá (story E1.0). No cambiarlo después.

Convención (congelada):
    account : acc_<company>_<code>     p.ej.  acc_eag_111005
    move    : mv_<company>_<je_id>     p.ej.  mv_eag_5881
    line    : aml_<je_id>_<n>          p.ej.  aml_5881_0

Normalización de los componentes:
  - `company`  → minúsculas + strip. Las dos entidades legales del proyecto son
                 "EAG" y "RUT2" (metadato `entity` del mirror). Pasarlas en
                 cualquier caja ("EAG"/"eag") produce el MISMO id → la
                 idempotencia trata a la misma entidad como una sola (feature).
                 "EAG" y "RUT2" nunca colapsan entre sí, así que dos entidades
                 con el mismo `code` (111005 en ambas) dan ids distintos.
  - `code`, `je_id` → `str().strip()` tal cual (los códigos Laudus son numéricos
                 y estables; no se re-mapean).
  - `n`        → índice **0-based** de la pata dentro del asiento (0, 1, 2, …).
                 Estable y derivable del asiento; no es el número de línea Laudus.

Cualquier componente vacío o con caracteres que romperían un XML ID de Odoo
(espacios, `.`, etc.) levanta `ValueError`: es preferible fallar fuerte a emitir
un id silenciosamente corrupto del que dependen upserts posteriores.
"""

import re

# XML ID de Odoo: letras, dígitos, guion bajo y guion. Congelado como el conjunto
# de caracteres permitido en cada componente ya normalizado.
_ALLOWED = re.compile(r"^[a-z0-9_-]+$", re.IGNORECASE)


def _component(value, *, name: str) -> str:
    """Normaliza (strip + str) y valida un componente del external ID."""
    s = str(value).strip()
    if not s:
        raise ValueError(f"external_id: componente '{name}' vacío")
    if not _ALLOWED.match(s):
        raise ValueError(
            f"external_id: componente '{name}'={value!r} tiene caracteres no "
            f"válidos para un XML ID de Odoo (permitido: [a-z0-9_-])"
        )
    return s


def account_xmlid(company, code) -> str:
    """`acc_<company>_<code>` — external ID de account.account."""
    return f"acc_{_component(company, name='company').lower()}_{_component(code, name='code')}"


def move_xmlid(company, je_id) -> str:
    """`mv_<company>_<je_id>` — external ID de account.move (asiento)."""
    return f"mv_{_component(company, name='company').lower()}_{_component(je_id, name='je_id')}"


def line_xmlid(je_id, n) -> str:
    """`aml_<je_id>_<n>` — external ID de account.move.line.

    `n` es el índice 0-based de la pata dentro del asiento.
    """
    idx = int(n)
    if idx < 0:
        raise ValueError(f"external_id: índice de línea n={n!r} debe ser >= 0")
    return f"aml_{_component(je_id, name='je_id')}_{idx}"

"""External IDs determinísticos para el loader Odoo (E1.5).

La columna vertebral de la idempotencia: re-correr el loader hace **upsert, no
duplica**, porque cada cuenta / asiento / línea se identifica por un external ID
(XML ID de Odoo) derivado determinísticamente de sus datos Laudus. E1.5 (loader)
y E1.6 (verificador de paridad) dependen de que esta convención sea **estable**.

  → Este formato se CONGELA acá (story E1.0). No cambiarlo después.

Convención (congelada):
    account : acc_<company>_<code>       p.ej.  acc_eag_111005
    move    : mv_<company>_<je_id>       p.ej.  mv_eag_5881
    line    : aml_<company>_<je_id>_<n>  p.ej.  aml_eag_5881_0

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

Por qué `company` va también en la LÍNEA (no solo en account/move): el `id` de
Laudus **reinicia por entidad** — `id=1` existe en EAG y en RUT2. Sin `company`,
la pata 0 de asientos homónimos de distinta entidad colisionaría en el mismo
`aml_1_0`, y el upsert de E1.5 haría que una entidad pise a la otra en silencio
(justo la idempotencia que este módulo protege). La línea lleva la entidad igual
que la cuenta y el asiento.

Cualquier componente vacío o con caracteres que romperían un XML ID de Odoo
(espacios, `.`, los separadores `_`/`-`, no-ASCII) levanta `ValueError`: es
preferible fallar fuerte a emitir un id silenciosamente corrupto o colisionable
del que dependen upserts posteriores.
"""

import re
import unicodedata

# Cada componente YA normalizado: solo alfanumérico ASCII. Se excluye a propósito
# el `_`/`-` (son el SEPARADOR del id: un componente con separador adentro haría
# el id ambiguo/colisionable, p.ej. ("eag","1_2") vs ("eag_1","2")) y los no-ASCII
# (bajo IGNORECASE, `re.ASCII` evita que el signo Kelvin U+212A "matchee" [a-z]).
_ALLOWED = re.compile(r"^[a-z0-9]+$", re.IGNORECASE | re.ASCII)


def _component(value, *, name: str) -> str:
    """Normaliza (strip + str) y valida un componente del external ID."""
    s = str(value).strip()
    if not s:
        raise ValueError(f"external_id: componente '{name}' vacío")
    if not _ALLOWED.match(s):
        raise ValueError(
            f"external_id: componente '{name}'={value!r} tiene caracteres no "
            f"válidos para un XML ID de Odoo (permitido: [a-z0-9] ASCII)"
        )
    return s


def _line_index(n) -> int:
    """Valida y normaliza el índice de pata `n` (fail-loud, no truncar en silencio).

    Rechaza `bool` (`True` daría índice 1) y `float` (`2.9` truncaría a 2, un id
    corrupto silencioso); acepta `int` y string entera (`"3"`). `None`/basura →
    `ValueError`, coherente con el contrato fail-loud del módulo.
    """
    if isinstance(n, bool) or isinstance(n, float):
        raise ValueError(f"external_id: índice de línea n={n!r} debe ser un entero")
    try:
        idx = int(n)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"external_id: índice de línea n={n!r} inválido") from exc
    if idx < 0:
        raise ValueError(f"external_id: índice de línea n={n!r} debe ser >= 0")
    return idx


def account_xmlid(company, code) -> str:
    """`acc_<company>_<code>` — external ID de account.account."""
    return f"acc_{_component(company, name='company').lower()}_{_component(code, name='code')}"


def move_xmlid(company, je_id) -> str:
    """`mv_<company>_<je_id>` — external ID de account.move (asiento)."""
    return f"mv_{_component(company, name='company').lower()}_{_component(je_id, name='je_id')}"


def line_xmlid(company, je_id, n) -> str:
    """`aml_<company>_<je_id>_<n>` — external ID de account.move.line.

    `n` es el índice 0-based de la pata dentro del asiento. Lleva `company`
    porque el `id` de Laudus reinicia por entidad (sin ella, `aml_1_0` chocaría
    entre EAG y RUT2).
    """
    idx = _line_index(n)
    return (
        f"aml_{_component(company, name='company').lower()}"
        f"_{_component(je_id, name='je_id')}_{idx}"
    )


# ---------------------------------------------------------------------------
# Helpers NUEVOS de E1.5 (partners + cuentas analíticas). Los 3 de arriba
# están CONGELADOS (E1.0) y no se tocan; estos son adiciones con la misma
# disciplina fail-loud. Los nombres canónicos (lista Valentina / valores de
# planes) traen espacios/tildes/paréntesis → se slugifican a [a-z0-9]. La
# unicidad slug↔canónico la valida el CONSUMIDOR (`load.py`) sobre su
# población cerrada: dos canónicos distintos con el mismo slug es fail-loud
# allá (acá no hay visibilidad de la población).
# ---------------------------------------------------------------------------


def slug(value, *, name: str = "value") -> str:
    """Slug determinístico de un nombre canónico: minúsculas, sin tildes,
    solo [a-z0-9]. `"José Alazraki"` → `"josealazraki"`. Vacío → ValueError
    (un canónico 100% no-ASCII produciría un xmlid sin identidad)."""
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]", "", text.lower())
    if not s:
        raise ValueError(
            f"external_id: slug de '{name}'={value!r} quedó vacío — el nombre "
            f"no tiene caracteres [a-z0-9] rescatables"
        )
    return s


def partner_xmlid(canonical_name) -> str:
    """`prt_<slug>` — external ID de res.partner (partner canónico E1.4)."""
    return f"prt_{slug(canonical_name, name='partner')}"


def analytic_xmlid(plan, value) -> str:
    """`aa_<plan>_<slug>` — external ID de account.analytic.account.

    `plan` es la clave interna del plan (propiedad_objeto, area_centro,
    offshore_vehiculo, por_cuenta_de, socio_uso, entidad — E1.1) y `value`
    el valor canónico de la dimensión. El plan también se slugifica (trae
    `_`, que es el separador del id): `aa_propiedadobjeto_viagris`.
    """
    return f"aa_{slug(plan, name='plan')}_{slug(value, name='analytic value')}"


def origin_account_xmlid(company, path) -> str:
    """`accs_<company>_<slug>` — external ID de una cuenta de ORIGEN SINCERADO.

    Son los destinos que E1.3 escribe en `line.odoo_account` al re-rutear una
    pata (naturalezas B/H: `Assets:EAG:JuliusBaer`, `Assets:EAG:InvTecnion`, …)
    y que NO existen como destino de ninguna fila de la tabla de mapeo — no
    tienen código Laudus, así que el formato congelado `acc_<company>_<code>`
    no les aplica. Prefijo propio `accs_` (sincerado) para no invadir ese
    namespace; el path completo se slugifica (review E1.5, P1).
    """
    return (
        f"accs_{_component(company, name='company').lower()}"
        f"_{slug(path, name='origin account path')}"
    )

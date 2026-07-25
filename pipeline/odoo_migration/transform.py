"""Transformador de colapso del plan (story E1.2).

Lee el espejo Beancount crudo y emite registros neutrales estilo Odoo (moves +
líneas, Python puro, SIN Odoo): cada línea lleva su cuenta Odoo destino según
la tabla de mapeo Y el código Laudus origen estampado — aunque N códigos
colapsen a 1 cuenta, cada línea conserva su origen. Esa es la llave de la
paridad (`parity.py`): el colapso cambia la cuenta destino pero NUNCA toca el
código origen.

Universo: SOLO transacciones con meta `source: "laudus-erp"`. El mirror
(`ledger/main.beancount`) también trae asientos manuales del proyecto
(conciliación TC, categorizaciones → p.ej. `Expenses:EAG:Suspense`) que NO son
historia Laudus y quedan fuera de la migración — filtro de universo, no
descarte silencioso. El lado-Laudus del verificador usa el MISMO filtro.

Qué NO hace (scope E1.2): reglas por transacción (sinceramiento por glosa,
washes → E1.3), dimensiones analíticas/partners (→ E1.4), carga a Odoo (E1.5).
Los destinos que la tabla ya redirige a nivel CUENTA (p.ej. Sade → activo) se
mapean tal cual dice la columna `odoo`.

Fail-loud: cuenta sin meta `code`, mapeo inexistente, asiento sin meta `id` o
que cruza compañías → excepción con contexto. Nada se pierde en silencio.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from beancount.core import data

from pipeline.odoo_migration.mapping import MappingTable, company_for_entity

#: Meta `source` que identifica el universo Laudus dentro del mirror.
LAUDUS_SOURCE = "laudus-erp"


@dataclass
class OdooLineRecord:
    """Una pata transformada. `laudus_code`/`entity` son lo que E1.5 estampará
    como `x_laudus_account_code`/`x_laudus_entity`; `amount` es el monto FIRMADO
    en su moneda (`units.number` del mirror — en Odoo será debit-credit)."""

    n: int  # índice 0-based de la pata (el de `line_xmlid`, E1.0)
    odoo_account: str
    laudus_code: str
    entity: str
    currency: str
    amount: Decimal
    desc: str = ""
    # Metadata de auditoría del sinceramiento (E1.3) — vacía hasta que la pata
    # pasa por `sincerar` (NFR1: cada re-clasificación es listable y reversible).
    sinc_naturaleza: str = ""  # 0/A..H
    sinc_regla: str = ""  # qué decidió (codigo:… / glosa:… / cuenta-vs-glosa)
    sinc_flag: str = ""  # "" | "sin clasificar" | "revisar con contadoras"
    odoo_account_colapso: str = ""  # destino de colapso original (pre-sinceramiento)
    # Metadata de partner + dimensiones analíticas (E1.4) — vacía hasta que la
    # pata pasa por `dimensionar`. E1.5 la convierte en `partner_id` /
    # `analytic_distribution`; acá es solo metadata (no cambia cuenta ni monto).
    partner: str = ""  # partner canónico (lista Valentina 2026-07-23)
    partner_categoria: str = ""  # socio-particion | socio-disperso | deudor | …
    partner_regla: str = ""  # cuenta:partner / cuenta:pin-lista / cuenta:socio / glosa:…
    partner_flag: str = ""  # "" | "revisar con contadoras"
    dim_propiedad: str = ""  # plan propiedad_objeto (columna `prop`)
    dim_area: str = ""  # plan area_centro (columna `area`, salvo por-cuenta-de)
    dim_offshore: str = ""  # plan offshore_vehiculo (columna `offshore`)
    dim_por_cuenta_de: str = ""  # plan por_cuenta_de (valor `por-cuenta-de` de `area`)
    dim_socio_uso: str = ""  # plan socio_uso (SOLO por glosa en retiros, E1.4 Task 3c)


@dataclass
class OdooMoveRecord:
    """Un asiento transformado. `je_id` = meta `id` de Laudus (NO `je_num`),
    consistente con `external_ids.py` (E1.0) y `x_laudus_je_id` (E1.1)."""

    company: str
    je_id: str
    date: datetime.date
    narration: str
    lines: list[OdooLineRecord] = field(default_factory=list)


def account_codes(entries) -> dict[str, str]:
    """Mapa cuenta Beancount → código Laudus, desde la meta `code` del open."""
    return {
        e.account: str(e.meta["code"]).strip()
        for e in entries
        if isinstance(e, data.Open) and e.meta and e.meta.get("code")
    }


def entity_of_account(account: str) -> str:
    """Entidad interna = segundo segmento del nombre (`Assets:Jocelyn:…`)."""
    parts = account.split(":")
    if len(parts) < 2 or not parts[1]:
        raise ValueError(f"transform: cuenta sin segmento de entidad: {account!r}")
    return parts[1]


def laudus_transactions(entries) -> list[data.Transaction]:
    """Las transacciones del universo Laudus (meta `source: "laudus-erp"`)."""
    return [
        e
        for e in entries
        if isinstance(e, data.Transaction)
        and e.meta
        and e.meta.get("source") == LAUDUS_SOURCE
    ]


def collapse(entries, mapping: MappingTable) -> list[OdooMoveRecord]:
    """Aplica el colapso del plan a todo el universo Laudus de `entries`."""
    codes = account_codes(entries)
    moves: list[OdooMoveRecord] = []
    seen: set[tuple[str, str]] = set()
    for txn in laudus_transactions(entries):
        je_id = str(txn.meta.get("id") or "").strip()
        if not je_id:
            raise ValueError(
                f"transform: asiento {txn.date} {txn.narration!r} sin meta `id` "
                f"(el je_id es la llave de idempotencia de E1.5)"
            )
        move = OdooMoveRecord(
            company="",  # se fija con la primera línea (y se valida homogénea)
            je_id=je_id,
            date=txn.date,
            narration=txn.narration or "",
        )
        for n, posting in enumerate(txn.postings):
            code = codes.get(posting.account)
            if not code:
                raise ValueError(
                    f"transform: la cuenta {posting.account!r} (asiento id={je_id}) "
                    f"no tiene meta `code` — no es una cuenta Laudus mapeable"
                )
            entity = entity_of_account(posting.account)
            row = mapping.get(entity, code)  # KeyError con contexto si falta
            company = company_for_entity(entity)
            if not move.company:
                move.company = company
            elif move.company != company:
                raise ValueError(
                    f"transform: el asiento id={je_id} cruza compañías "
                    f"({move.company} vs {company}) — el id de Laudus es por "
                    f"entidad legal, esto es data corrupta"
                )
            if posting.units is None:
                raise ValueError(
                    f"transform: pata {n} del asiento id={je_id} sin monto"
                )
            move.lines.append(
                OdooLineRecord(
                    n=n,
                    odoo_account=row.odoo_account,
                    laudus_code=code,
                    entity=entity,
                    currency=posting.units.currency,
                    amount=posting.units.number,
                    desc=str((posting.meta or {}).get("desc", "")),
                )
            )
        if not move.lines:
            raise ValueError(
                f"transform: asiento id={je_id} ({txn.date}) sin patas — "
                f"quedaría sin compañía y llegaría vacío a E1.5"
            )
        key = (move.company, je_id)
        if key in seen:
            raise ValueError(
                f"transform: je_id duplicado {key!r} — ¿doble import en el "
                f"mirror? colisionaría el external ID mv_<company>_<je_id> (E1.5)"
            )
        seen.add(key)
        moves.append(move)
    return moves

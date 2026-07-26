"""Payload builder del loader (story E1.5) — Tier A, Python puro, SIN Odoo.

Convierte el output de la cadena de transformadores (`collapse → sincerar →
dimensionar`) + la tabla de mapeo en payloads neutrales listos para escribir
en Odoo 18: el chart colapsado, los partners canónicos, las cuentas analíticas
y los asientos (debit/credit + `amount_currency` + `partner_id` +
`analytic_distribution`), cada uno con su external ID determinístico. Acá vive
TODA la lógica del loader; la capa que toca Odoo (`loader_rpc.py`) solo aplica
estos payloads con upsert por xmlid.

Decisiones pinneadas (story E1.5, winston §2.3/§6/§7):
  - **El chart es el plan COLAPSADO**: una cuenta Odoo por `(company,
    odoo_account)`. Los external IDs congelados `acc_<company>_<code>` (E1.0)
    se emiten POR CÓDIGO LAUDUS: N alias xmlid → la MISMA cuenta colapsada
    (ir.model.data permite N nombres al mismo res_id). `code` de la cuenta =
    el MENOR código Laudus origen, en orden NUMÉRICO — (largo, valor), no
    lexicográfico (determinístico; las cuentas 1:1 conservan su código —
    spec §1.1 "no se renumera").
  - **Las líneas rutean por su DESTINO, no por su código** (review E1.5, P1):
    `line.odoo_account` es el destino FINAL que dejó la cadena — E1.3 lo
    reescribe al sincerar (naturalezas B/H) sin tocar `laudus_code`. Rutear
    por código mandaría esas patas a la cuenta pre-sinceramiento. Los destinos
    sincerados que no existen en la tabla (cuentas de ORIGEN: JuliusBaer,
    InvTecnion, …) se agregan al chart vía `build_origin_accounts` con xmlid
    propio `accs_*` (el namespace congelado `acc_*` es por código Laudus).
  - **Convención de signo** (winston §6): monto firmado Beancount ==
    `debit − credit`. Positivo → debit, negativo → credit, en moneda compañía
    (CLP). Las líneas no-CLP exigen `price` (defer E1.2 cerrado acá): el
    contravalor CLP = amount × price; `amount_currency` = el monto firmado en
    su moneda. Un move que no balancea en CLP falla ANTES de tocar Odoo.
  - **`otype` con población cerrada** (cierra defers E1.2/E1.4): los 7 valores
    reales del CSV mapean fijo a `account_type` de Odoo 18; un valor nuevo o
    dos códigos que colapsan al mismo destino con `otype` distinto → LoadError
    con contexto, nunca una cuenta con tipo adivinado.
  - **Odoo queda tonto**: este módulo NO clasifica ni corrige — si algo falta
    o no cuadra, fail-loud; nunca "arreglar" en el loader.
"""

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from pipeline.odoo_migration.external_ids import (
    account_xmlid,
    analytic_xmlid,
    line_xmlid,
    move_xmlid,
    origin_account_xmlid,
    partner_xmlid,
)
from pipeline.odoo_migration.mapping import MappingTable

#: Moneda de las 2 compañías (hook E1.1). Las líneas en esta moneda van como
#: debit/credit pelados; cualquier otra lleva currency_id + amount_currency.
COMPANY_CURRENCY = "CLP"

#: Diario receptor por compañía — MISMA tabla que el hook de E1.1 (no divergir).
JOURNAL_CODE = {"EAG": "LAU1", "RUT2": "LAU2"}

#: Población CERRADA de `otype` (los 7 valores reales del CSV, verificado
#: 2026-07-25: expense 358 / income 80 / asset 65 / receivable 33 / bank 20 /
#: liability 11 / equity 2) → `account_type` de Odoo 18. Un valor nuevo en la
#: tabla revienta acá (cierra el defer E1.2 "otype sin población cerrada").
OTYPE_TO_ACCOUNT_TYPE = {
    "asset": "asset_current",
    "bank": "asset_cash",
    "receivable": "asset_receivable",
    "liability": "liability_current",
    "equity": "equity",
    "income": "income",
    "expense": "expense",
}

#: Los 6 planes analíticos contenedores (E1.1, XML noupdate): clave interna →
#: xmlid del record en el módulo. E1.5 los REFERENCIA, no los crea.
PLAN_XMLIDS = {
    "propiedad_objeto": "x_laudus_migration.plan_propiedad_objeto",
    "area_centro": "x_laudus_migration.plan_area_centro",
    "offshore_vehiculo": "x_laudus_migration.plan_offshore_vehiculo",
    "por_cuenta_de": "x_laudus_migration.plan_por_cuenta_de",
    "socio_uso": "x_laudus_migration.plan_socio_uso",
    "entidad": "x_laudus_migration.plan_entidad",
}

#: Campo de metadata E1.4 en la línea → plan analítico que puebla. La entidad
#: no está acá: se estampa SIEMPRE desde `line.entity` (plan `entidad`).
_LINE_DIM_TO_PLAN = {
    "dim_propiedad": "propiedad_objeto",
    "dim_area": "area_centro",
    "dim_offshore": "offshore_vehiculo",
    "dim_por_cuenta_de": "por_cuenta_de",
    "dim_socio_uso": "socio_uso",
}


class LoadError(ValueError):
    """El payload no se puede construir con garantías — no se toca Odoo."""


# ---------------------------------------------------------------------------
# Chart (plan de cuentas colapsado)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChartAccount:
    """Una cuenta Odoo colapsada + TODOS sus alias `acc_<company>_<code>`."""

    xmlid: str  # alias primario (el del código representante)
    aliases: tuple  # todos los acc_<company>_<code> de sus códigos origen
    company: str
    code: str  # representante = menor código Laudus origen
    name: str  # el path `odoo` de la tabla
    account_type: str
    x_laudus_group: str  # cat2/cat3 del representante (contexto, no paridad)


def build_chart(mapping: MappingTable) -> list[ChartAccount]:
    """Chart colapsado desde la tabla: una cuenta por (company, odoo_account).

    Valida (fail-loud): `otype` dentro de la población cerrada y CONSISTENTE
    entre los códigos que colapsan al mismo destino (cierra los 2 defers de
    E1.2), y unicidad del código representante por compañía.
    """
    groups: dict[tuple[str, str], list] = {}
    for row in mapping.rows:
        groups.setdefault((row.company, row.odoo_account), []).append(row)

    accounts: list[ChartAccount] = []
    seen_codes: set[tuple[str, str]] = set()
    for (company, dest), rows in sorted(groups.items()):
        otypes = {r.odoo_type for r in rows}
        if len(otypes) > 1:
            raise LoadError(
                f"load: destino ({company!r}, {dest!r}) colapsa códigos con "
                f"otype INCONSISTENTE {sorted(otypes)!r} (códigos "
                f"{sorted(r.code for r in rows)!r}) — la cuenta tendría tipo "
                f"ambiguo; corregir la tabla"
            )
        otype = otypes.pop()
        if otype not in OTYPE_TO_ACCOUNT_TYPE:
            raise LoadError(
                f"load: otype {otype!r} desconocido en destino ({company!r}, "
                f"{dest!r}) — población cerrada "
                f"{sorted(OTYPE_TO_ACCOUNT_TYPE)!r}; ¿columna corrupta o tipo "
                f"nuevo sin mapear?"
            )
        # Menor código en orden NUMÉRICO: (largo, valor). Puro-string haría
        # "9999" > "111005"; con largos {2,4,6} + "GVAR" esto es determinístico
        # y coincide con el orden numérico para códigos de dígitos (review P7).
        rep = min(rows, key=lambda r: (len(r.code), r.code))
        key = (company, rep.code)
        if key in seen_codes:
            raise LoadError(
                f"load: código representante duplicado {key!r} — dos destinos "
                f"colapsados eligieron la misma cuenta (bug del builder)"
            )
        seen_codes.add(key)
        group = "/".join(p for p in (rep.cat2, rep.cat3) if p)
        aliases = tuple(sorted(account_xmlid(company, r.code) for r in rows))
        accounts.append(
            ChartAccount(
                xmlid=account_xmlid(company, rep.code),
                aliases=aliases,
                company=company,
                code=rep.code,
                name=dest,
                account_type=OTYPE_TO_ACCOUNT_TYPE[otype],
                x_laudus_group=group,
            )
        )
    return accounts


#: Marca de grupo para las cuentas de origen sincerado (no vienen de cat2/cat3).
ORIGIN_GROUP = "ORIGEN-SINCERADO"


def build_origin_accounts(moves, mapping: MappingTable) -> list[ChartAccount]:
    """Cuentas de ORIGEN SINCERADO: destinos que E1.3 escribió en las patas
    (`line.odoo_account`) y que NO son destino de ninguna fila de la tabla.

    No tienen código Laudus: xmlid `accs_<company>_<slug>` (aditivo, no toca
    el namespace congelado `acc_*`), `code` = slug del path (determinístico,
    estable ante nuevas cuentas; no colisiona con los códigos numéricos/GVAR
    de la tabla) y tipo por población cerrada: HOY todos los destinos
    sincerados fuera de tabla son cuentas de activo (`Assets:` — naturalezas
    B/H de E1.3); otro root → LoadError, no un tipo adivinado. La numeración
    definitiva del plan es pregunta guardada a Valentina (review E1.5, P1).
    """
    table_dests = {(r.company, r.odoo_account) for r in mapping.rows}
    dests = sorted(
        {(m.company, l.odoo_account) for m in moves for l in m.lines} - table_dests
    )
    accounts: list[ChartAccount] = []
    for company, path in dests:
        if not path.startswith("Assets:"):
            raise LoadError(
                f"load: destino sincerado ({company!r}, {path!r}) no está en "
                f"la tabla y no es una cuenta de activo (`Assets:`) — población "
                f"cerrada de orígenes E1.3; ¿regla nueva sin mapear?"
            )
        xmlid = origin_account_xmlid(company, path)
        accounts.append(
            ChartAccount(
                xmlid=xmlid,
                aliases=(xmlid,),
                company=company,
                code=xmlid.split("_", 2)[2],  # slug del path — único por cía
                name=path,
                account_type="asset_current",
                x_laudus_group=ORIGIN_GROUP,
            )
        )
    _dedupe_by_slug([(a.xmlid, a.name) for a in accounts], kind="cuentas de origen")
    return accounts


# ---------------------------------------------------------------------------
# Partners + cuentas analíticas (las poblaciones REALES del output E1.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PartnerPayload:
    xmlid: str
    name: str  # canónico E1.4 (lista Valentina) — va tal cual a res.partner


@dataclass(frozen=True)
class AnalyticPayload:
    xmlid: str
    plan: str  # clave interna (PLAN_XMLIDS)
    plan_xmlid: str
    name: str  # valor canónico de la dimensión


def _dedupe_by_slug(pairs, *, kind: str) -> None:
    """Dos canónicos DISTINTOS con el mismo slug harían un xmlid ambiguo y el
    upsert pisaría uno con otro en silencio — fail-loud (población cerrada)."""
    by_xmlid: dict[str, str] = {}
    for xmlid, name in pairs:
        prev = by_xmlid.setdefault(xmlid, name)
        if prev != name:
            raise LoadError(
                f"load: colisión de slug en {kind}: {prev!r} y {name!r} "
                f"producen el mismo xmlid {xmlid!r} — renombrar el canónico"
            )


def build_partners(moves) -> list[PartnerPayload]:
    """Partners canónicos presentes en el output (metadata E1.4), deduplicados."""
    names = {l.partner for m in moves for l in m.lines if l.partner}
    pairs = sorted((partner_xmlid(n), n) for n in names)
    _dedupe_by_slug(pairs, kind="partners")
    return [PartnerPayload(xmlid=x, name=n) for x, n in pairs]


def build_analytic(moves) -> list[AnalyticPayload]:
    """Cuentas analíticas: valores de los 5 planes estampados por E1.4 + el
    plan `entidad` desde `line.entity` (E1.4 lo dejó explícito para E1.5)."""
    values: set[tuple[str, str]] = set()
    for move in moves:
        for line in move.lines:
            for dim_field, plan in _LINE_DIM_TO_PLAN.items():
                value = getattr(line, dim_field)
                if value:
                    values.add((plan, value))
            values.add(("entidad", line.entity))
    pairs = sorted((analytic_xmlid(p, v), p, v) for p, v in values)
    _dedupe_by_slug([(x, f"{p}:{v}") for x, p, v in pairs], kind="analíticas")
    return [
        AnalyticPayload(xmlid=x, plan=p, plan_xmlid=PLAN_XMLIDS[p], name=v)
        for x, p, v in pairs
    ]


# ---------------------------------------------------------------------------
# Moves (asientos + líneas)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinePayload:
    xmlid: str
    account_xmlid: str  # cuenta del DESTINO de la pata (acc_* colapsada o accs_* origen)
    name: str  # desc de la pata (o el ref del move si la desc viene vacía)
    debit: Decimal  # contravalor CLP (≥ 0)
    credit: Decimal  # contravalor CLP (≥ 0)
    currency: str | None  # None = moneda compañía; "USD" = lleva currency_id
    amount_currency: Decimal | None  # monto FIRMADO en su moneda (solo no-CLP)
    x_laudus_account_code: str
    x_laudus_entity: str
    partner_xmlid: str | None
    analytic_xmlids: tuple  # aa_* de las dims presentes (cada una al 100%)


@dataclass(frozen=True)
class MovePayload:
    xmlid: str
    company: str
    journal_code: str
    date: datetime.date
    ref: str
    x_laudus_je_id: str
    lines: tuple


def _contravalor(line, company: str, je_id: str) -> Decimal:
    """Monto firmado de la pata en moneda compañía (CLP).

    El contravalor no-CLP se CUANTIZA a la precisión de CLP (0 decimales,
    half-up — lo mismo que Odoo hace al escribir cada línea): chequear el
    balance sobre Decimals sin cuantizar dejaría pasar moves que Odoo, tras
    redondear línea a línea, postea desbalanceados (review E1.5, P5)."""
    if line.currency == COMPANY_CURRENCY:
        return line.amount
    if line.price is None:
        raise LoadError(
            f"load: pata {line.n} del asiento {company}/{je_id} en "
            f"{line.currency} SIN price — sin contravalor no hay debit/credit "
            f"(defer E1.2: el mirror registra el precio en el posting)"
        )
    return (line.amount * line.price).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def build_moves(moves, chart) -> list[MovePayload]:
    """Payloads de asientos. Balance por move en CLP o LoadError — un asiento
    desbalanceado NUNCA llega a Odoo (allá reventaría el post, acá revienta
    con contexto).

    `chart` = `build_chart(tabla) + build_origin_accounts(moves, tabla)`: cada
    línea rutea a la cuenta de su DESTINO `(company, line.odoo_account)` — el
    que dejó la cadena, sinceramiento E1.3 incluido. Un destino sin cuenta en
    el chart es LoadError (review E1.5, P1)."""
    dest_map = {(a.company, a.name): a.xmlid for a in chart}
    payloads: list[MovePayload] = []
    seen_move_xmlids: set[str] = set()
    for move in moves:
        journal = JOURNAL_CODE.get(move.company)
        if journal is None:
            raise LoadError(
                f"load: compañía {move.company!r} sin diario (asiento "
                f"{move.je_id}) — JOURNAL_CODE cubre {sorted(JOURNAL_CODE)!r}"
            )
        xmlid = move_xmlid(move.company, move.je_id)
        if xmlid in seen_move_xmlids:
            raise LoadError(
                f"load: asiento duplicado {move.company}/{move.je_id} — dos "
                f"moves del input producen el mismo xmlid {xmlid!r}; el upsert "
                f"los crearía dos veces (review E1.5, P10)"
            )
        seen_move_xmlids.add(xmlid)
        lines: list[LinePayload] = []
        balance = Decimal("0")
        for line in move.lines:
            clp = _contravalor(line, move.company, move.je_id)
            balance += clp
            account = dest_map.get((move.company, line.odoo_account))
            if account is None:
                raise LoadError(
                    f"load: pata {line.n} del asiento {move.company}/"
                    f"{move.je_id} rutea a ({move.company!r}, "
                    f"{line.odoo_account!r}) y esa cuenta no está en el chart "
                    f"— ¿faltó build_origin_accounts o cambió la tabla?"
                )
            is_foreign = line.currency != COMPANY_CURRENCY
            dims = [
                analytic_xmlid(plan, getattr(line, dim_field))
                for dim_field, plan in _LINE_DIM_TO_PLAN.items()
                if getattr(line, dim_field)
            ]
            dims.append(analytic_xmlid("entidad", line.entity))
            lines.append(
                LinePayload(
                    xmlid=line_xmlid(move.company, move.je_id, line.n),
                    account_xmlid=account,
                    name=line.desc or move.narration,
                    debit=clp if clp > 0 else Decimal("0"),
                    credit=-clp if clp < 0 else Decimal("0"),
                    currency=line.currency if is_foreign else None,
                    amount_currency=line.amount if is_foreign else None,
                    x_laudus_account_code=line.laudus_code,
                    x_laudus_entity=line.entity,
                    partner_xmlid=partner_xmlid(line.partner) if line.partner else None,
                    analytic_xmlids=tuple(sorted(dims)),
                )
            )
        if balance != 0:
            raise LoadError(
                f"load: asiento {move.company}/{move.je_id} ({move.date}) NO "
                f"balancea en {COMPANY_CURRENCY}: Σ = {balance} — ni se toca "
                f"Odoo con esto; ¿pata no-CLP con price incorrecto?"
            )
        payloads.append(
            MovePayload(
                xmlid=move_xmlid(move.company, move.je_id),
                company=move.company,
                journal_code=journal,
                date=move.date,
                ref=move.narration,
                x_laudus_je_id=move.je_id,
                lines=tuple(lines),
            )
        )
    return payloads

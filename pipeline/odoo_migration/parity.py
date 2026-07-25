"""Verificador de paridad Tier A (story E1.2) — Python puro, SIN Odoo.

Nace acá y corre como REGRESIÓN tras cada transformador posterior (E1.3, E1.4):
la paridad-origen es invariante al colapso Y al sinceramiento (el código origen
viaja en la línea pase lo que pase con la cuenta destino), así que el mismo
verificador vale para toda la cadena. E1.6 replica estos checks contra el Odoo
real cargado (Tier B).

Tres verificaciones:
  1. Paridad-ORIGEN (FR8, el gate):  Σ(líneas por código origen, por moneda,
     por compañía) == Σ(units.number) del mirror. 0 diffs.
  2. Gate de DESTINO (FR12a): Σ por cuenta Odoo destino == Σ de los códigos
     origen que la tabla mapea a ese destino (pesca una línea con código
     correcto pero cuenta destino inconsistente con la tabla).
  3. CONTEOS (FR12b): N moves == N transacciones, N líneas == N postings —
     ninguna fusión/partición silenciosa. Las exclusiones (washes de E1.3) se
     declaran por IDENTIDAD (`excluded_je_ids={(company, je_id), …}`):
     `verify_counts` verifica que exactamente esas faltan — ni una más, ni una
     menos — y que el conjunto excluido netea a 0 por código. Nunca en
     silencio, nunca por conteo ciego.

Convención de signo (winston §6): Beancount guarda el número firmado
(activo/gasto +, ingreso/pasivo/equity −); la línea transformada lo conserva y
en Odoo será `debit - credit`. Por eso las sumas cuadran exactas, por moneda
(CLP con CLP, USD con USD — nunca se convierte; IAS 21 es Fase 3).

El lado-Laudus se calcula desde las MISMAS entries con el MISMO filtro de
universo (`source: "laudus-erp"`) que usa el transformador — si no, la paridad
compararía universos distintos.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from pipeline.odoo_migration.mapping import MappingTable, company_for_entity
from pipeline.odoo_migration.transform import (
    OdooMoveRecord,
    account_codes,
    entity_of_account,
    laudus_transactions,
)


class ParityError(AssertionError):
    """El gate de paridad falló. El mensaje trae los diffs."""


@dataclass(frozen=True)
class ParityDiff:
    """Un descuadre de paridad-origen en (company, code, currency)."""

    company: str
    code: str
    currency: str
    laudus: Decimal
    transformed: Decimal

    @property
    def diff(self) -> Decimal:
        return self.laudus - self.transformed


@dataclass(frozen=True)
class DestinationDiff:
    """Un descuadre del gate de destino en (company, odoo_account, currency)."""

    company: str
    odoo_account: str
    currency: str
    expected: Decimal  # Σ de los códigos origen mapeados a este destino
    actual: Decimal  # Σ de las líneas transformadas en este destino

    @property
    def diff(self) -> Decimal:
        return self.expected - self.actual


def laudus_balances(entries) -> dict[tuple[str, str, str], Decimal]:
    """Lado Laudus (la verdad): Σ units.number por (company, code, currency)."""
    codes = account_codes(entries)
    balances: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for txn in laudus_transactions(entries):
        for posting in txn.postings:
            code = codes.get(posting.account)
            if not code:
                raise ValueError(
                    f"parity: la cuenta {posting.account!r} no tiene meta `code`"
                )
            if posting.units is None:
                raise ValueError(
                    f"parity: pata sin monto en el asiento "
                    f"id={txn.meta.get('id')!r} ({posting.account})"
                )
            entity = entity_of_account(posting.account)
            key = (company_for_entity(entity), code, posting.units.currency)
            balances[key] += posting.units.number
    return dict(balances)


def transformed_balances(
    moves: list[OdooMoveRecord],
) -> dict[tuple[str, str, str], Decimal]:
    """Lado transformado: Σ amount por (company, x_laudus_account_code, currency).

    La company se deriva de la ENTITY de cada línea (no del move) — así un
    código estampado con la entidad equivocada descuadra, no se camufla.
    """
    balances: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for move in moves:
        for line in move.lines:
            key = (company_for_entity(line.entity), line.laudus_code, line.currency)
            balances[key] += line.amount
    return dict(balances)


def verify_origin_parity(entries, moves) -> list[ParityDiff]:
    """FR8: 0 diffs entre el mirror y el output transformado, por código origen."""
    laudus = laudus_balances(entries)
    transformed = transformed_balances(moves)
    diffs = []
    for key in sorted(set(laudus) | set(transformed)):
        lado_laudus = laudus.get(key, Decimal(0))
        lado_odoo = transformed.get(key, Decimal(0))
        if lado_laudus != lado_odoo:
            company, code, currency = key
            diffs.append(
                ParityDiff(company, code, currency, lado_laudus, lado_odoo)
            )
    return diffs


def _txn_identity(txn) -> tuple[str, str]:
    """(company, je_id) de una transacción del mirror — la identidad que usan
    las exclusiones declaradas (E1.3: washes)."""
    je_id = str(txn.meta.get("id") or "").strip()
    company = company_for_entity(entity_of_account(txn.postings[0].account))
    return (company, je_id)


def verify_destination(
    entries,
    moves,
    mapping: MappingTable,
    *,
    route=None,
    excluded_je_ids: frozenset | set = frozenset(),
) -> list[DestinationDiff]:
    """FR12a: Σ por cuenta Odoo destino == Σ de sus códigos origen mapeados.

    El lado esperado se computa desde el MIRROR (no desde las líneas), ruteando
    cada (entity, code) a su destino — cruza el output contra la fuente, no
    contra sí mismo. Por defecto rutea por la tabla (post-colapso, E1.2);
    `route(entity, code, desc, amount, collapsed_account)` permite componer
    transformadores posteriores (E1.3: el sinceramiento comparte el ruteo con
    el transformador — el cross-check independiente son las cifras pinneadas
    del inventario). Los moves excluidos por identidad se saltan en el esperado.

    OJO standalone: esta función NO valida las exclusiones declaradas
    (existencia en el mirror / ausencia del output / neteo a 0) — eso lo hace
    `verify_counts`. Para el gate completo usar `run_tier_a`.
    """
    codes = account_codes(entries)
    expected: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for txn in laudus_transactions(entries):
        if txn.postings and _txn_identity(txn) in excluded_je_ids:
            continue
        for posting in txn.postings:
            code = codes.get(posting.account)
            if not code:
                raise ValueError(
                    f"parity: la cuenta {posting.account!r} no tiene meta `code`"
                )
            if posting.units is None:
                raise ValueError(
                    f"parity: pata sin monto en el asiento "
                    f"id={txn.meta.get('id')!r} ({posting.account})"
                )
            entity = entity_of_account(posting.account)
            row = mapping.get(entity, code)
            if route is None:
                account = row.odoo_account
            else:
                desc = str((posting.meta or {}).get("desc", ""))
                account = route(
                    entity, code, desc, posting.units.number, row.odoo_account
                )
            key = (row.company, account, posting.units.currency)
            expected[key] += posting.units.number

    actual: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for move in moves:
        for line in move.lines:
            key = (
                company_for_entity(line.entity),
                line.odoo_account,
                line.currency,
            )
            actual[key] += line.amount

    diffs = []
    for key in sorted(set(expected) | set(actual)):
        exp = expected.get(key, Decimal(0))
        act = actual.get(key, Decimal(0))
        if exp != act:
            company, odoo_account, currency = key
            diffs.append(DestinationDiff(company, odoo_account, currency, exp, act))
    return diffs


def verify_counts(
    entries,
    moves,
    *,
    excluded_je_ids: frozenset | set = frozenset(),
) -> list[str]:
    """FR12b: conteo de asientos y líneas preservado, con exclusiones declaradas
    por IDENTIDAD `(company, je_id)` — nunca por conteo ciego (learning del
    review E1.2: un int acepta la exclusión de *cualesquiera* N moves).

    Verifica que (a) exactamente los moves declarados faltan del output — ni uno
    más, ni uno menos —, (b) las líneas cuadran descontando las de los excluidos,
    y (c) el conjunto excluido NETEA A 0 por (company, code, currency) — excluir
    algo que no netea descuadraría el libro ("falla con alarma", AC2 E1.3).
    """
    txns = laudus_transactions(entries)
    problems = []
    mirror: dict[tuple[str, str], object] = {}
    for t in txns:
        if not t.postings:
            continue
        ident = _txn_identity(t)
        # La identidad tiene que ser única y no-vacía: un dict que sobrescribe
        # en silencio dejaría razonar al gate sobre un mirror deduplicado.
        if not ident[1]:
            problems.append(
                f"txn del mirror sin meta `id` ({t.date} {t.narration!r}) — "
                f"identidad vacía, el gate no puede razonar por identidad"
            )
            continue
        if ident in mirror:
            problems.append(f"identidad DUPLICADA en el mirror: {ident}")
        mirror[ident] = t
    output_ids = {(m.company, m.je_id) for m in moves}
    excluded = set(excluded_je_ids)
    fantasmas = excluded - set(mirror)
    if fantasmas:
        problems.append(
            f"exclusiones declaradas que NO existen en el mirror: {sorted(fantasmas)}"
        )
    presentes = excluded & output_ids
    if presentes:
        problems.append(
            f"exclusiones declaradas pero el move SIGUE en el output: {sorted(presentes)}"
        )
    missing = set(mirror) - output_ids
    no_declaradas = missing - excluded
    if no_declaradas:
        problems.append(
            f"moves del mirror ausentes del output SIN declarar: {sorted(no_declaradas)}"
        )

    n_excluded_postings = sum(
        len(mirror[k].postings) for k in excluded & set(mirror)
    )
    n_postings = sum(len(t.postings) for t in txns)
    n_lines = sum(len(m.lines) for m in moves)
    if n_lines + n_excluded_postings != n_postings:
        problems.append(
            f"líneas: {n_postings} postings en el mirror vs {n_lines} "
            f"transformadas (+{n_excluded_postings} de los {len(excluded)} "
            f"moves excluidos declarados)"
        )

    net: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    codes = account_codes(entries)
    for k in excluded & set(mirror):
        txn = mirror[k]
        for posting in txn.postings:
            code = codes.get(posting.account)
            if not code:
                raise ValueError(
                    f"parity: la cuenta {posting.account!r} no tiene meta `code`"
                )
            entity = entity_of_account(posting.account)
            net[(company_for_entity(entity), code, posting.units.currency)] += (
                posting.units.number
            )
    descuadres = {k: v for k, v in net.items() if v != 0}
    if descuadres:
        problems.append(
            f"el conjunto excluido NO netea a 0 por código (se excluyó una pata "
            f"suelta o un par incompleto): {descuadres}"
        )
    return problems


def run_tier_a(
    entries,
    moves,
    mapping: MappingTable,
    *,
    route=None,
    excluded_je_ids: frozenset | set = frozenset(),
) -> None:
    """El gate Tier A completo (origen + destino + conteos). Levanta
    `ParityError` con el detalle si algo descuadra.

    Contrato de E1 en adelante: TODO transformador nuevo (E1.3, E1.4) termina
    con esta función en verde sobre el golden slice. Las exclusiones (washes de
    E1.3) se declaran por IDENTIDAD (`excluded_je_ids={(company, je_id), …}`);
    `route` compone el ruteo esperado del gate de destino (ver
    `verify_destination` y `sincerar.route_sincerado`).
    """
    problems: list[str] = []
    origin = verify_origin_parity(entries, moves)
    if origin:
        problems.append(f"paridad-origen: {len(origin)} diffs — {origin[:5]}")
    destination = verify_destination(
        entries, moves, mapping, route=route, excluded_je_ids=excluded_je_ids
    )
    if destination:
        problems.append(f"gate destino: {len(destination)} diffs — {destination[:5]}")
    problems.extend(verify_counts(entries, moves, excluded_je_ids=excluded_je_ids))
    if problems:
        raise ParityError("Tier A FAIL:\n  " + "\n  ".join(problems))

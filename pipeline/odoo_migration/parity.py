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
     ninguna fusión/partición silenciosa. Los parámetros `expected_excluded_*`
     existen para E1.3: los washes se excluyen con conteo AUDITADO, declarado
     explícitamente — nunca en silencio.

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


def verify_destination(entries, moves, mapping: MappingTable) -> list[DestinationDiff]:
    """FR12a: Σ por cuenta Odoo destino == Σ de sus códigos origen mapeados.

    El lado esperado se computa desde el MIRROR (no desde las líneas), ruteando
    cada (entity, code) a su destino según la tabla — cruza el output contra la
    fuente, no contra sí mismo.
    """
    codes = account_codes(entries)
    expected: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
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
            row = mapping.get(entity, code)
            key = (row.company, row.odoo_account, posting.units.currency)
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
    expected_excluded_moves: int = 0,
    expected_excluded_lines: int = 0,
) -> list[str]:
    """FR12b: conteo de asientos y líneas preservado (o exclusión DECLARADA)."""
    txns = laudus_transactions(entries)
    n_postings = sum(len(t.postings) for t in txns)
    n_lines = sum(len(m.lines) for m in moves)
    problems = []
    if len(moves) + expected_excluded_moves != len(txns):
        problems.append(
            f"asientos: {len(txns)} en el mirror vs {len(moves)} transformados "
            f"(+{expected_excluded_moves} exclusión declarada)"
        )
    if n_lines + expected_excluded_lines != n_postings:
        problems.append(
            f"líneas: {n_postings} postings en el mirror vs {n_lines} "
            f"transformadas (+{expected_excluded_lines} exclusión declarada)"
        )
    return problems


def run_tier_a(
    entries,
    moves,
    mapping: MappingTable,
    *,
    expected_excluded_moves: int = 0,
    expected_excluded_lines: int = 0,
) -> None:
    """El gate Tier A completo (origen + destino + conteos). Levanta
    `ParityError` con el detalle si algo descuadra.

    Contrato de E1 en adelante: TODO transformador nuevo (E1.3, E1.4) termina
    con esta función en verde sobre el golden slice.
    """
    problems: list[str] = []
    origin = verify_origin_parity(entries, moves)
    if origin:
        problems.append(f"paridad-origen: {len(origin)} diffs — {origin[:5]}")
    destination = verify_destination(entries, moves, mapping)
    if destination:
        problems.append(f"gate destino: {len(destination)} diffs — {destination[:5]}")
    problems.extend(
        verify_counts(
            entries,
            moves,
            expected_excluded_moves=expected_excluded_moves,
            expected_excluded_lines=expected_excluded_lines,
        )
    )
    if problems:
        raise ParityError("Tier A FAIL:\n  " + "\n  ".join(problems))

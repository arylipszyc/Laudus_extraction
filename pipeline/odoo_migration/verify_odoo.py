"""Verificador lado-Odoo (story E1.6) — el gate de release de Epic E1.

El otro lado del espejo del loader (E1.5): lee lo que quedó EN Odoo y lo
compara contra el mirror/cadena. Tres planos, porque la paridad por código es
necesaria pero NO suficiente (lección P1 del review E1.5: el loader ruteaba
182 líneas a la cuenta equivocada y la paridad por código daba 0 diffs igual —
el código viaja correcto aunque la cuenta esté mal):

  1. Paridad ORIGEN (FR8): Σ `amount_currency` por `x_laudus_account_code` ×
     moneda × compañía en Odoo == Σ `units.number` del MIRROR (independiente de
     la cadena — `parity.laudus_balances` tal cual). 0 diffs, al peso.
  2. Gate de DESTINO (FR12): Σ `balance` por cuenta Odoo REAL (`account_id`)
     == Σ(debit−credit) por cuenta de los `MovePayload` — la MISMA fuente que
     el loader escribió. Este plano pesca el ruteo podrido que el plano 1 no ve.
  3. CONTEOS + invariantes (FR12b): identidades `(company, x_laudus_je_id)`
     exactas (ni una más ni una menos, sin duplicados), N líneas, todos
     posteados, 0 líneas con `x_laudus_*` vacíos, y las líneas 211005 en Odoo
     == exactamente las que la cadena emitió (DERIVADO del payload — nunca
     pinnear 0: en el golden son 0 porque el par wash se excluye, pero en la
     historia completa sobreviven 2 patas sin par con Σ = −751.912.981).

Columna por plano, explícito: origen agrega `amount_currency` (para líneas en
moneda compañía Odoo la puebla == debit−credit — verificado E1.5 Tier B);
destino agrega `balance`. Son columnas ALMACENADAS INDEPENDIENTES en Odoo 18
(junto a debit/credit), no derivadas al leer — por eso las mutaciones del
Tier B tocan LA columna que su plano agrega.

Dos capas, patrón de la casa (NFR3): el lado ESPERADO se deriva en Python puro
(Tier A, testeable sin Docker); el lado ODOO se lee vía XML-RPC (`read_group`
agrega server-side — el full history son ~570 códigos × moneda de resultado,
no 57k líneas por el socket) y el diff corre como gate de release Tier B
(`-m odoo`). La asimetría es deliberada: origen = mirror PURO (sin pasar por
la cadena), destino = cadena (lo que el loader debió escribir) — un bug
compartido no puede auto-validarse en el plano 1.

Muestreo dirigido (FR12d): 20 asientos de mayor monto + 20 aleatorios con seed
fija (NFR1: misma selección en cada corrida) → reporte markdown por asiento
(cuenta Odoo real + partner + dims vs payload) para firma de Ary/Valentina.
La FIRMA es humana; este módulo entrega el reporte.

CLI (el gate de release; el full load real es post-E1.6 — gates D-1 + VPS):
    PYTHONUTF8=1 venv/Scripts/python.exe -m pipeline.odoo_migration.verify_odoo \
        --db test_e16 [--url http://localhost:8070] \
        [--ledger ledger/main.beancount] [--out _bmad-output/.../e1-6-muestreo.md] \
        [--full]  # release: exige el pin FR12c del sinceramiento (exit 1 si no)

Además de los 3 planos Odoo, el CLI corre el gate Tier A (`run_tier_a`) sobre
el ledger VIVO — exclusiones por identidad + neteo a 0 del conjunto excluido —
porque los planos 2/3 comparan payload↔Odoo (misma cadena en ambos lados) y una
exclusión equivocada que netea a 0 por código sería invisible sin él.
"""

import argparse
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from pipeline.odoo_migration.loader_rpc import XMLID_MODULE, OdooClient
from pipeline.odoo_migration.parity import (
    ParityDiff,
    ParityError,
    laudus_balances,
    run_tier_a,
)

#: Parámetros del muestreo dirigido, PINNEADOS (readiness report 2026-07-24,
#: ítem 2 + NFR1): misma selección en cada corrida. La seed es un literal a
#: propósito — cambiarla cambia la muestra firmada.
MUESTREO_SEED = 20260723
MUESTREO_N_TOP = 20
MUESTREO_N_RANDOM = 20

#: Δ ingreso del sinceramiento sobre el mirror COMPLETO al corte (FR12c,
#: `test_sinceramiento_full_mirror.py`): DIRECCIONAL, `pre − post`. Un
#: `post − pre` natural da +45.576B y falla.
SINCERAMIENTO_DELTA_FULL = Decimal("-45576501123")

DEFAULT_URL = "http://localhost:8070"
DEFAULT_GOLDEN = "pipeline/odoo_migration/tests/fixtures/golden_slice.beancount"
DEFAULT_OUT = "_bmad-output/implementation-artifacts/e1-6-muestreo.md"

#: Código Laudus del invariante estructural #4 (winston §6): las líneas de la
#: cuenta de apertura/cierre en Odoo == exactamente las que la cadena emitió.
CODIGO_APERTURA = "211005"


# ---------------------------------------------------------------------------
# Lado ESPERADO (Tier A, Python puro)
# ---------------------------------------------------------------------------

#: Plano 1 — el lado esperado de la paridad-origen ES el agrupador de E1.2
#: TAL CUAL (mismo (company, code, currency) que ya dio 0 diffs en el Tier B
#: de E1.5). NO se escribe otro agregador: el punto es comparar Odoo contra el
#: MIRROR puro, sin pasar por la cadena.
expected_origin = laudus_balances


def expected_destination(payloads) -> dict[tuple[str, str], Decimal]:
    """Plano 2 — Σ(debit−credit) por `(company, account_xmlid)` desde los
    `MovePayload` de `build_moves`: la MISMA fuente que el loader escribe
    (sinceramiento E1.3 incluido — las cuentas `accs_*` de origen están acá).
    Este es el plano que pesca el ruteo podrido (lección P1)."""
    balances: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for move in payloads:
        for line in move.lines:
            balances[(move.company, line.account_xmlid)] += line.debit - line.credit
    return dict(balances)


@dataclass(frozen=True)
class ExpectedCounts:
    """Plano 3 — lo que el payload dice que debe haber en Odoo."""

    n_moves: int
    n_lines: int
    identities: frozenset  # {(company, x_laudus_je_id)}
    #: (n líneas, Σ debit−credit) del código 211005 — DERIVADO del payload,
    #: nunca pinneado (en el full history sobreviven 2 patas sin par).
    lines_211005: tuple


def expected_counts(payloads) -> ExpectedCounts:
    n_211005 = 0
    sum_211005 = Decimal(0)
    for move in payloads:
        for line in move.lines:
            if line.x_laudus_account_code == CODIGO_APERTURA:
                n_211005 += 1
                sum_211005 += line.debit - line.credit
    return ExpectedCounts(
        n_moves=len(payloads),
        n_lines=sum(len(m.lines) for m in payloads),
        identities=frozenset((m.company, m.x_laudus_je_id) for m in payloads),
        lines_211005=(n_211005, sum_211005),
    )


def sinceramiento_check(moves) -> tuple[Decimal, dict[tuple[str, str], Decimal]]:
    """AC2 — el resultado del sinceramiento, derivado de las LÍNEAS ruteadas
    (`line.odoo_account` ≠ colapso), NO de totales por cuenta (una cuenta
    destino de tabla también recibe líneas no-sinceradas).

    Devuelve `(delta, por_destino)`: `delta` es el Δ ingreso CLP DIRECCIONAL
    `pre − post` (la expresión EXACTA del gate FR12c — sobre el mirror completo
    al corte da `SINCERAMIENTO_DELTA_FULL`); `por_destino` es Σ CLP ruteado por
    `(company, cuenta destino)`. Ojo: Molco FFCC (+2.895.757.384) va a GASTO,
    no a activo (pin E1.3) — "activos de origen" del AC es shorthand del epic.
    """
    from pipeline.odoo_migration.mapping import company_for_entity

    delta = Decimal(0)
    por_destino: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for move in moves:
        for line in move.lines:
            if (
                line.sinc_naturaleza
                and line.odoo_account != line.odoo_account_colapso
                and line.odoo_account_colapso.startswith("Income:")
            ):
                if line.currency != "CLP":
                    # Nunca en silencio: el Δ FR12c es CLP; una pata sincerada
                    # no-CLP es un caso nuevo que subestimaría el Δ sin aviso.
                    raise RuntimeError(
                        f"sinceramiento_check: pata sincerada no-CLP "
                        f"({line.entity!r}, {line.laudus_code!r}, "
                        f"{line.currency!r}) — caso sin contemplar, el Δ FR12c "
                        f"se calcula en CLP"
                    )
                delta += line.amount
                por_destino[
                    (company_for_entity(line.entity), line.odoo_account)
                ] += line.amount
    return delta, dict(por_destino)


# ---------------------------------------------------------------------------
# Diffs (puros — comparan dicts; el Tier A los testea sin Odoo)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OdooDestinationDiff:
    """Un descuadre del gate de destino en (company, account_xmlid).

    `expected` = Σ(debit−credit) del payload; `actual` = Σ balance en Odoo.
    Sin moneda: `balance` es SIEMPRE moneda compañía (CLP)."""

    company: str
    account_xmlid: str
    expected: Decimal
    actual: Decimal

    @property
    def diff(self) -> Decimal:
        return self.expected - self.actual


def diff_origin(expected: dict, odoo: dict) -> list[ParityDiff]:
    """Plano 1: mirror vs Odoo por (company, code, currency). Un código
    ausente en Odoo con saldo mirror 0 es OK (washes excluidos netean a 0);
    ausente con saldo ≠ 0 es diff — nada se pierde en silencio.

    Ambos lados se comparan a 2 decimales: Odoo redondea `amount_currency` a
    la precisión de la moneda al escribir (`loader_rpc._f`) — un monto no-CLP
    del mirror con más decimales daría diff fantasma si se comparara exacto.
    HALF_UP = el redondeo de `float_round` de Odoo."""
    diffs = []
    for key in sorted(set(expected) | set(odoo)):
        lado_mirror = expected.get(key, Decimal(0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        lado_odoo = odoo.get(key, Decimal(0))
        if lado_mirror != lado_odoo:
            company, code, currency = key
            diffs.append(ParityDiff(company, code, currency, lado_mirror, lado_odoo))
    return diffs


def diff_destination(
    expected: dict, odoo_by_account_id: dict, xmlids_by_res_id: dict
) -> list[OdooDestinationDiff]:
    """Plano 2: payload vs Odoo por cuenta REAL. El lado Odoo viene agrupado
    por `account_id`; se resuelve a xmlid vía `ir.model.data` del namespace
    `__laudus__` (los alias N→1 del chart apuntan al mismo `res_id` — se
    matchea contra el REPRESENTANTE que emite `build_moves`). Una cuenta con
    saldo y sin xmlid del namespace es diff (nadie más escribe en esta db)."""
    actual: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for (company, account_id), amount in odoo_by_account_id.items():
        names = xmlids_by_res_id.get(account_id, ())
        representantes = [x for x in names if (company, x) in expected]
        if representantes:
            key = (company, representantes[0])
        elif names:
            key = (company, min(names))
        else:
            key = (company, f"account_id={account_id} (sin xmlid {XMLID_MODULE})")
        actual[key] += amount

    diffs = []
    for key in sorted(set(expected) | set(actual)):
        exp = expected.get(key, Decimal(0))
        act = actual.get(key, Decimal(0))
        if exp != act:
            company, xmlid = key
            diffs.append(OdooDestinationDiff(company, xmlid, exp, act))
    return diffs


@dataclass(frozen=True)
class OdooCounts:
    """Plano 3 — lo que hay en Odoo (crudo, con duplicados si los hay)."""

    identities: tuple  # ((company, x_laudus_je_id), …) de TODOS los moves
    n_lines: int
    non_posted: tuple  # identidades con state != posted
    incomplete_lines: int  # líneas con algún x_laudus_* vacío
    lines_211005: tuple  # (n líneas, Σ balance) del código 211005


def diff_counts(expected: ExpectedCounts, odoo: OdooCounts) -> list[str]:
    """Plano 3: identidades exactas + invariantes estructurales."""
    problems = []
    dupes = sorted(k for k, n in Counter(odoo.identities).items() if n > 1)
    if dupes:
        problems.append(
            f"conteos: {len(dupes)} identidades (company, x_laudus_je_id) "
            f"DUPLICADAS en Odoo — {dupes[:5]}"
        )
    odoo_ids = set(odoo.identities)
    missing = sorted(expected.identities - odoo_ids)
    if missing:
        problems.append(
            f"conteos: {len(missing)} moves del payload AUSENTES en Odoo — "
            f"{missing[:5]}"
        )
    extra = sorted(odoo_ids - expected.identities)
    if extra:
        problems.append(
            f"conteos: {len(extra)} moves en Odoo que el payload NO emitió — "
            f"{extra[:5]}"
        )
    if odoo.n_lines != expected.n_lines:
        problems.append(
            f"conteos: {odoo.n_lines} líneas en Odoo vs {expected.n_lines} "
            f"del payload"
        )
    if odoo.non_posted:
        problems.append(
            f"conteos: {len(odoo.non_posted)} moves NO posteados — "
            f"{sorted(odoo.non_posted)[:5]}"
        )
    if odoo.incomplete_lines:
        problems.append(
            f"conteos: {odoo.incomplete_lines} líneas con x_laudus_* vacíos "
            f"(trazabilidad FR5 rota)"
        )
    if odoo.lines_211005 != expected.lines_211005:
        problems.append(
            f"conteos: líneas {CODIGO_APERTURA} en Odoo {odoo.lines_211005} "
            f"vs payload {expected.lines_211005} (esperado DERIVADO del "
            f"payload — en el full history sobreviven 2 patas sin par)"
        )
    return problems


# ---------------------------------------------------------------------------
# Lector Odoo (XML-RPC — reusa OdooClient de loader_rpc; cero deps nuevas)
# ---------------------------------------------------------------------------


def _dec(value) -> Decimal:
    """Agregado XML-RPC (float) → Decimal a 2 decimales ANTES de comparar
    contra 0 exacto — el ruido binario en centavos crearía diffs fantasma."""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


class OdooReader:
    """Capa fina de LECTURA sobre `OdooClient`. Context `allowed_company_ids`
    SIEMPRE (las 2 compañías) — sin él, Odoo filtra por la compañía activa del
    usuario y el verificador vería medio libro."""

    def __init__(self, client: OdooClient):
        self.client = client
        rows = client.execute("res.company", "search_read", [], fields=["name"])
        companies = {r["name"]: r["id"] for r in rows}
        missing = {"EAG", "RUT2"} - set(companies)
        if missing:
            raise RuntimeError(
                f"verify: faltan las compañías {sorted(missing)!r} en la db — "
                f"¿se instaló x_laudus_migration? (el hook de E1.1 las crea)"
            )
        self._ctx = {"allowed_company_ids": sorted(companies.values())}

    def _read_group(self, model, domain, fields, groupby):
        return self.client.execute(
            model, "read_group", domain, fields, groupby,
            lazy=False, context=self._ctx,
        )

    def origin_balances(self) -> dict[tuple[str, str, str], Decimal]:
        """Plano 1: Σ `amount_currency` por (company, code, currency). Para
        líneas en moneda compañía Odoo puebla `amount_currency == debit−credit`
        (verificado E1.5 Tier B) — un solo agrupador sirve para ambas monedas.
        `x_laudus_account_code` está indexado (E1.1): es la query más caliente
        del sistema (winston §4)."""
        out: dict[tuple[str, str, str], Decimal] = {}
        for g in self._read_group(
            "account.move.line",
            [],
            ["amount_currency:sum"],
            ["x_laudus_account_code", "currency_id", "company_id"],
        ):
            code, currency, company = (
                g["x_laudus_account_code"], g["currency_id"], g["company_id"],
            )
            if not code or not currency or not company:
                raise RuntimeError(
                    f"verify: grupo de paridad con campo vacío (code={code!r}, "
                    f"currency={currency!r}, company={company!r}) — hay líneas "
                    f"sin trazabilidad en la db; el plano 1 no puede razonar "
                    f"por código sobre ellas"
                )
            out[(company[1], code, currency[1])] = _dec(g.get("amount_currency"))
        return out

    def destination_balances(self) -> dict[tuple[str, int], Decimal]:
        """Plano 2: Σ `balance` por (company, account_id). `balance` es columna
        ALMACENADA (debit−credit en moneda compañía) — la que una línea movida
        de cuenta re-agrupa."""
        out: dict[tuple[str, int], Decimal] = {}
        for g in self._read_group(
            "account.move.line", [], ["balance:sum"], ["account_id", "company_id"]
        ):
            account, company = g["account_id"], g["company_id"]
            if not account or not company:
                raise RuntimeError(
                    f"verify: grupo de destino con campo vacío "
                    f"(account={account!r}, company={company!r})"
                )
            out[(company[1], account[0])] = _dec(g.get("balance"))
        return out

    def account_xmlids(self) -> dict[int, tuple]:
        """{res_id: (nombres xmlid, …)} de las cuentas del namespace
        `__laudus__` — una query; los alias N→1 del chart vuelven juntos."""
        rows = self.client.execute(
            "ir.model.data", "search_read",
            [("module", "=", XMLID_MODULE), ("model", "=", "account.account")],
            fields=["name", "res_id"],
        )
        by_res: dict[int, list] = defaultdict(list)
        for r in rows:
            by_res[r["res_id"]].append(r["name"])
        return {res_id: tuple(sorted(names)) for res_id, names in by_res.items()}

    def counts(self) -> OdooCounts:
        """Plano 3: identidades + estados + invariantes estructurales."""
        moves = self.client.execute(
            "account.move", "search_read", [],
            fields=["x_laudus_je_id", "company_id", "state"],
            context=self._ctx,
        )
        identities = tuple(
            sorted((m["company_id"][1], str(m["x_laudus_je_id"] or "")) for m in moves)
        )
        non_posted = tuple(
            sorted(
                (m["company_id"][1], str(m["x_laudus_je_id"] or ""))
                for m in moves
                if m["state"] != "posted"
            )
        )
        n_lines = self.client.execute(
            "account.move.line", "search_count", [], context=self._ctx
        )
        incomplete = self.client.execute(
            "account.move.line", "search_count",
            ["|", "|",
             ("x_laudus_account_code", "in", [False, ""]),
             ("x_laudus_je_id", "in", [False, ""]),
             ("x_laudus_entity", "in", [False, ""])],
            context=self._ctx,
        )
        apertura = self.client.execute(
            "account.move.line", "search_read",
            [("x_laudus_account_code", "=", CODIGO_APERTURA)],
            fields=["balance"], context=self._ctx,
        )
        return OdooCounts(
            identities=identities,
            n_lines=n_lines,
            non_posted=non_posted,
            incomplete_lines=incomplete,
            lines_211005=(
                len(apertura),
                sum((_dec(r["balance"]) for r in apertura), Decimal(0)),
            ),
        )

    def sample_lines(self, sample) -> dict[str, list]:
        """Líneas REALES en Odoo de los moves del muestreo, por move xmlid.
        La cuenta/partner/dims/montos del reporte salen de ACÁ (leídos de
        Odoo, no del payload) — esa es la gracia del muestreo.

        Cada fila lleva su xmlid `aml_*` en la clave `"xmlid"` (o None si la
        línea no tiene xmlid del namespace): el reporte parea payload↔Odoo por
        IDENTIDAD, no por posición — un pareo posicional cruzaría las filas del
        documento firmado si el orden de ids no coincide con el de emisión."""
        wanted = {m.xmlid for m in sample}
        rows = self.client.execute(
            "ir.model.data", "search_read",
            [("module", "=", XMLID_MODULE), ("model", "=", "account.move"),
             ("name", "in", sorted(wanted))],
            fields=["name", "res_id"],
        )
        id_to_xmlid = {r["res_id"]: r["name"] for r in rows}
        missing = wanted - set(id_to_xmlid.values())
        if missing:
            raise RuntimeError(
                f"verify: moves del muestreo sin xmlid en Odoo (¿no cargados?): "
                f"{sorted(missing)[:5]}"
            )
        lines = self.client.execute(
            "account.move.line", "search_read",
            [("move_id", "in", sorted(id_to_xmlid))],
            fields=["move_id", "account_id", "x_laudus_account_code", "debit",
                    "credit", "amount_currency", "currency_id", "partner_id",
                    "analytic_distribution", "name"],
            order="move_id, id",
            context=self._ctx,
        )
        aml_rows = self.client.execute(
            "ir.model.data", "search_read",
            [("module", "=", XMLID_MODULE),
             ("model", "=", "account.move.line"),
             ("res_id", "in", [l["id"] for l in lines])],
            fields=["name", "res_id"],
        )
        aml_by_line_id = {r["res_id"]: r["name"] for r in aml_rows}
        out: dict[str, list] = {x: [] for x in wanted}
        for line in lines:
            line["xmlid"] = aml_by_line_id.get(line["id"])
            out[id_to_xmlid[line["move_id"][0]]].append(line)
        return out

    def analytic_names(self) -> dict[str, str]:
        """{str(id): nombre} de las cuentas analíticas — para volcar
        `analytic_distribution` (keyed por id) legible en el reporte."""
        rows = self.client.execute(
            "account.analytic.account", "search_read", [], fields=["name"],
            context=self._ctx,
        )
        return {str(r["id"]): r["name"] for r in rows}


# ---------------------------------------------------------------------------
# Orquestación: los 3 planos contra Odoo
# ---------------------------------------------------------------------------


def verify(reader: OdooReader, entries, payloads) -> None:
    """El gate completo. `ParityError` con diffs programáticos si descuadra.

    `entries` = el mirror (plano 1, independiente de la cadena);
    `payloads` = `build_moves(...)` (planos 2 y 3 — lo que el loader escribió).
    """
    origin = diff_origin(expected_origin(entries), reader.origin_balances())
    destination = diff_destination(
        expected_destination(payloads),
        reader.destination_balances(),
        reader.account_xmlids(),
    )
    counts = diff_counts(expected_counts(payloads), reader.counts())

    problems = []
    if origin:
        problems.append(f"paridad-origen: {len(origin)} diffs — {origin[:5]}")
    if destination:
        problems.append(f"gate destino: {len(destination)} diffs — {destination[:5]}")
    problems.extend(counts)
    if problems:
        raise ParityError(
            "Verificación lado-Odoo FAIL:\n  " + "\n  ".join(problems),
            origin_diffs=origin,
            destination_diffs=destination,
            count_diffs=counts,
        )


# ---------------------------------------------------------------------------
# Muestreo dirigido (FR12d) + reporte para firma
# ---------------------------------------------------------------------------


def select_sample(
    payloads,
    *,
    n_top: int = MUESTREO_N_TOP,
    n_random: int = MUESTREO_N_RANDOM,
    seed: int = MUESTREO_SEED,
) -> list:
    """Selección determinística: `n_top` moves de mayor Σ debit + `n_random`
    aleatorios con seed fija sobre el resto (si un move está en ambos grupos,
    el aleatorio toma el siguiente — `sample` sin reposición sobre el pool ya
    depurado). Misma selección en cada corrida (NFR1)."""

    def magnitude(move) -> Decimal:
        return sum((line.debit for line in move.lines), Decimal(0))

    ordered = sorted(payloads, key=lambda m: (-magnitude(m), m.xmlid))
    top = ordered[:n_top]
    top_ids = {m.xmlid for m in top}
    pool = sorted(
        (m for m in payloads if m.xmlid not in top_ids), key=lambda m: m.xmlid
    )
    rng = random.Random(seed)
    rand = rng.sample(pool, min(n_random, len(pool)))
    return top + rand


def glosa_histogram(refs) -> list[tuple[str, int]]:
    """Histograma por-glosa (winston §6·B.4): agrupa `LineRef.desc` por glosa
    NORMALIZADA y cuenta. No recalcula clasificación — es una agregación de
    data que ya viaja en los reportes de la cadena."""
    from pipeline.odoo_migration.sincerar import normalize

    counter: Counter = Counter(normalize(r.desc) or "(glosa vacía)" for r in refs)
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def _cell(value) -> str:
    """Texto crudo (glosa Laudus, partner, nombre de cuenta) → celda markdown:
    un `|` o salto de línea sin escapar correría las columnas del documento
    que se firma."""
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _aid_key(aid) -> tuple:
    """Orden NUMÉRICO de ids analíticos ("10" después de "3"; las keys de
    `analytic_distribution` son strings, a veces "3,7")."""
    parts = str(aid).split(",")
    return ([int(p) for p in parts if p.strip().isdigit()], str(aid))


def _fmt_dims(distribution, analytic_names: dict) -> str:
    if not distribution:
        return "—"
    parts = []
    for aid, pct in sorted(distribution.items(), key=lambda kv: _aid_key(kv[0])):
        name = analytic_names.get(str(aid), f"id={aid}")
        parts.append(name if pct == 100 else f"{name} ({pct}%)")
    return ", ".join(parts)


def build_muestreo_report(
    sample,
    odoo_lines_by_move: dict,
    *,
    analytic_names: dict | None = None,
    sinc_report=None,
    dim_report=None,
) -> str:
    """Reporte markdown del muestreo para firma humana. DETERMINÍSTICO: sin
    timestamps ni orden dependiente de ids de db — dos corridas sobre el mismo
    estado producen el MISMO archivo (NFR1; el Tier B lo verifica)."""
    analytic_names = analytic_names or {}
    out = [
        "# E1.6 — Muestreo dirigido (FR12d) para firma",
        "",
        f"Selección determinística: {MUESTREO_N_TOP} asientos de mayor monto + "
        f"{MUESTREO_N_RANDOM} aleatorios (seed {MUESTREO_SEED}, pinneada). "
        f"Moves en la muestra: **{len(sample)}**.",
        "",
        "Las columnas *Odoo* están LEÍDAS de Odoo (cuenta, montos, partner, "
        "dims — no del payload); las *esperado* salen del payload de la "
        "cadena. Cada línea se parea por su identidad `aml_*`, no por "
        "posición. Revisar cada asiento a mano contra Laudus (cuenta + "
        "partner + dimensión) y firmar al pie.",
        "",
    ]
    header = (
        "| # | código | cuenta esperada (payload) | cuenta Odoo (real) | "
        "debit (esperado / Odoo) | credit (esperado / Odoo) | moneda | "
        "partner (esperado / Odoo) | dims (Odoo) |"
    )
    divider = ("|---|--------|---------------------------|--------------------|"
               "------------------------|-------------------------|--------|"
               "---------------------------|-------------|")
    for move in sample:
        out.append(
            f"## {move.xmlid} — {move.company} · JE {move.x_laudus_je_id} · "
            f"{move.date.isoformat()}"
        )
        out.append("")
        out.append(f"Glosa: {_cell(move.ref) if move.ref else '(sin glosa)'}")
        out.append("")
        out.append(header)
        out.append(divider)
        odoo_rows = odoo_lines_by_move.get(move.xmlid, [])
        row_by_xmlid = {r["xmlid"]: r for r in odoo_rows if r.get("xmlid")}
        matched = set()
        for n, payload_line in enumerate(move.lines):
            row = row_by_xmlid.get(payload_line.xmlid)
            if row is None:
                cuenta_odoo, partner_odoo, dims, moneda = (
                    "⚠️ LÍNEA AUSENTE", "—", "—", "—",
                )
                debit_odoo = credit_odoo = "—"
            else:
                matched.add(payload_line.xmlid)
                cuenta_odoo = (
                    _cell(row["account_id"][1]) if row["account_id"]
                    else "⚠️ sin cuenta"
                )
                partner_odoo = (
                    _cell(row["partner_id"][1]) if row["partner_id"] else "—"
                )
                dims = _cell(
                    _fmt_dims(row.get("analytic_distribution"), analytic_names)
                )
                moneda = row["currency_id"][1] if row["currency_id"] else "—"
                if row["currency_id"] and row["currency_id"][1] != "CLP":
                    moneda += f" ({row['amount_currency']})"
                debit_odoo = _dec(row["debit"])
                credit_odoo = _dec(row["credit"])
            partner_esp = _cell(payload_line.partner_xmlid) if payload_line.partner_xmlid else "—"
            out.append(
                f"| {n} | {payload_line.x_laudus_account_code} | "
                f"{payload_line.account_xmlid} | {cuenta_odoo} | "
                f"{payload_line.debit} / {debit_odoo} | "
                f"{payload_line.credit} / {credit_odoo} | {moneda} | "
                f"{partner_esp} / {partner_odoo} | {dims} |"
            )
        extras = [
            r for r in odoo_rows
            if not r.get("xmlid") or r["xmlid"] not in matched
        ]
        if extras:
            out.append("")
            out.append(
                f"⚠️ Odoo tiene {len(extras)} línea(s) que el payload NO "
                f"emitió (lo sospechoso, a la vista del firmante):"
            )
            out.append("")
            out.append("| xmlid | código | cuenta Odoo | debit | credit | partner | dims |")
            out.append("|-------|--------|-------------|-------|--------|---------|------|")
            for r in extras:
                out.append(
                    f"| {r.get('xmlid') or '(sin xmlid)'} | "
                    f"{r.get('x_laudus_account_code') or '—'} | "
                    f"{_cell(r['account_id'][1]) if r['account_id'] else '—'} | "
                    f"{_dec(r['debit'])} | {_dec(r['credit'])} | "
                    f"{_cell(r['partner_id'][1]) if r['partner_id'] else '—'} | "
                    f"{_cell(_fmt_dims(r.get('analytic_distribution'), analytic_names))} |"
                )
        out.append("")

    out += [
        "## Firma",
        "",
        "| Revisor | Resultado (OK / observaciones) | Fecha | Firma |",
        "|---------|--------------------------------|-------|-------|",
        "| Ary |  |  |  |",
        "| Valentina |  |  |  |",
        "",
    ]

    # Anexo de cobertura de glosa (winston §6·B): adjunta los reportes que la
    # cadena YA emite — no recalcula nada.
    if sinc_report is not None or dim_report is not None:
        out += ["## Anexo — Cobertura de glosa (winston §6·B)", ""]
        if sinc_report is not None:
            out += [f"- {sinc_report.resumen()}"]
        if dim_report is not None:
            out += [f"- {dim_report.resumen()}"]
        out.append("")
        if sinc_report is not None and sinc_report.sin_clasificar:
            out += [
                "### Histograma por glosa — patas MIXTO `sin clasificar` (E1.3)",
                "",
                "| glosa (normalizada) | patas |",
                "|---------------------|-------|",
            ]
            out += [
                f"| {_cell(glosa)} | {n} |"
                for glosa, n in glosa_histogram(sinc_report.sin_clasificar)
            ]
            out.append("")
        if dim_report is not None and dim_report.sin_match:
            out += [
                "### Glosas sin match del dimensionado (E1.4 — listado sign-off AC5)",
                "",
                "| company | je_id | código | glosa | regla |",
                "|---------|-------|--------|-------|-------|",
            ]
            out += [
                f"| {r.company} | {r.je_id} | {r.code} | {_cell(r.desc)} | "
                f"{_cell(r.regla)} |"
                for r in dim_report.sin_match
            ]
            out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI — el gate de release
# ---------------------------------------------------------------------------


def _chain_with_reports(ledger_path: str, table):
    """Cadena completa + los reportes de cobertura que el anexo adjunta.
    (`loader_rpc.run_chain` devuelve solo los moves — acá se necesitan también
    los reportes de `sincerar`/`dimensionar` y los aliases para el gate Tier A
    del mirror.)"""
    from beancount import loader as bc_loader

    from pipeline.odoo_migration.dimensionar import dimensionar
    from pipeline.odoo_migration.sincerar import load_alias_table, sincerar
    from pipeline.odoo_migration.transform import collapse

    entries, errors, _ = bc_loader.load_file(ledger_path)
    if errors:
        raise RuntimeError(f"verify: el ledger {ledger_path!r} tiene {len(errors)} errores")
    aliases = load_alias_table()
    moves = collapse(entries, table)
    sinc = sincerar(moves, table, alias_table=aliases)
    dim = dimensionar(sinc.moves, table, alias_table=aliases)
    return entries, aliases, sinc, dim


def main(argv=None) -> int:
    import os

    from pipeline.odoo_migration.load import (
        build_chart,
        build_moves,
        build_origin_accounts,
    )
    from pipeline.odoo_migration.mapping import load_mapping_table
    from pipeline.odoo_migration.sincerar import route_sincerado

    parser = argparse.ArgumentParser(
        description="Verificador lado-Odoo (E1.6): paridad origen + destino + "
        "conteos + muestreo dirigido. Default: golden slice contra el compose "
        "migration_e1."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--db", required=True)
    parser.add_argument("--login", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--ledger", default=DEFAULT_GOLDEN)
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="ruta del reporte de muestreo (markdown)")
    parser.add_argument(
        "--full", action="store_true",
        help="declara que --ledger es el mirror COMPLETO al corte: el pin "
        "FR12c del sinceramiento pasa de informativo a GATE (delta distinto "
        "del pin = exit 1). Usar en la corrida de release del full load.",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.ledger):
        parser.error(f"--ledger {args.ledger!r} no existe (¿ruta desde la raíz del repo?)")

    table = load_mapping_table()
    entries, aliases, sinc, dim = _chain_with_reports(args.ledger, table)
    chart = build_chart(table) + build_origin_accounts(dim.moves, table)
    payloads = build_moves(dim.moves, chart)

    client = OdooClient(args.url, args.db, args.login, args.password)
    reader = OdooReader(client)

    delta, por_destino = sinceramiento_check(dim.moves)
    if args.full and delta != SINCERAMIENTO_DELTA_FULL:
        print(
            f"FAIL: --full pero delta del sinceramiento = {delta} != pin "
            f"FR12c {SINCERAMIENTO_DELTA_FULL} (pre - post, direccional)"
        )
        return 1

    exp_counts = expected_counts(payloads)
    try:
        # Gate Tier A sobre el ledger VIVO (no solo el test congelado al
        # corte): exclusiones por identidad + neteo a 0 del conjunto excluido.
        # Sin esto, una exclusión equivocada que netea a 0 por código sería
        # invisible a los 3 planos Odoo (payload y Odoo comparten la cadena).
        run_tier_a(
            entries,
            dim.moves,
            table,
            route=route_sincerado(table, aliases),
            excluded_je_ids=sinc.excluded_je_ids,
        )
        verify(reader, entries, payloads)
    except ParityError as exc:
        print(exc)
        print(
            f"diffs programáticos: origen={len(exc.origin_diffs)} "
            f"destino={len(exc.destination_diffs)} conteos={len(exc.count_diffs)}"
        )
        return 1
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1

    print(
        f"OK: 0 diffs en los 3 planos — {exp_counts.n_moves} asientos / "
        f"{exp_counts.n_lines} líneas verificados contra {args.db}"
    )
    print(
        f"sinceramiento: delta ingreso (pre - post) = {delta} sobre "
        f"{len(por_destino)} cuentas destino"
        + (
            "  [== pin FR12c del mirror completo, gate --full]"
            if args.full
            else "  [sin --full: pin FR12c no exigido — usarlo en el release]"
        )
    )

    try:
        sample = select_sample(payloads)
        report = build_muestreo_report(
            sample,
            reader.sample_lines(sample),
            analytic_names=reader.analytic_names(),
            sinc_report=sinc.report,
            dim_report=dim.report,
        )
    except RuntimeError as exc:
        print(f"FAIL muestreo: {exc}")
        return 1
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(report)
    print(f"muestreo dirigido ({len(sample)} asientos) -> {args.out} (firma pendiente)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

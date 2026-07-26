"""Tier B (opt-in) — E1.6: el verificador contra Odoo REAL (AC1–AC4).

NO corre por-commit (marcado `@pytest.mark.odoo`, saltado por el conftest).
Requiere Docker. Levanta el compose propio (`migration_e1`, puerto 8070),
instala `x_laudus_migration` en una db fresca (`test_e16`), CARGA el golden
con el loader de E1.5 (`load_all`, import directo) y verifica:

  - Gate verde: 0 diffs en los 3 planos (paridad origen por código × moneda ×
    compañía, destino por cuenta Odoo REAL incluidas las 5 `accs_*` de
    Tecnión, conteos 5/18).
  - MUTACIONES contra Odoo real (la razón de ser del Tier B — un gate que no
    puede fallar es `tsc --noEmit`). Cada mutación toca LA COLUMNA QUE SU
    PLANO AGREGA: debit/credit/balance/amount_currency son 4 columnas
    ALMACENADAS independientes en Odoo 18 — un `UPDATE … SET debit` no mueve
    `amount_currency` ni `balance` y NINGÚN plano lo vería:
      (a) `amount_currency += 1000` → la paridad ORIGEN acusa ese código;
      (b) línea movida de cuenta (`account_id`; el plano destino re-agrupa
          `balance`) → el DESTINO acusa y el origen NO — el plano 2 existe
          exactamente por eso (lección P1 del review E1.5);
      (c) move borrado (draft+unlink, como E1.5) → los CONTEOS acusan.
    Cada mutación se revierte (o se re-carga) antes del siguiente assert.
  - Muestreo dirigido: la selección es estable (2 corridas → mismo archivo).

Las mutaciones SQL van por `_psql` (UPDATE directo — Odoo no permite editar
posted vía ORM, y justamente queremos corromper POR DEBAJO para que el gate
acuse).

Correr:
  PYTHONUTF8=1 venv/Scripts/python.exe -m pytest \
      pipeline/odoo_migration/tests/test_verify_odoo_tier_b.py -m odoo -q

Helpers de compose duplicados de `test_loader_idempotente.py` a propósito
(DB distinta; si se endurece el skip de `up -d`, endurecer todos — defer
E1.0/E1.1 vigente).
"""

import os
import shutil
import subprocess
import time
from decimal import Decimal

import pytest
from beancount import loader as bc_loader

from pipeline.odoo_migration.dimensionar import dimensionar
from pipeline.odoo_migration.load import (
    build_analytic,
    build_chart,
    build_moves,
    build_origin_accounts,
    build_partners,
)
from pipeline.odoo_migration.loader_rpc import XMLID_MODULE, OdooClient, load_all
from pipeline.odoo_migration.mapping import load_mapping_table
from pipeline.odoo_migration.parity import ParityError
from pipeline.odoo_migration.sincerar import load_alias_table, sincerar
from pipeline.odoo_migration.transform import collapse
from pipeline.odoo_migration.verify_odoo import (
    OdooReader,
    build_muestreo_report,
    diff_counts,
    diff_destination,
    diff_origin,
    expected_counts,
    expected_destination,
    expected_origin,
    select_sample,
    verify,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
COMPOSE = os.path.join(REPO, "pipeline", "odoo_migration", "docker-compose.yml")
FIXTURE = os.path.join(REPO, "pipeline", "odoo_migration", "tests", "fixtures",
                       "golden_slice.beancount")
PROJECT = "migration_e1"
DB = "test_e16"
URL = "http://localhost:8070"

pytestmark = pytest.mark.odoo


def _compose(*args, timeout=600):
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", COMPOSE, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _psql(sql):
    res = _compose("exec", "-T", "db", "psql", "-U", "odoo", "-d", DB, "-tA", "-c", sql)
    assert res.returncode == 0, f"psql falló: {res.stderr}\n{res.stdout}"
    return res.stdout.strip()


def _wait_for_db(timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _compose("exec", "-T", "db", "pg_isready", "-U", "odoo").returncode == 0:
            return
        time.sleep(2)
    pytest.fail(f"Postgres no estuvo listo en {timeout}s")


def _wait_for_odoo(timeout=120):
    """El server HTTP tarda en subir tras el install --stop-after-init."""
    import xmlrpc.client

    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common").version()
            return
        except Exception as exc:  # noqa: BLE001 — poll de arranque
            last = exc
            time.sleep(2)
    pytest.fail(f"Odoo no respondió en {URL} tras {timeout}s: {last}")


def _res_id(xmlid):
    """id del record por su xmlid `aml_*`/`mv_*` (para las mutaciones SQL)."""
    out = _psql(
        f"SELECT res_id FROM ir_model_data "
        f"WHERE module = '{XMLID_MODULE}' AND name = '{xmlid}'"
    )
    assert out, f"xmlid {xmlid!r} no existe en ir_model_data (¿golden cambió o carga a medias?)"
    return int(out)


def _payloads():
    """Cadena completa sobre el golden, SIN metadata sintética (el write-path
    de partner/analítica ya lo cubre E1.5; acá el sujeto es el verificador).
    Las patas sinceradas (naturaleza B → `Assets:*:InvTecnion`) vienen REALES."""
    entries, errors, _ = bc_loader.load_file(FIXTURE)
    assert errors == []
    table = load_mapping_table()
    aliases = load_alias_table()
    moves = collapse(entries, table)
    sinc = sincerar(moves, table, alias_table=aliases)
    dim = dimensionar(sinc.moves, table, alias_table=aliases)

    chart = build_chart(table) + build_origin_accounts(dim.moves, table)
    partners = build_partners(dim.moves)
    analytic = build_analytic(dim.moves)
    payloads = build_moves(dim.moves, chart)
    return entries, sinc, dim, (chart, partners, analytic, payloads)


@pytest.fixture(scope="module")
def loaded():
    """Stack arriba + módulo instalado en db fresca + golden CARGADO (E1.5).

    Devuelve (client, reader, entries, sinc, dim, payload_tuple).
    """
    if shutil.which("docker") is None:
        pytest.skip("docker no está en el PATH")
    try:
        up = _compose("up", "-d")
        if up.returncode != 0:
            pytest.skip(f"no se pudo levantar el stack (¿daemon Docker abajo?): {up.stderr}")
        _wait_for_db()
        drop = _compose("exec", "-T", "db", "dropdb", "-U", "odoo", "--if-exists", DB)
        assert drop.returncode == 0, f"dropdb {DB} falló: {drop.stderr}"
        install = _compose(
            "exec", "-T", "odoo",
            "odoo", "-d", DB, "--stop-after-init",
            "-i", "x_laudus_migration",
            "--without-demo", "all",
            timeout=600,
        )
        if install.returncode != 0:
            pytest.fail(f"instalar x_laudus_migration falló:\n{install.stderr[-2000:]}")
        _wait_for_odoo()

        entries, sinc, dim, (chart, partners, analytic, payloads) = _payloads()
        client = OdooClient(URL, DB, "admin", "admin")
        load_all(client, chart, partners, analytic, payloads)
        reader = OdooReader(client)
        yield client, reader, entries, sinc, dim, (chart, partners, analytic, payloads)
    finally:
        _compose("down", "-v")


def _planes(reader, entries, payloads):
    """Los 3 planos por separado (para asseverar cuál acusa y cuál NO)."""
    origin = diff_origin(expected_origin(entries), reader.origin_balances())
    destination = diff_destination(
        expected_destination(payloads),
        reader.destination_balances(),
        reader.account_xmlids(),
    )
    counts = diff_counts(expected_counts(payloads), reader.counts())
    return origin, destination, counts


def test_gate_verde_0_diffs_3_planos(loaded):
    _client, reader, entries, _sinc, _dim, (_c, _p, _a, payloads) = loaded

    verify(reader, entries, payloads)  # no levanta: 0 diffs en los 3 planos

    # El plano destino cubre las 5 cuentas de ORIGEN SINCERADO reales del
    # golden (lección P1) — y en Odoo tienen exactamente el saldo del payload.
    expected = expected_destination(payloads)
    accs_keys = sorted(k for k in expected if k[1].startswith("accs_"))
    assert accs_keys == [
        ("EAG", "accs_eag_assetseaginvtecnion"),
        ("EAG", "accs_eag_assetsjaelinvtecnion"),
        ("EAG", "accs_eag_assetsjeannetteinvtecnion"),
        ("EAG", "accs_eag_assetsjocelyninvtecnion"),
        ("EAG", "accs_eag_assetsjohannainvtecnion"),
    ]
    odoo_dest = diff_destination(
        {k: expected[k] for k in accs_keys},
        reader.destination_balances(),
        reader.account_xmlids(),
    )
    # 0 diffs restringiendo el esperado a las accs_* implicaría diffs en las
    # demás — lo que se assevera es que las accs_* NO aparecen entre ellos.
    assert not [d for d in odoo_dest if d.account_xmlid.startswith("accs_")]

    counts = expected_counts(payloads)
    assert (counts.n_moves, counts.n_lines) == (5, 18)
    odoo_counts = reader.counts()
    assert len(odoo_counts.identities) == 5
    assert odoo_counts.n_lines == 18
    assert odoo_counts.non_posted == ()


def test_mutacion_a_amount_currency_acusa_origen(loaded):
    _client, reader, entries, _sinc, _dim, (_c, _p, _a, payloads) = loaded
    line_id = _res_id("aml_eag_29_0")
    code = _psql(f"SELECT x_laudus_account_code FROM account_move_line WHERE id = {line_id}")

    # Mutación (a): la columna que el plano ORIGEN agrega. Un UPDATE a `debit`
    # no la movería (columnas almacenadas independientes) y ningún plano lo vería.
    _psql(f"UPDATE account_move_line SET amount_currency = amount_currency + 1000 "
          f"WHERE id = {line_id}")
    try:
        origin, destination, counts = _planes(reader, entries, payloads)
        assert [d.code for d in origin] == [code]
        assert origin[0].diff == Decimal("-1000.00")  # mirror − odoo
        # `balance` no se tocó: el destino NO acusa; los conteos tampoco.
        assert destination == []
        assert counts == []
        # El gate completo levanta ParityError con los diffs programáticos.
        with pytest.raises(ParityError) as exc_info:
            verify(reader, entries, payloads)
        assert [d.code for d in exc_info.value.origin_diffs] == [code]
    finally:
        _psql(f"UPDATE account_move_line SET amount_currency = amount_currency - 1000 "
              f"WHERE id = {line_id}")

    verify(reader, entries, payloads)  # revertido: verde de nuevo


def test_mutacion_b_linea_movida_acusa_destino_no_origen(loaded):
    _client, reader, entries, _sinc, _dim, (_c, _p, _a, payloads) = loaded
    line_id = _res_id("aml_eag_29_0")
    other_id = _res_id("aml_eag_29_1")
    original = int(_psql(f"SELECT account_id FROM account_move_line WHERE id = {line_id}"))
    target = int(_psql(f"SELECT account_id FROM account_move_line WHERE id = {other_id}"))
    assert original != target

    # Mutación (b) — EL bug P1 del review E1.5, reproducido por debajo: la
    # línea cambia de cuenta, el código viaja intacto. El plano destino
    # re-agrupa `balance` por account_id y acusa; la paridad origen NO VE NADA
    # — este test documenta que el plano 2 existe exactamente por eso.
    _psql(f"UPDATE account_move_line SET account_id = {target} WHERE id = {line_id}")
    try:
        origin, destination, counts = _planes(reader, entries, payloads)
        assert origin == []  # ciega al ruteo podrido — por diseño del plano 1
        assert len(destination) == 2  # una cuenta de más, otra de menos
        assert sum((d.diff for d in destination), Decimal(0)) == 0
        assert counts == []
    finally:
        _psql(f"UPDATE account_move_line SET account_id = {original} WHERE id = {line_id}")

    verify(reader, entries, payloads)


def test_mutacion_c_move_borrado_acusa_conteos(loaded):
    client, reader, entries, _sinc, _dim, (chart, partners, analytic, payloads) = loaded
    move_id = _res_id("mv_eag_4158")
    cids = [int(x) for x in _psql("SELECT id FROM res_company ORDER BY id").splitlines()]
    # `button_draft` devuelve None y el XML-RPC no marshalea None (patrón E1.5).
    client.execute("account.move", "write", [move_id], {"state": "draft"},
                   context={"allowed_company_ids": cids})
    # El unlink vía ORM limpia también los xmlids mv_*/aml_* en ir.model.data
    # (por eso la re-carga de E1.5 CREA el move de nuevo — mismo camino que
    # su test AC2 de reconvergencia).
    client.execute("account.move", "unlink", [move_id],
                   context={"allowed_company_ids": cids})

    # La re-carga va en finally (como el revert de las mutaciones a/b): un
    # assert fallido acá NO puede dejar la db del fixture de módulo sin el
    # move — el test de muestreo caería en cascada enmascarando la causa.
    try:
        origin, destination, counts = _planes(reader, entries, payloads)
        assert counts, "los conteos NO acusaron un move borrado"
        assert any("AUSENTES" in p and "4158" in p for p in counts)
        assert any("líneas" in p for p in counts)  # n_lines también descuadra
        # El move borrado tenía saldo: origen y destino también lo ven (borrar
        # NO es silencioso en ningún plano — acá el que manda es conteos).
        assert origin and destination
    finally:
        # Re-carga (loader E1.5) → converge.
        load_all(client, chart, partners, analytic, payloads)

    verify(reader, entries, payloads)  # gate verde de nuevo


def test_muestreo_estable_2_corridas_mismo_archivo(loaded):
    _client, reader, _entries, sinc, dim, (_c, _p, _a, payloads) = loaded

    sample = select_sample(payloads)
    assert len(sample) == 5  # golden: los 5 moves salen, sin duplicar

    def render():
        return build_muestreo_report(
            sample,
            reader.sample_lines(sample),
            analytic_names=reader.analytic_names(),
            sinc_report=sinc.report,
            dim_report=dim.report,
        )

    report_1 = render()
    report_2 = render()
    assert report_1 == report_2  # NFR1: 2 corridas → mismo archivo

    # La cuenta de la columna "Odoo (real)" está LEÍDA de Odoo: la pata
    # sincerada del JE 1237 muestra la cuenta de ORIGEN, no el colapso.
    assert "mv_eag_1237" in report_1
    assert "assetseaginvtecnion" in report_1
    assert "## Firma" in report_1
    assert "Cobertura de glosa" in report_1

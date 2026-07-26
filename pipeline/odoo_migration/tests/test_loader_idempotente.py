"""Smoke Tier B (opt-in) — E1.5: el loader idempotente contra Odoo real (AC1–AC4).

NO corre por-commit (marcado `@pytest.mark.odoo`, saltado por el conftest).
Requiere Docker. Levanta el compose propio (`migration_e1`, puerto 8070),
instala `x_laudus_migration` en una db fresca (`test_e15`) y corre el loader
REAL (XML-RPC) sobre el golden slice:

  - AC1: cuentas/asientos/líneas con xmlids en `__laudus__`, posteados, 2 cías.
  - AC2: 2ª corrida → 0 creates, estado idéntico; borrar la mitad → converge.
  - AC3: la apertura no se duplica (211005 sin líneas — el par wash quedó
    excluido en E1.3) + paridad por código × moneda × compañía == mirror golden.
  - AC4: la línea USD lleva currency_id + amount_currency y cuadra por moneda.

El golden no trae metadata E1.4 poblada (verificado en esa story), así que el
write-path de partner/analítica se ejercita estampando metadata SINTÉTICA en
dos patas del JE 1237 (lección E1.4). El ruteo por destino sincerado (review
P1) en cambio tiene cobertura REAL: las 5 patas de ingreso del JE 1237 son
naturaleza B (retiros Tecnión) y E1.3 las re-rutea a cuentas de ORIGEN
`Assets:*:InvTecnion` — el chart las crea vía `build_origin_accounts`
(xmlids `accs_*`) y las líneas deben aterrizar ahí, no en el colapso.

Correr:
  PYTHONUTF8=1 venv/Scripts/python.exe -m pytest \
      pipeline/odoo_migration/tests/test_loader_idempotente.py -m odoo -q

Helpers de compose duplicados de `test_x_laudus_migration_install.py` a
propósito (DB distinta; si se endurece el skip de `up -d`, endurecer ambos —
defer E1.0/E1.1 vigente).
"""

import dataclasses
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
from pipeline.odoo_migration.parity import laudus_balances
from pipeline.odoo_migration.sincerar import load_alias_table, sincerar
from pipeline.odoo_migration.transform import collapse

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
COMPOSE = os.path.join(REPO, "pipeline", "odoo_migration", "docker-compose.yml")
FIXTURE = os.path.join(REPO, "pipeline", "odoo_migration", "tests", "fixtures",
                       "golden_slice.beancount")
PROJECT = "migration_e1"
DB = "test_e15"
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


def _payloads():
    """Cadena completa sobre el golden + metadata E1.4 SINTÉTICA en 2 patas
    del JE 1237 (partner partición + dim propiedad) para el write-path. Las
    patas sinceradas (naturaleza B → `Assets:*:InvTecnion`) vienen REALES de
    la cadena — no se estampa ruteo."""
    entries, errors, _ = bc_loader.load_file(FIXTURE)
    assert errors == []
    table = load_mapping_table()
    aliases = load_alias_table()
    moves = collapse(entries, table)
    sinc = sincerar(moves, table, alias_table=aliases)
    dim = dimensionar(sinc.moves, table, alias_table=aliases)

    stamped = []
    for move in dim.moves:
        if move.je_id == "1237":
            lines = list(move.lines)
            lines[0] = dataclasses.replace(
                lines[0], partner="José Alazraki",
                partner_categoria="socio-particion", partner_regla="test:sintetico",
            )
            lines[1] = dataclasses.replace(lines[1], dim_propiedad="Vía Gris")
            move = dataclasses.replace(move, lines=lines)
        stamped.append(move)

    return entries, table, stamped


def _snapshot():
    """Estado observable de la carga: N moves/líneas + saldos por código ×
    moneda × compañía (en amount_currency: CLP == debit−credit, USD == nominal)."""
    n_moves = _psql("SELECT count(*) FROM account_move")
    n_lines = _psql("SELECT count(*) FROM account_move_line")
    balances = _psql(
        "SELECT co.name, l.x_laudus_account_code, cu.name, "
        "       SUM(l.amount_currency) "
        "FROM account_move_line l "
        "JOIN res_company co ON co.id = l.company_id "
        "JOIN res_currency cu ON cu.id = l.currency_id "
        "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
    )
    return n_moves, n_lines, balances


@pytest.fixture(scope="module")
def loaded():
    """Stack arriba + módulo instalado en db fresca + PRIMERA corrida del loader.

    Devuelve (client, counts_1a_corrida, snapshot_1a_corrida, entries, payloads).
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

        entries, table, moves = _payloads()
        chart = build_chart(table) + build_origin_accounts(moves, table)
        partners = build_partners(moves)
        analytic = build_analytic(moves)
        payloads = build_moves(moves, chart)

        client = OdooClient(URL, DB, "admin", "admin")
        counts = load_all(client, chart, partners, analytic, payloads)
        yield client, counts, _snapshot(), entries, (chart, partners, analytic, payloads)
    finally:
        _compose("down", "-v")


def test_ac1_carga_con_xmlids_y_posteo(loaded):
    client, counts, snapshot, _entries, (chart, partners, analytic, payloads) = loaded

    # Conteos de la primera corrida (pinneados: chart full-tabla + golden).
    # 361 de la tabla + 5 cuentas de ORIGEN SINCERADO reales del golden (las
    # patas naturaleza-B del JE 1237 → Assets:*:InvTecnion, review P1).
    assert counts["accounts_created"] == 366
    assert counts["partners_created"] == 1  # José Alazraki (sintético)
    assert counts["analytic_created"] == 7  # 6 entidades + Vía Gris
    assert counts["moves_created"] == 5  # 7 del slice − 2 washes E1.3
    assert counts["moves_skipped"] == 0
    # Db fresca: nada que adoptar ni re-postear; el grupo analítico se otorga
    # UNA vez (prerequisito propio, visible — review P2/P3/P9).
    assert counts["accounts_adopted"] == 0
    assert counts["moves_adopted"] == 0
    assert counts["moves_reposted"] == 0
    assert counts["analytic_group_granted"] == 1
    # currencies_activated depende de la data base de Odoo (si USD ya viene
    # activa es 0) — lo que SÍ es contrato es que la 2ª corrida no active nada.
    assert counts["currencies_activated"] in (0, 1)

    # Posteados, ambas compañías (AC1).
    posted = _psql(
        "SELECT co.name, count(*) FROM account_move m "
        "JOIN res_company co ON co.id = m.company_id "
        "WHERE m.state = 'posted' GROUP BY 1 ORDER BY 1"
    ).splitlines()
    assert posted == ["EAG|4", "RUT2|1"], posted

    # Todos los xmlids registrados en el namespace (573 de cuenta = 568
    # alias acc_* de la tabla + 5 accs_* de origen; 5 mv_*, 18 aml_*,
    # 1 prt_*, 7 aa_*).
    by_model = dict(
        row.split("|")
        for row in _psql(
            f"SELECT model, count(*) FROM ir_model_data "
            f"WHERE module = '{XMLID_MODULE}' GROUP BY model"
        ).splitlines()
    )
    assert int(by_model["account.account"]) == sum(len(a.aliases) for a in chart)
    assert int(by_model["account.move"]) == 5
    assert int(by_model["account.move.line"]) == 18
    assert int(by_model["res.partner"]) == 1
    assert int(by_model["account.analytic.account"]) == 7

    # Trazabilidad: TODAS las líneas llevan los 3 campos x_laudus_* (AC1/FR5).
    incomplete = _psql(
        "SELECT count(*) FROM account_move_line "
        "WHERE coalesce(x_laudus_account_code,'') = '' "
        "   OR coalesce(x_laudus_je_id,'') = '' "
        "   OR coalesce(x_laudus_entity,'') = ''"
    )
    assert incomplete == "0"


def test_ac1_partner_y_analitica_escritos(loaded):
    # El write-path sintético: pata 0 del JE 1237 con partner + pata 1 con
    # analítica de propiedad (además de la entidad que llevan todas).
    partner = _psql(
        "SELECT p.name FROM account_move_line l "
        "JOIN res_partner p ON p.id = l.partner_id "
        "JOIN ir_model_data d ON d.model = 'account.move.line' AND d.res_id = l.id "
        f"WHERE d.module = '{XMLID_MODULE}' AND d.name = 'aml_eag_1237_0'"
    )
    assert partner == "José Alazraki"

    dist = _psql(
        "SELECT l.analytic_distribution FROM account_move_line l "
        "JOIN ir_model_data d ON d.model = 'account.move.line' AND d.res_id = l.id "
        f"WHERE d.module = '{XMLID_MODULE}' AND d.name = 'aml_eag_1237_1'"
    )
    via_gris = _psql(
        "SELECT a.id FROM account_analytic_account a "
        "JOIN ir_model_data d ON d.model = 'account.analytic.account' AND d.res_id = a.id "
        f"WHERE d.module = '{XMLID_MODULE}' AND d.name = 'aa_propiedadobjeto_viagris'"
    )
    import json

    parsed = json.loads(dist)
    assert parsed.get(via_gris) == 100, (dist, via_gris)


def test_ac1_ruteo_por_destino_sincerado(loaded):
    # Las 5 patas de ingreso del JE 1237 son naturaleza B REAL (retiros
    # Tecnión): E1.3 les reescribe el destino a Assets:*:InvTecnion sin tocar
    # laudus_code. En Odoo deben quedar en las cuentas de ORIGEN `accs_*`, NO
    # en el colapso de su código — el bug crítico del review (P1).
    account_xmlid = _psql(
        "SELECT da.name FROM account_move_line l "
        "JOIN ir_model_data d ON d.model = 'account.move.line' AND d.res_id = l.id "
        "JOIN ir_model_data da ON da.model = 'account.account' AND da.res_id = l.account_id "
        f"WHERE d.module = '{XMLID_MODULE}' AND d.name = 'aml_eag_1237_1' "
        f"  AND da.module = '{XMLID_MODULE}'"
    )
    assert account_xmlid == "accs_eag_assetseaginvtecnion"
    # Las 5 cuentas de origen existen y recibieron exactamente esas 5 patas.
    n_origin_lines = _psql(
        "SELECT count(*) FROM account_move_line l "
        "JOIN ir_model_data da ON da.model = 'account.account' AND da.res_id = l.account_id "
        f"WHERE da.module = '{XMLID_MODULE}' AND da.name LIKE 'accs_%'"
    )
    assert n_origin_lines == "5"
    # Tipo + marca de grupo de origen. En Odoo 18 `code` es company-dependent:
    # no es columna de account_account, vive en el jsonb `code_store` keyed
    # por id de compañía.
    row = _psql(
        "SELECT a.code_store ->> co.id::text, a.account_type, a.x_laudus_group "
        "FROM account_account a "
        "JOIN res_company co ON co.name = 'EAG' "
        "JOIN ir_model_data d ON d.model = 'account.account' AND d.res_id = a.id "
        f"WHERE d.module = '{XMLID_MODULE}' AND d.name = 'accs_eag_assetseaginvtecnion'"
    )
    assert row == "assetseaginvtecnion|asset_current|ORIGEN-SINCERADO"


def test_ac2_idempotencia_2x_estado_identico(loaded):
    client, _counts, snapshot_1, _entries, (chart, partners, analytic, payloads) = loaded

    counts_2 = load_all(client, chart, partners, analytic, payloads)
    assert counts_2["accounts_created"] == 0
    assert counts_2["partners_created"] == 0
    assert counts_2["analytic_created"] == 0
    assert counts_2["moves_created"] == 0
    assert counts_2["moves_skipped"] == 5
    # Nada que adoptar/re-postear (todo tiene xmlid y está posteado) y el
    # grupo analítico ya estaba otorgado — la 2ª corrida no muta NADA (P9).
    assert counts_2["accounts_adopted"] == 0
    assert counts_2["moves_adopted"] == 0
    assert counts_2["moves_reposted"] == 0
    assert counts_2["analytic_group_granted"] == 0
    assert counts_2["currencies_activated"] == 0
    assert _snapshot() == snapshot_1


def test_ac2_borrar_mitad_y_reconverger(loaded):
    client, _counts, snapshot_1, _entries, (chart, partners, analytic, payloads) = loaded

    # La "mitad" intercalada entre compañías (no solo la cola de una):
    # 2 EAG + 1 RUT2 de los 5.
    victims = ["mv_eag_29", "mv_rut2_3994", "mv_eag_4158"]
    ids = [
        int(_psql(
            f"SELECT res_id FROM ir_model_data "
            f"WHERE module = '{XMLID_MODULE}' AND name = '{name}'"
        ))
        for name in victims
    ]
    cids = [int(x) for x in _psql(
        "SELECT id FROM res_company ORDER BY id").splitlines()]
    # `button_draft` devuelve None y el XML-RPC de Odoo no marshalea None;
    # write(state='draft') es lo que button_draft hace por dentro y sí retorna.
    client.execute("account.move", "write", ids, {"state": "draft"},
                   context={"allowed_company_ids": cids})
    client.execute("account.move", "unlink", ids,
                   context={"allowed_company_ids": cids})
    assert _psql("SELECT count(*) FROM account_move") == "2"

    counts_3 = load_all(client, chart, partners, analytic, payloads)
    assert counts_3["moves_created"] == 3
    assert counts_3["moves_skipped"] == 2
    assert counts_3["accounts_created"] == 0
    assert _snapshot() == snapshot_1


def test_ac3_apertura_sin_doble_conteo_y_paridad_golden(loaded):
    _client, _counts, _snapshot_1, entries, _payloads = loaded

    # El par wash (Comprobante cierre/apertura, 211005) quedó excluido en
    # E1.3: NINGUNA línea debe haber llegado a Odoo con ese código (AC3 en
    # miniatura: cargarlo dos veces duplicaría la apertura).
    assert _psql(
        "SELECT count(*) FROM account_move_line WHERE x_laudus_account_code = '211005'"
    ) == "0"

    # Paridad estilo E1.6 sobre el golden: Σ amount_currency por (compañía,
    # código, moneda) en Odoo == Σ units.number del mirror (0 diffs). El lado
    # Laudus se deriva del MIRROR, no del transformador (patrón E1.3).
    odoo_side = {}
    for row in _psql(
        "SELECT co.name, l.x_laudus_account_code, cu.name, SUM(l.amount_currency) "
        "FROM account_move_line l "
        "JOIN res_company co ON co.id = l.company_id "
        "JOIN res_currency cu ON cu.id = l.currency_id "
        "GROUP BY 1, 2, 3"
    ).splitlines():
        company, code, currency, total = row.split("|")
        odoo_side[(company, code, currency)] = Decimal(total)

    # El lado mirror trae TODOS los códigos, incluidos los del par wash
    # excluido (que netean a 0.00). El loop de abajo cubre ambos casos: un
    # código cargado debe calzar al peso, y un código NO cargado (ausente en
    # odoo_side → get() devuelve 0) solo pasa si su saldo mirror es 0 — nada
    # se pierde en silencio (review P12: el comment anterior describía un
    # filtro que no existía).
    laudus_side = laudus_balances(entries)
    for key, expected in laudus_side.items():
        got = odoo_side.get(key, Decimal("0"))
        assert got == expected, f"paridad rota en {key}: odoo={got} mirror={expected}"
    for key in set(odoo_side) - set(laudus_side):
        pytest.fail(f"Odoo tiene saldo en {key} que el mirror no conoce")


def test_ac4_usd_currency_y_amount_currency(loaded):
    row = _psql(
        "SELECT cu.name, l.amount_currency, l.debit, l.credit "
        "FROM account_move_line l "
        "JOIN res_currency cu ON cu.id = l.currency_id "
        "JOIN ir_model_data d ON d.model = 'account.move.line' AND d.res_id = l.id "
        f"WHERE d.module = '{XMLID_MODULE}' AND d.name = 'aml_eag_9000003_0'"
    )
    currency, amount_currency, debit, credit = row.split("|")
    assert currency == "USD"
    assert Decimal(amount_currency) == Decimal("100.00")
    assert Decimal(debit) == Decimal("80000")
    assert Decimal(credit) == 0

    # El asiento cuadra por moneda: CLP netea 0 dentro del move y el nominal
    # USD quedó preservado (AC4).
    balance = _psql(
        "SELECT SUM(l.debit - l.credit) FROM account_move_line l "
        "JOIN account_move m ON m.id = l.move_id WHERE m.x_laudus_je_id = '9000003'"
    )
    assert Decimal(balance) == 0

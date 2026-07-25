"""Smoke Tier B (opt-in) — E1.1: instala x_laudus_migration y verifica AC1-AC4.

NO corre por-commit (marcado `@pytest.mark.odoo`, saltado por el conftest). Requiere
Docker. Levanta el compose PROPIO de E1.1 (no el del spike) bajo project aislado,
instala el módulo en una db fresca y verifica por SQL:
  - AC1: los 5 campos custom existen en sus modelos.
  - AC4/AC1: los 4 campos que deben ir indexados tienen índice DB.
  - AC2: 6 planes analíticos + 1 diario por compañía (2).
  - AC3: 2 compañías (EAG/RUT2), ninguna con l10n_cl instalado.
Siempre baja el stack.

Correr:  PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -m odoo -q
"""

import os
import shutil
import subprocess
import time

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
COMPOSE = os.path.join(REPO, "pipeline", "odoo_migration", "docker-compose.yml")
PROJECT = "migration_e1"
DB = "test_e1"

pytestmark = pytest.mark.odoo


def _compose(*args, timeout=600):
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", COMPOSE, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _psql(sql):
    """Corre SQL en la db instalada y devuelve stdout (tuplas, sin encabezado)."""
    res = _compose("exec", "-T", "db", "psql", "-U", "odoo", "-d", DB, "-tA", "-c", sql)
    assert res.returncode == 0, f"psql falló: {res.stderr}\n{res.stdout}"
    return res.stdout.strip()


def _wait_for_db(timeout=120):
    """Poll hasta que Postgres acepte conexiones.

    `up -d` retorna al arrancar el contenedor, no cuando la db está lista: en un
    volumen fresco el initdb sigue corriendo y el `odoo -i` inmediato pegaría
    connection-refused (Odoo no reintenta). Mismo espíritu que `_wait_for_odoo`
    del smoke de E1.0.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _compose("exec", "-T", "db", "pg_isready", "-U", "odoo").returncode == 0:
            return
        time.sleep(2)
    pytest.fail(f"Postgres no estuvo listo en {timeout}s")


def _has_index(table, column):
    n = _psql(
        f"SELECT count(*) FROM pg_indexes "
        f"WHERE tablename='{table}' AND indexdef LIKE '%{column}%'"
    )
    return int(n) > 0


@pytest.fixture(scope="module")
def odoo_stack():
    # module scope: levanta e instala el módulo UNA vez; los 4 tests consultan la
    # misma db; baja una vez. (function scope reinstalaría Odoo 4 veces.)
    if shutil.which("docker") is None:
        pytest.skip("docker no está en el PATH")
    try:
        up = _compose("up", "-d")
        if up.returncode != 0:
            pytest.skip(f"no se pudo levantar el stack (¿daemon Docker abajo?): {up.stderr}")
        _wait_for_db()
        # Garantizar db FRESCA: un run anterior matado a la fuerza (sin `down -v`)
        # deja test_e1 instalada, y `odoo -i` sobre db existente NO re-corre el
        # post_init_hook → los tests validarían lo que dejó código viejo (falso verde).
        drop = _compose("exec", "-T", "db", "dropdb", "-U", "odoo", "--if-exists", DB)
        assert drop.returncode == 0, f"dropdb {DB} falló: {drop.stderr}"
        # Instala el módulo en una db fresca (crea la db, instala base+deps+addon).
        install = _compose(
            "exec", "-T", "odoo",
            "odoo", "-d", DB, "--stop-after-init",
            "-i", "x_laudus_migration",
            "--without-demo", "all",
            timeout=600,
        )
        if install.returncode != 0:
            pytest.fail(f"instalar x_laudus_migration falló:\n{install.stderr[-2000:]}")
        yield
    finally:
        _compose("down", "-v")


def test_ac1_campos_custom_existen(odoo_stack):
    line_cols = _psql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='account_move_line' AND column_name LIKE 'x_laudus_%' "
        "ORDER BY column_name"
    ).split()
    assert line_cols == ["x_laudus_account_code", "x_laudus_entity", "x_laudus_je_id"]

    acc_cols = _psql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='account_account' AND column_name LIKE 'x_laudus_%'"
    ).split()
    assert acc_cols == ["x_laudus_group"]

    move_cols = _psql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='account_move' AND column_name LIKE 'x_laudus_%'"
    ).split()
    assert move_cols == ["x_laudus_je_id"]


def test_ac4_campos_indexados_tienen_indice(odoo_stack):
    # Los 4 que deben ir indexados (3 en la línea + je_id en la cabecera).
    assert _has_index("account_move_line", "x_laudus_account_code")
    assert _has_index("account_move_line", "x_laudus_je_id")
    assert _has_index("account_move_line", "x_laudus_entity")
    assert _has_index("account_move", "x_laudus_je_id")
    # x_laudus_group NO debe estar indexado (es contexto, no paridad).
    assert not _has_index("account_account", "x_laudus_group")


def test_ac2_seed_planes_y_diarios(odoo_stack):
    # Los 6 planes creados por ESTE módulo (por external id, robusto ante i18n del name).
    plans = _psql(
        "SELECT count(*) FROM ir_model_data "
        "WHERE module='x_laudus_migration' AND model='account.analytic.plan'"
    )
    assert plans == "6", f"esperaba 6 planes analíticos del módulo, got {plans}"

    # Por compañía y con tipo (AC2 dice "un diario, tipo general, POR compañía" —
    # un count por code pasaría aunque ambos cayeran en la misma compañía).
    journals = _psql(
        "SELECT c.name, j.code, j.type FROM account_journal j "
        "JOIN res_company c ON c.id = j.company_id "
        "WHERE j.code IN ('LAU1','LAU2') ORDER BY c.name"
    ).splitlines()
    assert journals == ["EAG|LAU1|general", "RUT2|LAU2|general"], journals


def test_ac3_companias_sin_l10n_cl(odoo_stack):
    # Exactamente las 2 (db fresca = main company renombrada a EAG + RUT2 creada;
    # membership solo dejaría pasar una "My Company" huérfana si el rename regresara).
    companies = _psql("SELECT name FROM res_company ORDER BY name").splitlines()
    assert companies == ["EAG", "RUT2"], companies

    l10n = _psql(
        "SELECT count(*) FROM ir_module_module WHERE name='l10n_cl' AND state='installed'"
    )
    assert l10n == "0", "l10n_cl NO debe estar instalado (AC3)"

    # Guard directo del invariante "compañías SIN CoA": si la cancelación del
    # auto-load de generic_coa (hooks.py) dejara de funcionar, acá aparecen cuentas.
    accounts = _psql("SELECT count(*) FROM account_account")
    assert accounts == "0", f"esperaba 0 cuentas (sin CoA), got {accounts}"

"""Smoke Tier B (opt-in) — AC4: el stack Odoo levanta y acepta un addon custom.

NO corre por-commit: está marcado `@pytest.mark.odoo` y el conftest lo salta
salvo que se pida explícitamente:

    PYTHONUTF8=1 venv/Scripts/python.exe -m pytest pipeline/odoo_migration -m odoo -q

Requiere Docker. Levanta el compose del spike (referenciado, no duplicado —
E1.1 promoverá su propio compose cuando monte el addon real), confirma que
Odoo 18 responde en :8069 y que acepta INSTALAR un addon custom mínimo
(scaffold + `--stop-after-init -i`, la señal que pide AC4). Siempre baja el
stack al terminar. Es lento (~2-3 min): por eso es gate de release, no de commit.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
COMPOSE = os.path.join(REPO, "_spike-odoo", "docker-compose.yml")
# Project name dedicado: aísla los volúmenes del smoke de los del stack del spike
# (proyecto default `_spike-odoo`), así `down -v` nunca borra datos del spike.
PROJECT = "migration_smoke"
ODOO_URL = "http://localhost:8069"
STUB_ADDON = "x_laudus_smoke"
STUB_HOST_DIR = os.path.join(REPO, "_spike-odoo", "addons", STUB_ADDON)

pytestmark = pytest.mark.odoo


def _compose(*args, timeout=300):
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", COMPOSE, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _wait_for_odoo(timeout=240):
    """Poll hasta que Odoo responda y devuelve su version_info."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    f"{ODOO_URL}/web/webclient/version_info",
                    data=b'{"jsonrpc":"2.0","method":"call","params":{}}',
                    headers={"Content-Type": "application/json"},
                ),
                timeout=10,
            ) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, ConnectionError, OSError, json.JSONDecodeError) as exc:
            # JSONDecodeError: durante el boot Odoo puede responder 200 con HTML
            # (login/redirect) en vez de JSON → seguir reintentando, no abortar.
            last = exc
            time.sleep(5)
    raise TimeoutError(f"Odoo no respondió en {timeout}s (último error: {last})")


@pytest.fixture
def odoo_stack():
    if shutil.which("docker") is None:
        pytest.skip("docker no está en el PATH")
    # `up` va DENTRO del try: si lanza (p.ej. TimeoutExpired) el `finally` igual
    # baja el stack, sin dejar contenedores/volúmenes huérfanos.
    try:
        up = _compose("up", "-d")
        if up.returncode != 0:
            pytest.skip(f"no se pudo levantar el stack (¿daemon Docker abajo?): {up.stderr}")
        yield
    finally:
        _compose("down", "-v")
        shutil.rmtree(STUB_HOST_DIR, ignore_errors=True)


def test_odoo18_responde_y_acepta_addon_custom(odoo_stack):
    # 1) Odoo 18 responde en :8069
    info = _wait_for_odoo()
    # `or info`: si la key `result` está presente pero es null, `.get(default)`
    # devolvería None (el default solo aplica a key AUSENTE) → None.get → crash.
    serie = str((info.get("result") or info).get("server_serie", ""))
    assert serie.startswith("18"), f"esperaba Odoo 18, server_serie={serie!r}"

    # 2) Acepta un addon custom: scaffold en el addons_path + instalación limpia.
    scaffold = _compose("exec", "-T", "odoo", "odoo", "scaffold", STUB_ADDON, "/mnt/extra-addons")
    assert scaffold.returncode == 0, f"odoo scaffold falló: {scaffold.stderr}"

    install = _compose(
        "exec", "-T", "odoo",
        "odoo", "-d", "smoke_db", "--stop-after-init", "-i", STUB_ADDON,
        timeout=300,
    )
    assert install.returncode == 0, f"instalar el addon custom falló por infra: {install.stderr}"

"""Tests del subárbol de cuentas RUT2 (Fondo Común) — Story 12.3.

Verifican sobre el LEDGER REAL (`ledger/accounts.beancount`) que el bloque
appendeado por `bootstrap/generate_rut2_accounts.py` cumple la clasificación
FIRMADA (`clasificacion-contable-rut2-firmada-2026-07-11.md` §1/§3/§8):
311 opens nuevos (309 hojas + 2 Equity), convención de path
`{Root}:{Entidad}:{slug}-{código}`, metadata `code` en toda cuenta RUT2
(cierra el defer de 11.2 "cuenta sin code rompe drill-down") y cero
contaminación del namespace EAG.
"""
import json
import re
import uuid
from pathlib import Path

import pytest
from beancount.core.data import Open
from beancount.loader import load_file

from bootstrap.account_mapping import slugify

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS_FILE = REPO_ROOT / "ledger" / "accounts.beancount"
PLAN_JSON = (
    REPO_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "rut2-plan-cuentas-laudus-2026-07-10.json"
)

# Artefacto §1 — dígito de raíz → (Root, Entidad). Liabilities:JAB NO existe.
ROOT_MAP = {
    "1": ("Assets", "FFCC"),
    "2": ("Liabilities", "FFCC"),
    "3": ("Income", "FFCC"),
    "4": ("Expenses", "FFCC"),
    "6": ("Assets", "JAB"),
    "7": ("Income", "JAB"),
    "8": ("Expenses", "JAB"),
}

RUT2_ENTITIES = ("FFCC", "JAB")


def _load_opens() -> list[Open]:
    if not ACCOUNTS_FILE.exists():
        pytest.skip("ledger/accounts.beancount not present in this checkout")
    entries, errors, _ = load_file(str(ACCOUNTS_FILE))
    assert not errors, f"accounts.beancount tiene errores de carga: {errors[:3]}"
    return [e for e in entries if isinstance(e, Open)]


def _rut2_opens(opens: list[Open]) -> list[Open]:
    """Opens cuyo 2º segmento es una entidad RUT2 (incluye Equity:FFCC/JAB)."""
    return [
        o for o in opens if o.account.split(":")[1] in RUT2_ENTITIES
    ]


@pytest.fixture(scope="module")
def opens() -> list[Open]:
    return _load_opens()


@pytest.fixture(scope="module")
def rut2(opens) -> list[Open]:
    return _rut2_opens(opens)


@pytest.fixture(scope="module")
def plan_leaves() -> list[dict]:
    if not PLAN_JSON.exists():
        pytest.skip("plan JSON RUT2 not present in this checkout")
    accounts = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    numbers = {a["accountNumber"] for a in accounts}

    def is_leaf(n: str) -> bool:
        return not any(m != n and m.startswith(n) for m in numbers)

    return [a for a in accounts if is_leaf(a["accountNumber"])]


def test_total_311_opens_rut2(rut2):
    """AC1+AC2: 311 opens nuevos — 309 hojas + 2 Equity (artefacto §6/§8)."""
    assert len(rut2) == 311


def test_hojas_matchean_plan_por_path_completo(rut2, plan_leaves):
    """AC1: bijección hoja-del-plan ↔ open, con la convención firmada
    `{Root}:{Entidad}:{slugify(name)}-{código}` (slugify canónico)."""
    expected = set()
    for leaf in plan_leaves:
        number, name = leaf["accountNumber"], leaf["name"]
        root, entity = ROOT_MAP[number[0]]
        expected.add(f"{root}:{entity}:{slugify(name)}-{number}")
    assert len(expected) == 309  # los sufijos -{código} desambiguan los 31 dupes

    actual = {o.account for o in rut2 if not o.account.startswith("Equity:")}
    assert actual == expected


def test_toda_cuenta_rut2_tiene_code(rut2):
    """Cierra el defer de 11.2: cuenta sin `code` rompe el drill-down."""
    for o in rut2:
        code = (o.meta or {}).get("code")
        assert code, f"{o.account} sin metadata code"
        if not o.account.startswith("Equity:"):
            assert o.account.endswith(f"-{code}"), (
                f"{o.account}: sufijo de path no coincide con code {code!r}"
            )


def test_toda_cuenta_rut2_tiene_categoria1(rut2):
    """Guard 10.2: laudus_categoria1 no-vacía en todo el subárbol."""
    for o in rut2:
        assert (o.meta or {}).get("laudus_categoria1"), f"{o.account} sin categoria1"


def test_equity_apertura_convencion_firmada(rut2):
    """AC2: dos Equity de respaldo per artefacto §3 — cat1 PATRIMONIO,
    cat2/3 vacías, code sintético 9-prefix, sin bank_account_id."""
    equity = {o.account: o for o in rut2 if o.account.startswith("Equity:")}
    assert set(equity) == {"Equity:FFCC:Apertura", "Equity:JAB:Apertura"}
    codes = set()
    for o in equity.values():
        meta = o.meta or {}
        assert meta.get("laudus_categoria1") == "PATRIMONIO"
        assert meta.get("laudus_categoria2") == ""
        assert meta.get("laudus_categoria3") == ""
        assert "bank_account_id" not in meta
        code = meta.get("code")
        assert re.fullmatch(r"9\d{5}", code), f"code no 9-prefix: {code!r}"
        codes.add(code)
    assert len(codes) == 2  # únicos bajo el índice (entidad, code) de 12.2


def test_bancos_rut2_con_uuid_y_metadata(rut2, opens):
    """AC1: bank_account_id (uuid4) SOLO en los bancos reales de raíces 1/6;
    Cajas/fondos sin UUID. UUIDs únicos contra TODO el plan de cuentas."""
    banks = [o for o in rut2 if "bank_account_id" in (o.meta or {})]
    assert {o.account.split(":")[-1] for o in banks} == {
        "BancoBci28981162-111005",
        "BancoEdwards011626509-111007",
        "BancoBciFgk35190183-611004",
        "BancoBciJabfgk28986911-611005",
        "BancoBciFgk30396000-611006",
        "BancoBciUsdFgk19681721-611007",
    }
    for o in banks:
        meta = o.meta
        uuid.UUID(meta["bank_account_id"])  # formato válido
        assert meta.get("bank_name")
        assert meta.get("bank_account_type") == "cta_corriente"
        assert meta.get("bank_account_currency") in ("CLP", "USD")
    # El banco USD (611007) declara CLP, USD como commodities (espejo EAG 111011).
    usd = next(o for o in banks if o.account.endswith("-611007"))
    assert usd.meta["bank_account_currency"] == "USD"
    assert set(usd.currencies or []) == {"CLP", "USD"}
    # Unicidad global de bank_account_id (RUT2 + EAG).
    all_ids = [
        (o.meta or {}).get("bank_account_id")
        for o in opens
        if "bank_account_id" in (o.meta or {})
    ]
    assert len(all_ids) == len(set(all_ids))


def test_distribucion_por_root_y_entidad(rut2):
    """AC1: distribución de hojas firmada (artefacto §4) y Liabilities:JAB
    inexistente (JAB sin raíz 2)."""
    from collections import Counter

    hojas = [o for o in rut2 if not o.account.startswith("Equity:")]
    dist = Counter(tuple(o.account.split(":")[:2]) for o in hojas)
    assert dist == {
        ("Assets", "FFCC"): 26,
        ("Liabilities", "FFCC"): 1,
        ("Income", "FFCC"): 9,
        ("Expenses", "FFCC"): 63,
        ("Assets", "JAB"): 12,
        ("Income", "JAB"): 2,
        ("Expenses", "JAB"): 196,
    }


def test_ninguna_cuenta_nueva_bajo_namespace_eag():
    """AC3 (aislamiento): TODO lo que agregó 12.3 vive en la sección RUT2 del
    archivo, y cada open de esa sección cuelga de {Root}:{FFCC|JAB}: — cero
    opens nuevos bajo EAG/hijas. (Nota: chequear por (code, nombre) no sirve —
    ambos libros Laudus comparten pares legítimos, ej. 115001 "Cuentas
    Corrientes del Personal" existe en EAG y en RUT2.)"""
    if not ACCOUNTS_FILE.exists():
        pytest.skip("ledger/accounts.beancount not present in this checkout")
    text = ACCOUNTS_FILE.read_text(encoding="utf-8")
    marker = ";; ─── RUT2 (Fondo Común) — subárbol FFCC/JAB — Story 12.3 ───"
    assert marker in text, "sección RUT2 no encontrada en accounts.beancount"
    section = text.split(marker, 1)[1]
    section_opens = re.findall(r"^\d{4}-\d{2}-\d{2} open (\S+)", section, re.M)
    assert len(section_opens) == 311
    pattern = re.compile(
        r"^(Assets|Liabilities|Income|Expenses|Equity):(FFCC|JAB):"
    )
    for account in section_opens:
        assert pattern.match(account), f"open fuera de namespace RUT2: {account}"

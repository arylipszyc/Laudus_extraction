"""Tests del histórico importado del libro RUT2 (Fondo Común) — Story 12.4.

Verifican sobre el LEDGER REAL que el import multi-libro dejó lo que la story
manda: includes activos en main.beancount, todos los asientos de
`imports/laudus-rut2/` bajo entidades del libro (FFCC/JAB — jamás EAG),
la apertura ruteada per convención firmada 12.1 §3 (JE real "Saldo Inicial"
vía `Liabilities:FFCC:Apertura-211005`; Equity de respaldo SIN uso = caso (a)
del veredicto de la sonda), y cuarentena vacía (AC5: pending masivo = ruteo
roto, no cuentas faltantes).

Pines deliberados (patrón 12.3): si un cambio futuro postea a las Equity de
respaldo o mete un pending, estos tests DEBEN romperse — es señal, no bug.
"""
from pathlib import Path

from beancount.core.data import Open, Transaction
from beancount.parser import parser

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = REPO_ROOT / "ledger"
RUT2_IMPORTS = LEDGER_DIR / "imports" / "laudus-rut2"
RUT2_PENDING = LEDGER_DIR / "imports" / "_new-accounts-pending-rut2.beancount"

RUT2_ENTITIES = {"FFCC", "JAB"}
EQUITY_RESPALDO = {"Equity:FFCC:Apertura", "Equity:JAB:Apertura"}


def _rut2_transactions() -> list[Transaction]:
    txs: list[Transaction] = []
    for path in sorted(RUT2_IMPORTS.glob("*.beancount")):
        if path.name.startswith("_"):
            continue
        entries, errors, _options = parser.parse_file(str(path))
        assert not errors, f"{path.name}: {errors[:3]}"
        txs.extend(e for e in entries if isinstance(e, Transaction))
    return txs


def test_main_incluye_los_archivos_rut2():
    """El wiring de 12.4: sin estos includes, bean-check no ve el libro RUT2."""
    main = (LEDGER_DIR / "main.beancount").read_text(encoding="utf-8")
    assert 'include "imports/laudus-rut2/*.beancount"' in main
    assert 'include "imports/_new-accounts-pending-rut2.beancount"' in main
    assert (RUT2_IMPORTS / "_init.beancount").exists()  # glob nunca vacío


def test_historico_importado_y_solo_bajo_entidades_del_libro():
    """NFR20: ninguna pata de imports/laudus-rut2/ postea fuera de FFCC/JAB."""
    txs = _rut2_transactions()
    assert len(txs) > 10_000  # backfill 2021→hoy (la sonda contó 10.530 JEs)
    for tx in txs:
        for posting in tx.postings:
            segments = posting.account.split(":")
            assert segments[1] in RUT2_ENTITIES, (
                f"{tx.date} {tx.meta.get('id')}: pata fuera del libro → {posting.account}"
            )


def test_apertura_es_je_real_via_211005():
    """FR53 per convención firmada §3 (supersede la letra del epic): la apertura
    es el JE real id=1 'Saldo Inicial' y rutea a Liabilities:FFCC:Apertura-211005
    — el mecanismo primario espejo-Laudus, no las Equity."""
    entries, errors, _options = parser.parse_file(str(RUT2_IMPORTS / "2021-01.beancount"))
    assert not errors
    apertura = next(
        e for e in entries
        if isinstance(e, Transaction) and (e.meta or {}).get("id") == "1"
    )
    assert apertura.date.isoformat() == "2021-01-01"
    assert apertura.narration == "Saldo Inicial"
    accounts = {p.account for p in apertura.postings}
    assert "Liabilities:FFCC:Apertura-211005" in accounts
    assert not accounts & EQUITY_RESPALDO


def test_equity_de_respaldo_sin_uso():
    """Veredicto de la sonda (caso a): la apertura cerró self-balancing vía 211005
    → las Equity de respaldo quedan en 0 postings. Si esto rompe, algo empezó a
    postearles — revisar antes de tocar el test (advertencia §3.5: un plug ahí
    NO es patrimonio real)."""
    for tx in _rut2_transactions():
        used = {p.account for p in tx.postings} & EQUITY_RESPALDO
        assert not used, f"{tx.date} {tx.meta.get('id')}: postea a {used}"


def test_cuarentena_rut2_vacia():
    """AC5: el árbol de 12.3 cubre el 100% de los codes del histórico (la sonda
    lo predijo: 0 de 243) — el pending RUT2 no tiene ni un open."""
    entries, errors, _options = parser.parse_file(str(RUT2_PENDING))
    assert not errors
    assert [e for e in entries if isinstance(e, Open)] == []

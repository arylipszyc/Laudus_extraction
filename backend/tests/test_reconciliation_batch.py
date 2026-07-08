"""Story 6.7 — batch-resolve de discrepancias (un `bean_check` + un commit para N) + atomicidad total.

Cierra los 2 defers de 6.3: un solo write por archivo DENTRO del lock (lost-update) + rollback total
de los archivos `manual/` si `bean_check` falla O si `git_commit_push` lanza (commit parcial). Patrón de
`test_reconciliation_annotate.py`: bean-check real sobre el render, git no-op local
(`IMPORTER_GIT_ENABLED` desactivado).
"""
import json

import pytest

from backend.app.api.v1.reconciliation import service as svc
from backend.app.api.v1.reconciliation.service import (
    AnnotationFailed,
    ResolveError,
    read_discrepancies,
    resolve_batch,
)
from pipeline.importers import reconcile as reconcile_mod
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter
from pipeline.importers.discrepancy_writer import append_discrepancy, build_discrepancy

CC_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT = "Assets:EAG:Bancos:CtaCorriente-100200"

ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:CtaCorriente-100200 CLP, USD
  bank_account_id: "11111111-1111-1111-1111-111111111111"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
  bank_account_last4: "0200"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Expenses:EAG:Super CLP
"""

_TS = "2026-04-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    monkeypatch.delenv("LEDGER_DISCREPANCIES", raising=False)


def _root(tmp_path):
    (tmp_path / "manual").mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    (tmp_path / "main.beancount").write_text(
        'include "accounts.beancount"\ninclude "manual/*.beancount"\n', encoding="utf-8")
    return tmp_path


def _importer(root):
    return CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"))


def _jsonl(root):
    return root / "_meta" / "cartola-discrepancies.jsonl"


def _seed(root, *, state, cartola, laudus=None, fx=None, source="cartola"):
    d = build_discrepancy(batch_id="b1", bank_account_id=CC_ID, state=state, ts=_TS,
                          cartola=cartola, laudus=laudus, fx=fx, source=source)
    append_discrepancy(d, _jsonl(root))
    return d["discrepancy_id"]


def _missing_in_laudus(root, *, line_no=3, amount=-45000.0, currency="CLP", fx=None, date="2026-03-15"):
    return _seed(root, state="missing-in-laudus", fx=fx, cartola={
        "line_no": line_no, "date": date, "amount": amount,
        "currency": currency, "description": f"GASTO REAL {line_no}"})


def _missing_in_cartola(root, *, je_id="JE9"):
    return _seed(root, state="missing-in-cartola", source="laudus", cartola=None,
                 laudus={"journal_entry_id": je_id, "date": "2026-03-20",
                         "amount": -12000.0, "description": "SOLO-LAUDUS"})


def _manual_files(root):
    return list((root / "manual").glob("*.beancount"))


def _resolution_lines(root):
    p = _jsonl(root)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("ref_discrepancy_id")]


def _resolve(root, items, justification="cierre de mes verificado vs banco"):
    return resolve_batch(items, justification=justification, user_email="c@test.com", now_iso=_TS,
                         path=_jsonl(root), ledger_root=root, importer=_importer(root))


# ── AC1: N discrepancias → UN bean_check + UN git_commit_push (spies ≤1) ───────


def test_ac1_un_bean_check_un_commit(tmp_path, monkeypatch):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    d2 = _missing_in_laudus(root, line_no=2)
    calls = {"bean": 0, "git": 0}

    from pipeline.importers import laudus_run
    orig_bean, orig_git = laudus_run.bean_check, laudus_run.git_commit_push

    def spy_bean(main_path):
        calls["bean"] += 1
        return orig_bean(main_path)

    def spy_git(root_, paths, msg):
        calls["git"] += 1
        return orig_git(root_, paths, msg)

    monkeypatch.setattr(laudus_run, "bean_check", spy_bean)
    monkeypatch.setattr(laudus_run, "git_commit_push", spy_git)

    out = _resolve(root, [
        {"discrepancy_id": d1, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
        {"discrepancy_id": d2, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
    ])
    assert calls["bean"] == 1 and calls["git"] == 1
    assert len(out["results"]) == 2
    assert all(r["status"] == "resolved" for r in out["results"])
    # ambas cerradas
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 0
    assert len(_resolution_lines(root)) == 2


# ── AC2: bean-check rojo → rollback total, todas abiertas, sin resoluciones ─────


def test_ac2_bean_check_rojo_rollback_total(tmp_path):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    d2 = _missing_in_laudus(root, line_no=2)
    with pytest.raises(AnnotationFailed):
        _resolve(root, [
            {"discrepancy_id": d1, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
            # cuenta inexistente → bean-check rojo para TODO el batch
            {"discrepancy_id": d2, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:NoExiste"},
        ])
    assert _manual_files(root) == []                                        # rollback total
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 2   # ambas abiertas
    assert _resolution_lines(root) == []


# ── AC3: git push lanza tras bean-check verde → rollback total + retry sin doble ─


def test_ac3_git_push_raise_rollback_y_retry_sin_doble(tmp_path, monkeypatch):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    d2 = _missing_in_laudus(root, line_no=2)

    from pipeline.importers import laudus_run
    boom = {"raise": True}
    orig_git = laudus_run.git_commit_push

    def flaky_git(root_, paths, msg):
        if boom["raise"]:
            raise RuntimeError("deploy key rechazada")
        return orig_git(root_, paths, msg)

    monkeypatch.setattr(laudus_run, "git_commit_push", flaky_git)

    items = [
        {"discrepancy_id": d1, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
        {"discrepancy_id": d2, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
    ]
    with pytest.raises(AnnotationFailed):
        _resolve(root, items)
    # rollback: nada escrito, ninguna resolución, ambas abiertas
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 2
    assert _resolution_lines(root) == []

    # retry con git sano → sin doble-conteo (dedup + rollback previo garantizan una sola tx c/u)
    boom["raise"] = False
    _resolve(root, items)
    files = _manual_files(root)
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert content.count(f'ref_discrepancy_id: "{d1}"') == 1
    assert content.count(f'ref_discrepancy_id: "{d2}"') == 1
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 0


# ── AC4: 2 anotaciones misma cuenta+mes → ambas en UN archivo (un read/un write) ─


def test_ac4_misma_cuenta_mes_ambas_presentes(tmp_path):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1, date="2026-03-10")
    d2 = _missing_in_laudus(root, line_no=2, date="2026-03-25")
    _resolve(root, [
        {"discrepancy_id": d1, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
        {"discrepancy_id": d2, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
    ])
    files = _manual_files(root)
    assert len(files) == 1                                   # misma cuenta+mes → un solo archivo
    content = files[0].read_text(encoding="utf-8")
    assert f'ref_discrepancy_id: "{d1}"' in content          # ninguna se pierde (no lost-update)
    assert f'ref_discrepancy_id: "{d2}"' in content


# ── AC5: dedup por ref_discrepancy_id (motor batch corrido dos veces) ───────────


def test_ac5_dedup_por_ref(tmp_path):
    root = _root(tmp_path)
    did = _missing_in_laudus(root, line_no=1)
    disc = next(e for e in _iter(root) if e.get("discrepancy_id") == did)
    imp = _importer(root)
    # correr el motor dos veces con el mismo item → la entry aparece una sola vez (idempotente)
    reconcile_mod.annotate_discrepancies_batch(
        [(disc, "Expenses:EAG:Super")], importer=imp, ledger_root=root, ts=_TS)
    reconcile_mod.annotate_discrepancies_batch(
        [(disc, "Expenses:EAG:Super")], importer=imp, ledger_root=root, ts=_TS)
    content = _manual_files(root)[0].read_text(encoding="utf-8")
    assert content.count(f'ref_discrepancy_id: "{did}"') == 1


def test_ac5_service_retry_ventana_crash(tmp_path):
    """Ventana crash-entre-push-y-append: tx commiteada, resolución NO appendeada. Retry no duplica."""
    root = _root(tmp_path)
    did = _missing_in_laudus(root, line_no=1)
    items = [{"discrepancy_id": did, "action": "confirm-cartola-only",
              "category_account": "Expenses:EAG:Super"}]
    _resolve(root, items)
    # simular el crash: borrar la línea de resolución (la tx queda en manual/)
    p = _jsonl(root)
    kept = [l for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip() and not json.loads(l).get("ref_discrepancy_id")]
    p.write_text("\n".join(kept) + "\n", encoding="utf-8")
    assert read_discrepancies(path=p)["summary"]["total"] == 1   # reabierta
    # retry: dedup evita 2ª tx; la resolución se re-appendea
    _resolve(root, items)
    content = _manual_files(root)[0].read_text(encoding="utf-8")
    assert content.count(f'ref_discrepancy_id: "{did}"') == 1
    assert read_discrepancies(path=p)["summary"]["total"] == 0


# ── AC6: un id inválido → preflight aborta el batch entero (todo-o-nada) ────────


def test_ac6_preflight_id_invalido_todo_o_nada(tmp_path):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    d2 = _missing_in_laudus(root, line_no=2)
    with pytest.raises(ResolveError, match="no existe"):
        _resolve(root, [
            {"discrepancy_id": d1, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
            {"discrepancy_id": "no-such-id", "action": "confirm-cartola-only"},
            {"discrepancy_id": d2, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
        ])
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 2


def test_ac6_accion_invalida_para_estado(tmp_path):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    with pytest.raises(ResolveError, match="no permitida"):
        _resolve(root, [{"discrepancy_id": d1, "action": "accept-cartola"}])  # inválida para missing-in-laudus
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1


def test_ac6_ids_duplicados_intra_batch(tmp_path):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    with pytest.raises(ResolveError, match="duplicados"):
        _resolve(root, [
            {"discrepancy_id": d1, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
            {"discrepancy_id": d1, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
        ])
    assert _manual_files(root) == []


def test_justificacion_corta_rechazada(tmp_path):
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    with pytest.raises(ResolveError, match="justification"):
        _resolve(root, [{"discrepancy_id": d1, "action": "confirm-cartola-only",
                         "category_account": "Expenses:EAG:Super"}], justification="corta")
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1


def test_tope_max_batch(tmp_path):
    root = _root(tmp_path)
    items = [{"discrepancy_id": _missing_in_laudus(root, line_no=i), "action": "escalate"}
             for i in range(svc.MAX_BATCH + 1)]
    with pytest.raises(ResolveError, match="excede el máximo"):
        _resolve(root, items)


# ── Batch MIXTO: anotan + baratas → todas cerradas con UN commit ───────────────


def test_batch_mixto_anota_y_baratas(tmp_path, monkeypatch):
    root = _root(tmp_path)
    d_anota = _missing_in_laudus(root, line_no=1)
    d_barata = _missing_in_cartola(root)

    from pipeline.importers import laudus_run
    calls = {"bean": 0, "git": 0}
    orig_bean, orig_git = laudus_run.bean_check, laudus_run.git_commit_push
    monkeypatch.setattr(laudus_run, "bean_check", lambda m: (calls.__setitem__("bean", calls["bean"] + 1), orig_bean(m))[1])
    monkeypatch.setattr(laudus_run, "git_commit_push", lambda r, p, m: (calls.__setitem__("git", calls["git"] + 1), orig_git(r, p, m))[1])

    out = _resolve(root, [
        {"discrepancy_id": d_anota, "action": "confirm-cartola-only", "category_account": "Expenses:EAG:Super"},
        {"discrepancy_id": d_barata, "action": "confirm-laudus-only"},
    ])
    assert calls["bean"] == 1 and calls["git"] == 1           # solo la anotación pasa por bean/git
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 0   # ambas cerradas
    # solo la anotación escribe al ledger; la barata cierra sin tocar manual/
    files = _manual_files(root)
    assert len(files) == 1 and f'ref_discrepancy_id: "{d_anota}"' in files[0].read_text(encoding="utf-8")
    by_id = {r["discrepancy_id"]: r for r in out["results"]}
    assert by_id[d_anota]["status"] == "resolved" and by_id[d_barata]["status"] == "resolved"


# ── Batch SOLO-BARATAS: sin bean_check ni git (nada que anotar) ────────────────


def test_batch_solo_baratas_sin_bean_check_ni_git(tmp_path, monkeypatch):
    root = _root(tmp_path)
    d1 = _missing_in_cartola(root, je_id="JE1")
    d2 = _missing_in_cartola(root, je_id="JE2")

    from pipeline.importers import laudus_run
    calls = {"bean": 0, "git": 0}
    monkeypatch.setattr(laudus_run, "bean_check", lambda m: (calls.__setitem__("bean", 1), (True, ""))[1])
    monkeypatch.setattr(laudus_run, "git_commit_push", lambda r, p, m: calls.__setitem__("git", 1))

    out = _resolve(root, [
        {"discrepancy_id": d1, "action": "confirm-laudus-only"},
        {"discrepancy_id": d2, "action": "confirm-laudus-only"},
    ])
    assert calls == {"bean": 0, "git": 0}                     # nada que anotar → no toca el ledger/git
    assert out["git_commit_sha"] is None
    assert _manual_files(root) == []
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 0


def test_batch_todo_escalate_sin_justificacion(tmp_path):
    """`escalate` no cierra ni exige justificación; un batch todo-escalate no requiere justificación común."""
    root = _root(tmp_path)
    d1 = _missing_in_laudus(root, line_no=1)
    out = resolve_batch([{"discrepancy_id": d1, "action": "escalate"}],
                        justification=None, user_email="c@test.com", now_iso=_TS,
                        path=_jsonl(root), ledger_root=root, importer=_importer(root))
    assert out["results"][0]["status"] == "escalated"
    assert read_discrepancies(path=_jsonl(root))["summary"]["total"] == 1   # escalate no cierra


def _iter(root):
    p = _jsonl(root)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

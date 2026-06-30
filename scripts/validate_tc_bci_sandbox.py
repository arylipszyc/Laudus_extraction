"""Validación sandbox del desglose TC (Goal A) contra la cartola BCI 2026-04 real.

NO toca el ledger real: copia todo a un sandbox temporal, parcha el bank_account_id
del staging, corre correct_tc_cartola y reporta el cuadre. Sin push (IMPORTER_GIT_ENABLED
queda off → git_commit_push es no-op).

Uso (desde la raíz del repo):
    PYTHONUTF8=1 venv/Scripts/python.exe scripts/validate_tc_bci_sandbox.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

# La raíz del repo debe estar en sys.path para importar `backend.*` / `pipeline.*`
# (pytest lo hace solo; un script suelto no).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beancount import loader
from beancount.core import data

from backend.app.api.v1.cartolas.service import _build_importer
from pipeline.importers.tc_correction import correct_tc_cartola

BATCH_ID = "58431cba-29d2-41be-9313-d1867e8d3804"
BANK_ACCOUNT_ID = "e919b1db-be7d-430c-9f40-60fc58ae2bcb"  # BCI Visa Infinity 1027 (accounts.beancount:903)
TC_REAL = "Liabilities:EAG:TC:Real:Tc1027VisaInfinity"
BANK_CHARGES = "Expenses:EAG:GastosBancarios-430003"
EXPECTED_CLOSING = Decimal("-3219948")  # criterio #1 del spec (hoy, pre-fix, daba -3.213.153)

os.environ.pop("IMPORTER_GIT_ENABLED", None)  # asegura no-op de git en el sandbox

repo_root = Path(__file__).resolve().parents[1]
real_ledger = repo_root / "ledger"

# 1) sandbox: copia el ledger completo a un temp aislado
sandbox = Path(tempfile.mkdtemp(prefix="tc-validate-")) / "ledger"
shutil.copytree(real_ledger, sandbox)
print(f"[1] sandbox: {sandbox}")

# 2) parcha el bank_account_id del staging (la cartola real no lo trae apuntado a la cuenta)
staging = sandbox / "imports" / "cartolas" / "_staging" / f"{BATCH_ID}.cartola.json"
doc = json.loads(staging.read_text(encoding="utf-8"))
doc["source"]["bank_account_id"] = BANK_ACCOUNT_ID
staging.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[2] staging parchado → bank_account_id={BANK_ACCOUNT_ID}")

# 3) corre la corrección TC
importer = _build_importer(sandbox)
res = correct_tc_cartola(BATCH_ID, importer, sandbox, ts="2026-06-29T00:00:00Z")
print(f"[3] correct_tc_cartola → status={res['status']} fx={res['fx']} "
      f"purchases={res['purchases']} payments={res['payments']} "
      f"opening_emitted={res['opening_emitted']}")
print(f"    reason={res.get('reason')}")

# 4) inspecciona el ledger resultante.
# OJO: GastosBancarios y otras cuentas son GLOBALES (acumulan cargos Laudus de todo el año).
# Para validar esta cartola hay que medir el APORTE de esta corrida, no el saldo total de la cuenta.
# Aislamos los asientos por su metadata `source: cartola-tc` (la marca de nuestro builder).
entries, errors, _ = loader.load_file(str(sandbox / "main.beancount"))
if errors:
    print(f"    !! bean-check errors: {len(errors)} (primero: {errors[0]})")


def sums(account: str) -> tuple[Decimal, Decimal]:
    """(saldo TOTAL de la cuenta, aporte SOLO de esta cartola)."""
    total = cartola = Decimal(0)
    for e in entries:
        if isinstance(e, data.Transaction):
            is_cartola = (e.meta or {}).get("source") == "cartola-tc"
            for p in e.postings:
                if p.account == account and p.units is not None:
                    total += p.units.number
                    if is_cartola:
                        cartola += p.units.number
    return total, cartola


tc_real_total, tc_real_cartola = sums(TC_REAL)
charges_total, charges_cartola = sums(BANK_CHARGES)

print("\n=== VEREDICTO ===")
print(f"  TC:Real (cuenta nueva, solo esta cartola) = {tc_real_total:>16,}  (esperado {EXPECTED_CLOSING:>14,})")
print(f"  GastosBancarios — TOTAL de la cuenta      = {charges_total:>16,}  (cargos Laudus de TODO el año)")
print(f"  GastosBancarios — aporte de esta cartola  = {charges_cartola:>16,}  (esperado 6,795 = 781 + 6,014)")
print(f"  unmapped = {res['unmapped']}")
ok_closing = tc_real_total == EXPECTED_CLOSING
ok_charges = charges_cartola == Decimal("6795")
ok_unmapped = res["unmapped"] == []
print(f"\n  #1 TC:Real == -closing           : {'PASS' if ok_closing else 'FAIL'}")
print(f"  #2 cargos de la cartola == 6,795 : {'PASS' if ok_charges else 'FAIL'}")
print(f"  #4 unmapped == []                : {'PASS' if ok_unmapped else 'FAIL'}")
print(f"\n  sandbox dejado en: {sandbox}  (borralo cuando termines de inspeccionar)")

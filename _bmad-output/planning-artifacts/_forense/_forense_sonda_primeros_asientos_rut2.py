"""Sonda read-only sobre los primeros asientos del libro RUT2 (Story 12.4, Task 0).

Decide la fecha de corte y la FORMA de la apertura directo de Laudus (decisión Ary
2026-07-10 — sin contador). NO escribe nada: ni ledger/, ni git, ni import-log.

Responde (story 12.4 AC1, Task 0 a-f):
  (a) fecha del primer asiento del libro = fecha de corte
  (b) forma de la apertura: ¿JE real (journalentryid != 0) o filas sintéticas id==0
      que el writer DROPEA (beancount_writer._rows_to_jes)?
  (c) ¿la apertura usa la cuenta 211005 (Liabilities:FFCC:Apertura-211005)?
  (d) ¿hay asientos con fecha <= 2020-12-31? (los opens RUT2 son 2020-12-31)
  (e) ¿la cuenta "13" tiene movimientos? (_min_account_number la excluiría del fetch)
  (f) actividad no-CLP en las cuentas cash-US$ abiertas solo-CLP (111003/115007/613007)

Extra (dry-run de ruteo): codes presentes en los datos que NO están en el índice
scoped del libro → predicción de cuarentena (AC5 espera ≈ 0).

Uso (desde la raíz del repo, con LAUDUS_COMPANYVATID_RUT2 en .env):
    PYTHONUTF8=1 python _bmad-output/planning-artifacts/_forense_sonda_primeros_asientos_rut2.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from pipeline.config.laudus_config import get_book, get_endpoints  # noqa: E402
from pipeline.models import map_ledger_row  # noqa: E402
from pipeline.services.laudus_service import verify_book_identity  # noqa: E402
from pipeline.services.ledger_service import fetch_ledger  # noqa: E402
from pipeline.writers.beancount_writer import load_account_index  # noqa: E402

# Rango deliberadamente ancho para capturar el PRIMER asiento del libro, sea cual sea.
DATE_FROM = "2000-01-01"
DATE_TO = "2030-12-31"
# accountNumberFrom="1" a propósito (NO _min_account_number): la sonda debe ver la
# cuenta "13" si tiene movimientos — el fetch de prod con "111001" la excluiría.
ACCOUNT_FROM = "1"

CASH_USD_SOLO_CLP = {"111003", "115007", "613007"}  # defer 12.3: opens solo-CLP


def main() -> None:
    book = get_book("RUT2")

    print(f"== Sonda RUT2 — verify_book_identity (espera {book.expected_root_name!r}) ==")
    verify_book_identity(book)  # aborta con BookIdentityError si el VAT apunta a otro libro
    print("   identidad OK\n")

    cfg = get_endpoints(DATE_FROM, DATE_TO)["GET_LEDGER"]
    cfg["params"]["accountNumberFrom"] = ACCOUNT_FROM
    raw = fetch_ledger(cfg["url"], cfg["params"], book=book)
    if raw is None:
        raise SystemExit("fetch_ledger devolvió None (auth/HTTP) — sin datos, abortando")
    rows = [map_ledger_row(item, DATE_TO) for item in raw]
    print(f"== Filas crudas del ledger RUT2 [{DATE_FROM}..{DATE_TO}]: {len(rows)} ==\n")
    if not rows:
        raise SystemExit("El libro RUT2 no devolvió filas — nada que analizar")

    def d(row) -> str:
        return str(row.get("date", ""))[:10]

    # (a) fecha de corte
    dates = sorted({d(r) for r in rows if d(r)})
    print(f"(a) FECHA DE CORTE: primer asiento = {dates[0]} | último = {dates[-1]}")
    per_year = Counter(dt[:4] for dt in (d(r) for r in rows) if dt)
    print(f"    filas por año: {dict(sorted(per_year.items()))}\n")

    # (b) forma de la apertura — filas que el writer DROPEARÍA
    synthetic = [r for r in rows if r.get("journalentryid") in (0, "0", None)]
    print(f"(b) FILAS SINTÉTICAS (journalentryid==0/None, el writer las DROPEA): {len(synthetic)}")
    for r in synthetic[:15]:
        print(f"    {d(r)}  cta {r['accountnumber']:>7}  D-C {Decimal(str(r['debit'])) - Decimal(str(r['credit']))}  {str(r.get('description',''))[:60]!r}")
    if len(synthetic) > 15:
        print(f"    ... y {len(synthetic) - 15} más")
    print()

    # JEs del primer día (candidatos a asiento de apertura real)
    first_day = dates[0]
    by_je: dict[str, list] = defaultdict(list)
    for r in rows:
        if d(r) == first_day and r.get("journalentryid") not in (0, "0", None):
            by_je[str(r["journalentryid"])].append(r)
    print(f"    JEs REALES del primer día ({first_day}): {len(by_je)}")
    for je_id, legs in sorted(by_je.items(), key=lambda kv: int(kv[0]))[:5]:
        total = sum(Decimal(str(x["debit"])) - Decimal(str(x["credit"])) for x in legs)
        descs = {str(x.get("description", ""))[:50] for x in legs}
        print(f"    JE id={je_id}  legs={len(legs)}  suma D-C={total}  desc={sorted(descs)[:2]!r}")
        for leg in legs[:12]:
            print(f"       cta {leg['accountnumber']:>7}  {Decimal(str(leg['debit'])) - Decimal(str(leg['credit']))}")
        if len(legs) > 12:
            print(f"       ... y {len(legs) - 12} legs más")
    print()

    # (c) uso de 211005
    r211005 = [r for r in rows if str(r.get("accountnumber")) == "211005"]
    print(f"(c) FILAS EN 211005 'Apertura': {len(r211005)}")
    for r in r211005[:10]:
        print(f"    {d(r)}  je={r['journalentryid']}  D-C {Decimal(str(r['debit'])) - Decimal(str(r['credit']))}  {str(r.get('description',''))[:60]!r}")
    print()

    # (d) asientos <= 2020-12-31 (fecha de los opens RUT2)
    early = [r for r in rows if d(r) <= "2020-12-31"]
    print(f"(d) FILAS CON FECHA <= 2020-12-31 (opens RUT2 son 2020-12-31): {len(early)}")
    if early:
        print(f"    fechas: {sorted({d(r) for r in early})[:10]}")
    print()

    # (e) movimientos en la cuenta "13"
    r13 = [r for r in rows if str(r.get("accountnumber")) == "13"]
    print(f"(e) FILAS EN CUENTA '13' (excluida por accountNumberFrom='111001' en prod): {len(r13)}")
    for r in r13[:5]:
        print(f"    {d(r)}  je={r['journalentryid']}  D-C {Decimal(str(r['debit'])) - Decimal(str(r['credit']))}")
    print()

    # (f) monedas + actividad en las cash-US$ solo-CLP
    currencies = Counter(str(r.get("currencycode")) for r in rows)
    print(f"(f) MONEDAS en el libro: {dict(currencies)}")
    usd_cash = [r for r in rows if str(r.get("accountnumber")) in CASH_USD_SOLO_CLP]
    non_clp_cash = [r for r in usd_cash if str(r.get("currencycode")) not in ("CLP", "")]
    print(f"    filas en cuentas cash-US$ solo-CLP {sorted(CASH_USD_SOLO_CLP)}: "
          f"{len(usd_cash)} (no-CLP: {len(non_clp_cash)})")
    for r in non_clp_cash[:5]:
        print(f"    {d(r)}  cta {r['accountnumber']}  {r['currencycode']}  parity={r['paritytomaincurrency']}")
    print()

    # Dry-run de ruteo: predicción de cuarentena (AC5)
    index = load_account_index(REPO / "ledger" / "accounts.beancount", book)
    codes_in_data = {str(r.get("accountnumber")) for r in rows
                     if r.get("journalentryid") not in (0, "0", None)}
    unknown = sorted(codes_in_data - set(index))
    print(f"(+) DRY-RUN CUARENTENA: {len(codes_in_data)} codes distintos en los datos; "
          f"{len(unknown)} SIN cuenta en el índice scoped RUT2")
    for code in unknown[:20]:
        n = sum(1 for r in rows if str(r.get("accountnumber")) == code)
        print(f"    code {code}: {n} filas")
    print()

    # Balance por sub-entidad (tamaño del plug §3.5) — sobre filas REALES (lo que importaría)
    real = [r for r in rows if r.get("journalentryid") not in (0, "0", None)]
    ffcc = sum(Decimal(str(r["debit"])) - Decimal(str(r["credit"]))
               for r in real if str(r["accountnumber"])[:1] in "1234")
    jab = sum(Decimal(str(r["debit"])) - Decimal(str(r["credit"]))
              for r in real if str(r["accountnumber"])[:1] in "678")
    total = sum(Decimal(str(r["debit"])) - Decimal(str(r["credit"])) for r in real)
    n_jes = len({str(r["journalentryid"]) for r in real})
    print(f"(+) BALANCE filas reales: {len(real)} filas / {n_jes} JEs | suma total D-C = {total}")
    print(f"    suma FFCC (raíces 1-4) = {ffcc}  ← plug Equity:FFCC:Apertura si ≠ 0")
    print(f"    suma JAB  (raíces 6-8) = {jab}  ← plug Equity:JAB:Apertura si ≠ 0")
    print("\n== FIN — la sonda no escribió nada ==")


if __name__ == "__main__":
    main()

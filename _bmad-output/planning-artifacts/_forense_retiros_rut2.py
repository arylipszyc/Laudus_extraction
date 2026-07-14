"""Sondeo forense: cuentas por cobrar / retiros del Fondo Común (FFCC).

Evidencia del hallazgo de la story 13.1: el ciclo préstamo→reparto de las cuentas
`Assets:FFCC:*-115xxx` (categoria3="CUENTAS POR COBRAR") cerraba a saldo 0 en
2021-2022 pero se rompe desde 2023 (los saldos se acumulan; la mayoría queda
acreedor = reparto > retiro). Read-only; no escribe nada.

Uso:  PYTHONUTF8=1 venv/Scripts/python.exe _bmad-output/planning-artifacts/_forense_retiros_rut2.py
"""
import re
from collections import defaultdict

from beancount import loader
from beancount.core.data import Transaction

entries, errors, _ = loader.load_file("ledger/main.beancount")
print("load errors:", len(errors))

# Cuentas por cobrar de FFCC: 2º segmento FFCC + código 115xxx.
rx = re.compile(r"^Assets:FFCC:.*-(115\d{3})$")


def short(acc):
    return acc.split(":")[-1]


# acc -> año -> [debitos(+), creditos(-)]
flow = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
for e in entries:
    if not isinstance(e, Transaction):
        continue
    for p in e.postings:
        if not rx.match(p.account) or p.units is None:
            continue
        n = float(p.units.number)
        flow[p.account][e.date.year][0 if n >= 0 else 1] += n

years = sorted({y for a in flow for y in flow[a]})
print("años:", years, "\n")
for a in sorted(flow, key=short):
    bal, moved, cols = 0.0, False, [f"{short(a):34s}"]
    for y in years:
        deb, cred = flow[a].get(y, [0.0, 0.0])
        bal += deb + cred
        moved = moved or bool(deb or cred)
        cols.append(f"{y}: ret={deb/1e6:8.1f}M rep={cred/1e6:8.1f}M saldo={bal/1e6:8.1f}M")
    if moved:
        print("\n  ".join(cols) + "\n")

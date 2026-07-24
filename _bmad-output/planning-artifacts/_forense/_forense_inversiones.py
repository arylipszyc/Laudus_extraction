# -*- coding: utf-8 -*-
"""Forense: cuentas de inversion (activos) vs ingresos de inversion.
Caza el patron 'ingreso registrado sin actualizar el activo'."""
import os, re, glob, sys

ROOT = r"c:\dev\bmad-workspace-new\family-office-eag\ledger"
LAUDUS = sorted(glob.glob(os.path.join(ROOT, "imports", "laudus", "*.beancount")))
ACCOUNTS = os.path.join(ROOT, "accounts.beancount")
OPENING = os.path.join(ROOT, "opening-2021.beancount")

# ---- 1. clasificar cuentas desde accounts.beancount (metadata-driven) ----
invest_asset, invest_income = set(), set()
cur, meta = None, {}
def flush():
    global cur, meta
    if cur:
        name = cur
        code = name.rsplit("-", 1)[-1] if "-" in name else ""
        is_inv = (meta.get("bank_account_type") == "cta_inversiones"
                  or meta.get("laudus_categoria3") == "INVERSIONES"
                  or re.search(r"Inversi|FmBci|Mbi|Fip|Hemanext|NuevoCiclo|FondoCom|TierraYHuertos", name))
        if name.startswith("Assets") and (is_inv or code.startswith("113") or code.startswith("115")):
            invest_asset.add(name)
        if name.startswith("Income") and (is_inv or code.startswith("510")
                or code in {"310006","310009","310010","310011","310013","310015","310016",
                            "310025","310027","310029","310059","310091","310095"}):
            invest_income.add(name)
    cur, meta = None, {}

for line in open(ACCOUNTS, encoding="utf-8"):
    m = re.match(r"\d{4}-\d{2}-\d{2} open (\S+)", line)
    if m:
        flush(); cur = m.group(1); continue
    mm = re.match(r"\s+(\w+):\s*\"?([^\"]*)\"?", line)
    if mm and cur: meta[mm.group(1)] = mm.group(2).strip()
flush()

# ---- 2. parsear transacciones ----
txn_re = re.compile(r'^(\d{4}-\d{2}-\d{2}) [*!] "(.*)"')
post_re = re.compile(r'^\s+([A-Z][A-Za-z0-9:_-]+)\s+(-?[\d.]+)\s+(CLP|USD)')
def parse(files):
    txns = []
    for f in files:
        cur = None
        for line in open(f, encoding="utf-8"):
            t = txn_re.match(line)
            if t:
                cur = {"date": t.group(1), "narr": t.group(2), "post": [], "file": os.path.basename(f)}
                txns.append(cur); continue
            p = post_re.match(line)
            if p and cur is not None:
                cur["post"].append((p.group(1), float(p.group(2)), p.group(3)))
            elif line.strip() == "" :
                cur = None
    return txns

txns = parse(LAUDUS)
opening = parse([OPENING]) if os.path.exists(OPENING) else []

# ---- 3. saldos por cuenta de inversion (con saldo minimo corrido) ----
print("="*90)
print("SECCION 1 — Saldos de cuentas de INVERSION (activo). neg = imposible para activo")
print("="*90)
bal = {}
for t in opening + txns:
    for a, amt, cur_ in t["post"]:
        if a in invest_asset: bal[a] = bal.get(a, 0) + amt
for a in sorted(bal, key=lambda x: bal[x]):
    flag = "  <-- NEGATIVO" if bal[a] < -1 else ""
    print(f"{bal[a]:>20,.0f}  {a}{flag}")

# ---- 4. cazar 'rescate/retiro/venta' que NO reducen un activo de inversion ----
KW = re.compile(r"rescate|retiro|venta|liquid|redenc|vencimiento|reembolso|devoluc|amortiz|capital", re.I)
print("\n" + "="*90)
print("SECCION 2 — Asientos con narracion de salida de inversion")
print("  OK   = reduce un activo de inversion (correcto)")
print("  SOSP = NO toca activo de inversion (posible ingreso mal cargado sin bajar el activo)")
print("="*90)
sosp = []
for t in txns:
    if not KW.search(t["narr"]): continue
    touches_inv_asset_down = any(a in invest_asset and amt < 0 for a, amt, _ in t["post"])
    touches_inv_income = any(a in invest_income for a, amt, _ in t["post"])
    if not touches_inv_asset_down and (touches_inv_income or "rescate" in t["narr"].lower()):
        sosp.append(t)
print(f"\nSOSPECHOSOS (narracion de salida, sin bajar activo de inversion): {len(sosp)}")
for t in sosp[:60]:
    accts = ", ".join(f"{a.split(':')[-1]} {amt:+,.0f}" for a, amt, _ in t["post"])
    print(f"  {t['date']} [{t['file']}] {t['narr'][:55]}")
    print(f"        -> {accts}")

# ---- 5. ingresos de inversion: ¿el asiento tambien mueve el activo? ----
print("\n" + "="*90)
print("SECCION 3 — Postings a cuentas de INGRESO de inversion")
print("  Para cada uno: ¿el mismo asiento reduce un activo de inversion?")
print("="*90)
inc_tot = {}
inc_no_asset_tot = {}
for t in txns:
    inc_here = [(a, amt) for a, amt, _ in t["post"] if a in invest_income]
    if not inc_here: continue
    asset_moves = any(a in invest_asset for a, amt, _ in t["post"])
    for a, amt in inc_here:
        inc_tot[a] = inc_tot.get(a, 0) + amt
        if not asset_moves:
            inc_no_asset_tot[a] = inc_no_asset_tot.get(a, 0) + amt
print(f"\n{'INGRESO (signo contable)':>22} {'sin tocar activo':>18}  cuenta")
for a in sorted(inc_tot, key=lambda x: inc_tot[x]):
    print(f"{inc_tot[a]:>22,.0f} {inc_no_asset_tot.get(a,0):>18,.0f}  {a}")
print("\n(Nota: ingreso sin tocar activo PUEDE ser legitimo = dividendo/interes en efectivo.")
print(" Es SOSPECHOSO cuando la narracion dice rescate/venta/retiro de capital.)")

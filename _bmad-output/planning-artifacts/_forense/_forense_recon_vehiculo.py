# -*- coding: utf-8 -*-
"""Reconciliacion por vehiculo de inversion (solo EAG).
aportes (sube activo) | retiros via activo | retiros via ingreso | saldo actual."""
import os, re, glob

ROOT = r"c:\dev\bmad-workspace-new\family-office-eag\ledger"
LAUDUS = sorted(glob.glob(os.path.join(ROOT, "imports", "laudus", "*.beancount")))
OPENING = os.path.join(ROOT, "opening-2021.beancount")

txn_re = re.compile(r'^(\d{4}-\d{2}-\d{2}) [*!] "(.*)"')
post_re = re.compile(r'^\s+([A-Z][A-Za-z0-9:_-]+)\s+(-?[\d.]+)\s+(CLP|USD)')
def parse(files):
    txns = []
    for f in files:
        cur = None
        for line in open(f, encoding="utf-8"):
            t = txn_re.match(line)
            if t:
                cur = {"date": t.group(1), "narr": t.group(2), "post": []}
                txns.append(cur); continue
            p = post_re.match(line)
            if p and cur is not None:
                cur["post"].append((p.group(1), float(p.group(2))))
            elif line.strip() == "":
                cur = None
    return txns
txns = parse([OPENING] + LAUDUS) if os.path.exists(OPENING) else parse(LAUDUS)

# vehiculo -> (cuentas activo EAG, cuentas ingreso EAG)
VEH = {
 "Tecnion":     (["InvTecnionLimitada-113018","TecnionInternacional-113016","TecninLlc-113017"], ["RetirosTecnin-310013"]),
 "Nuevo Ciclo": (["InversionesNuevoCiclo-115016"], ["RetirosInvNuevoCiclo-310016"]),
 "MBI":         (["MbiSecuencia0-113011","MbiSecuencia2-113013"], ["Mbi-310027"]),
 "JB":          (["BancoJuliusBaer03133171-111017"], ["Jb-310029"]),
 "BCI FM":      (["FmBciAltoPatrimonio-113001","FmBciCompetitivoSerieAp0-113002",
                  "FmBciExpressSerieClsica-113003","FmBciCompetitivoSerieClass0-113004",
                  "FmBciRealStateLmvIii-113005"], ["FondosMutuosBci-310025"]),
}
def hit(acct, keys): return any(k in acct for k in keys)

print(f"{'VEHICULO':<13}{'aportes(+act)':>16}{'retiro via act':>16}{'retiro via ING':>16}{'saldo activo hoy':>18}")
print("-"*79)
for v,(assets,incomes) in VEH.items():
    ap=ret_act=ret_inc=bal=0.0
    for t in txns:
        for a,amt in t["post"]:
            if hit(a, assets):
                bal+=amt
                if amt>0: ap+=amt
                else: ret_act+=amt
            if hit(a, incomes) and amt<0:
                ret_inc+=amt
    print(f"{v:<13}{ap:>16,.0f}{ret_act:>16,.0f}{-ret_inc:>16,.0f}{bal:>18,.0f}")
print("-"*79)
print("retiro via ING = plata que SALIO de la inversion pero se cargo a una cuenta de INGRESO")
print("(para vehiculos = inversion, eso debio bajar el activo; el saldo de hoy esta inflado por ese monto)")

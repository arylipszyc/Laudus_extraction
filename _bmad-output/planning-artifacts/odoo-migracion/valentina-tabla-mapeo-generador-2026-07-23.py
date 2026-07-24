import csv, re, collections
from beancount import loader
from beancount.core import data
from beancount.core.number import Decimal
entries, errors, opts = loader.load_file("ledger/main.beancount")

bal=collections.defaultdict(lambda:Decimal(0))
for e in entries:
    if isinstance(e,data.Transaction):
        for p in e.postings:
            if p.units and p.units.currency=="CLP": bal[p.account]+=p.units.number

EAG_ENT={"EAG","Jocelyn","Jeannette","Johanna","Jael"}
PROP={"MANTENCION VIA GRIS":"Vía Gris","MANTENCION MOLCO":"Molco","MANTENCION REÑACA":"Reñaca",
 "MANTENCION YATE KEIKI KAI":"Yate Keiki Kai","MANTENCION YATE DESTINY":"Yate Destiny","MANTENCION YATE ALFIN II":"Yate Alfín II",
 "AVION CC-N225AW":"Avión N225AW","AVION CC-N266WW":"Avión N266WW","AVION CC-AJK":"Avión AJK","AVIONES - GASTOS GENERALES":"Aviones (grl)",
 "DEPARTAMENTO MIAMI":"Depto Miami","CANCHA DE GOLF":"Cancha de Golf"}
SOCIOS=["AAG","EAG","DAG","SAG","AZBA","FGK"]
BENEF={"raquel":"Raquel Ventura","jacqueline deutsch":"Jacqueline Deutsch","patricia deutsch":"Patricia Deutsch",
 "gloria jimenez":"Gloria Jiménez"}
APELLIDOS=["alazraki","zeldis","borzutzky","israel"]

def strip_socio(n):
    for s in SOCIOS:
        m=re.match(rf"^{s}\s*-\s*(.*)",n)
        if m: return s, m.group(1).strip()
    return "", n

def norm(n):
    n=n.strip()
    n=re.sub(r'\s+',' ',n)
    return n

rows=[]
for e in entries:
    if not isinstance(e,data.Open): continue
    A=e.account
    typ=A.split(":")[0]
    if typ=="Equity": 
        rows.append(dict(code=e.meta.get("code",""),entity=A.split(":")[1],company="",name=e.meta.get("laudus_account_name",""),
            cat2="",cat3="",bal=int(bal.get(A,0)),odoo="Equity:Apertura",otype="equity",ent="",prop="",socio="",benef="",area="",offshore="",partner="",sinc="",flag="keep")); continue
    m=e.meta; code=m.get("code",""); name=m.get("laudus_account_name",""); c2=m.get("laudus_categoria2","") or ""; c3=m.get("laudus_categoria3","") or ""
    entity=A.split(":")[1]
    company="EAG" if entity in EAG_ENT else "RUT2"
    r=dict(code=code,entity=entity,company=company,name=name,cat2=c2,cat3=c3,bal=int(bal.get(A,0)),
           odoo="",otype="",ent=entity,prop="",socio="",benef="",area="",offshore="",partner="",sinc="",flag="")
    c3u=c3.upper(); nl=name.lower()
    socio,base=strip_socio(name)
    if socio: r["socio"]=socio

    if typ=="Assets":
        r["otype"]="asset"
        if name.startswith("Banco"): r["odoo"]=f"Bancos:{norm(name)}"; r["otype"]="bank"; r["flag"]="keep-1:1"
        elif name.startswith("Caja"): r["odoo"]="Caja "+("USD" if "US$" in name or "US" in name else "CLP")
        elif re.search(r"Retiros(Aag|Eag|Dag|Sag|Azba)",A) or any(k in nl for k in APELLIDOS):
            r["odoo"]="Cuentas corriente socios"; r["otype"]="receivable"
            r["partner"]=name.replace("Retiros","").strip() or name
        elif "OtrosRetirosHijos" in A: r["odoo"]="Cuentas corriente socios"; r["otype"]="receivable"; r["partner"]="Otros hijos"
        elif "prestamo" in nl or "Deudores" in name: r["odoo"]="Préstamos/Deudores a terceros"; r["otype"]="receivable"; r["partner"]=name; r["flag"]="partner-por-deudor"
        elif "LeoPartnership" in A: r["odoo"]="Inversiones:Leo"; r["offshore"]="Leo"; r["flag"]="origen-inv(SPEC)"
        elif "Tauro" in A: r["odoo"]="Inversiones:Tauro"; r["offshore"]="Tauro"; r["flag"]="origen-inv(SPEC)"
        elif "InversionesNuevoCiclo" in A: r["odoo"]="Inversiones:NuevoCiclo"; r["flag"]="origen-inv(SPEC)"
        elif c3u in ("VALORES NEGOCIABLES","INVERSIONES","EMPRESAS INTERNACIONALES") or "InversionesSade" in A:
            r["odoo"]=f"Inversiones:{norm(name)}"; r["offshore"]=norm(name)
            r["flag"]="inversión(F3-valuar)" + ("|NEGATIVO(¿errorB?)" if int(bal.get(A,0))<0 else "")
        elif "ControlYLiquidacin" in A: r["odoo"]="Control y Liquidación"; r["area"]="por-cuenta-de"
        elif "DISPONIBLE" in c3u and (name.startswith("FM BCI") or name.startswith("MBI")):
            r["odoo"]=f"Inversiones:{norm(name)}"; r["offshore"]=norm(name); r["flag"]="inversión-hija(F3)"
        elif c3u=="CUENTAS POR COBRAR": r["odoo"]="Cuentas por cobrar"; r["otype"]="receivable"; r["partner"]=norm(name)
        elif any(k in name for k in ["Fondo Fijo","Fondos por Rendir","Cuentas Corrientes del Personal","Caja"]): r["odoo"]=norm(name)
        elif any(k in c2.upper() for k in ["FONDO","RENDIR","PERSONAL"]): r["odoo"]=norm(name)
        else: r["odoo"]=norm(name); r["flag"]="keep-normalizado"
    elif typ=="Liabilities":
        r["otype"]="liability"; r["odoo"]=norm(name); r["flag"]="keep"
    elif typ=="Income":
        r["otype"]="income"; r["odoo"]=f"Income:{norm(base)}"
        # sinceramiento por naturaleza
        if code=="310011" and "Indumotora" in name: r["sinc"]="REAL(allowlist-dividendo)"
        elif re.search(r"Sueldo|Directorio|Dividendo|Indumotora|Kia|Hyundai|IngresosPorInversiones|DevolucinOficina",A): r["sinc"]="REAL(se queda)"
        elif "Sade" in A: r["sinc"]="APORTE→Assets:InversionesSade"; r["odoo"]="Assets:FFCC:InversionesSade"; r["otype"]="asset"
        elif re.search(r"Retiros|Mbi|Jb|Rescate",A): r["sinc"]="RETIRO→activo origen"
        elif "VentaDeActivos" in A or "VentaAcciones" in A: r["sinc"]="DISPOSICIÓN→baja activo"
        elif "Molco" in A: r["sinc"]="→GASTO(Molco financiamiento)"; r["odoo"]="Expenses:MolcoFinanciamiento"; r["otype"]="expense"
        elif "Devoluci" in name or "Devol" in name: r["sinc"]="REEMBOLSO(se queda)"
        elif "OtrosIngresos" in A: r["sinc"]="MIXTO→regla por-glosa"; r["flag"]="mixto-por-glosa"
        else: r["sinc"]="REAL?(revisar)"; r["flag"]="revisar-ingreso"
    elif typ=="Expenses":
        r["otype"]="expense"
        # TC
        if ":TC:" in A or "T/C" in name: r["odoo"]="Liabilities:TC (desglose Epic6)"; r["otype"]="liability"; r["flag"]="TC-especial"
        elif c3u in PROP: r["odoo"]=f"Gasto:{norm(base)}"; r["prop"]=PROP[c3u]
        elif c3u in ("DONACIONES",): r["odoo"]="Donaciones"; r["partner"]=norm(name); r["flag"]="partner-benef"
        elif c3u in ("SOCIALES",): r["odoo"]="Cuotas y Membresías"; r["partner"]=norm(name); r["flag"]="partner-benef"
        elif c3u in ("REGALOS",): r["odoo"]="Regalos"; r["area"]="ocasión:"+norm(base)
        elif any(k in nl for k in BENEF): 
            for k,v in BENEF.items():
                if k in nl: r["benef"]=v; r["partner"]=v
            r["odoo"]="Asignaciones a personas"
        elif "Impuesto Renta" in name or "Impuesto a la Renta" in name: r["odoo"]="Impuesto Renta"
        elif "Donaciones" in name or "Coronas" in name: r["odoo"]="Donaciones"; r["partner"]=norm(name); r["flag"]="partner-benef"
        else:
            r["odoo"]=f"Gasto:{norm(base)}"
            if c3 and c3u not in PROP: r["area"]=c3
    rows.append(r)

# write CSV
cols=["code","entity","company","name","cat2","cat3","bal","odoo","otype","ent","prop","socio","benef","area","offshore","partner","sinc","flag"]
out="_bmad-output/planning-artifacts/valentina-tabla-mapeo-odoo-2026-07-23.csv"
with open(out,"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
    for r in rows: w.writerow(r)

# summary
print(f"Filas: {len(rows)}  → CSV: {out}")
odoo_accts=collections.Counter(r["odoo"] for r in rows if r["odoo"])
print(f"Cuentas Odoo únicas: {len(odoo_accts)}")
flags=collections.Counter(r["flag"] for r in rows if r["flag"])
print("\nFlags:")
for k,v in flags.most_common(): print(f"  {v:4}  {k}")
# dims
for dim in ["prop","socio","benef","offshore"]:
    vals=sorted(set(r[dim] for r in rows if r[dim]))
    print(f"\ndim {dim} ({len(vals)}): {', '.join(vals)}")

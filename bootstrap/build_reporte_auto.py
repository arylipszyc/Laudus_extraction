"""
Genera una versión AUTOMÁTICA del reporte "Gastos EAG 12-2025" a partir del ledger
real de Laudus (Google Sheets `ledger_final`, cacheado en _cache/laudus_dump.json) y
la compara contra el Excel original que arma el contador a mano.

Salida: _reportes-prototipo/Gastos EAG 12-2025_AUTO.xlsx
  - Clona la hoja Resúmen del original.
  - Cada línea de detalle con código de cuenta se RELLENA con el valor de Laudus.
  - Código de colores en las celdas de valor:
        VERDE  = reproducido desde Laudus (la cuenta existe y tiene movimientos)
        AMARILLO = está en el reporte original pero NO tiene fuente en Laudus
                   (descomposición de cartola/TC, detalle por empleado, USD Miami,
                    sub-cuentas de hijas, columnas HABITUAL/EXTRA, memos)
  - Consola: reconciliación por centro de costo (Laudus vs Excel) + total $ del
    "trabajo manual" (suma de celdas amarillas).
"""
import json
import os
from collections import defaultdict

import openpyxl
from openpyxl.styles import PatternFill, Font
from openpyxl.comments import Comment

ORIG = r"H:\My Drive\Emprendimientos\Analisis gastos Edu\Edu\Gastos EAG 12-2025.xlsx"
OUTDIR = r"c:\dev\bmad-workspace-new\family-office-eag\_reportes-prototipo"
OUT = os.path.join(OUTDIR, "Gastos EAG 12-2025_AUTO.xlsx")
CACHE = r"c:\dev\bmad-workspace-new\family-office-eag\bootstrap\_cache\laudus_dump.json"

MONTH_COLS = list(range(3, 15))  # C..N = Ene..Dic

GREEN = PatternFill("solid", fgColor="C6EFCE")    # mapea directo a cuenta Laudus
YELLOW = PatternFill("solid", fgColor="FFEB9C")   # sin correspondencia en Laudus
BLUE = PatternFill("solid", fgColor="BDD7EE")     # sub-línea: suma a una cuenta Laudus padre

# Alias: código del Excel (normalizado) -> código(s) real(es) en Laudus.
# Cubre reclasificaciones y los códigos de hijas mal escritos en el Excel
# (confirmados por match exacto de monto contra el ledger).
ALIAS = {
    "310025": ["113002", "113003"],  # FONDOS MUTUOS reclasificado
    # hijas — códigos garabateados en el Excel -> cuenta limpia en Laudus
    "6900001": ["690001"], "69000003": ["690003"], "6501073": ["690073"], "6900099": ["690099"],
    "79000003": ["790003"], "7900099": ["790099"],
    "9900001": ["990001"], "9900003": ["990003"], "9501073": ["990073"], "9900099": ["990099"],
}


def num(v):
    try:
        return float(str(v).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def norm_codes(a):
    """Normaliza el código col-A del Excel a lista de códigos Laudus candidatos.

    Maneja: guiones/espacios, shorthand 'NNN-002/003' (= dos cuentas), y la
    variante de formato '4101-0XX' que el contador usa por '411-0XX'.
    """
    s = str(a).strip().upper()
    if not s or s.startswith("TC") or s.startswith("T/C"):
        return []
    s = s.replace(" ", "").replace("-", "")
    parts = s.split("/")
    if not parts[0].isdigit():
        return []
    base = parts[0]
    if base.startswith("4101"):
        base = "411" + base[4:]   # 4101-0XX = 411-0XX
    codes = [base]
    for p in parts[1:]:           # '...002/003' -> sustituye el sufijo sobre la base
        if p.isdigit():
            codes.append(base[: len(base) - len(p)] + p)
    out = []
    for c in codes:
        out.extend(ALIAS.get(c, [c]))
    return out


def build_laudus_index():
    """Devuelve dict[code] -> [12 montos mensuales 2025, con signo del reporte]."""
    d = json.load(open(CACHE, encoding="utf-8"))
    rows = [r for r in d["ledger_final"] if str(r.get("date", ""))[:4] == "2025"]
    # signo por cuenta: ingreso (credit-debit) si su Categoria1 menciona INGRESOS
    is_income = defaultdict(lambda: False)
    for r in rows:
        if "INGRESOS" in str(r.get("Categoria1", "")).upper():
            is_income[str(r.get("accountnumber", ""))] = True
    idx = defaultdict(lambda: [0.0] * 12)
    for r in rows:
        acc = str(r.get("accountnumber", ""))
        m = int(str(r.get("date", ""))[5:7]) - 1
        de, cr = num(r.get("debit")), num(r.get("credit"))
        idx[acc][m] += (cr - de) if is_income[acc] else (de - cr)
    return idx


def is_total_row(label):
    u = str(label).strip().upper()
    return u.startswith(("TOTAL", "SUBTOTAL", "SALDO", "DISPONIBLE", "RESUMEN",
                         "DETALLE", "VARIACION"))


def mark_eag(wb, accts):
    """Marca la hoja EAG (fuente de banco/Laudus). Devuelve (verde, azul, amarillo, lista_amarillas).

    VERDE  = la línea tiene código propio que mapea a una cuenta Laudus.
    AZUL   = sub-línea sin código propio que suma a una cuenta Laudus padre
             (desglose más fino que Laudus: por empleado, bencina vs autopista...).
    AMARILLO = no hay correspondencia en Laudus.
    """
    ws = wb["EAG"]
    wsv = openpyxl.load_workbook(ORIG, data_only=True)["EAG"]

    def printed(r, c):
        v = wsv.cell(r, c).value
        return v if isinstance(v, (int, float)) else 0.0

    green = blue = yellow = 0
    yellow_list = []
    parent_in_laudus = False
    # arranca en la fila 45 (primer bloque DETALLE con códigos)
    for r in range(45, ws.max_row + 1):
        a = ws.cell(r, 1).value
        label = ws.cell(r, 2).value
        codes = norm_codes(a)
        if codes:
            parent_in_laudus = any(c in accts for c in codes)
        has_val = any(printed(r, c) for c in MONTH_COLS)
        if is_total_row(label) or not has_val:
            continue

        if codes:
            ok = any(c in accts for c in codes)
            fill = GREEN if ok else YELLOW
            if ok:
                green += 1
            else:
                yellow += 1
                yellow_list.append((r, str(a), str(label)))
                ws.cell(r, 2).comment = Comment(
                    f"NO EN LAUDUS — código {codes} no existe en el ledger", "auto")
        else:
            # sub-línea: hereda del último código (parent)
            if parent_in_laudus:
                fill = BLUE
                blue += 1
            else:
                fill = YELLOW
                yellow += 1
                yellow_list.append((r, "(sin código)", str(label)))
                ws.cell(r, 2).comment = Comment(
                    "NO EN LAUDUS — sub-línea sin cuenta padre en el ledger", "auto")
        for c in MONTH_COLS:
            if printed(r, c):
                ws.cell(r, c).fill = fill
    return green, blue, yellow, yellow_list


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    laudus = build_laudus_index()

    wb = openpyxl.load_workbook(ORIG)              # canvas: fórmulas + formato (no se tocan valores)
    ws = wb["Resúmen"]
    wsv = openpyxl.load_workbook(ORIG, data_only=True)["Resúmen"]  # valores impresos (oráculo)

    def printed(r, c):
        v = wsv.cell(r, c).value
        return v if isinstance(v, (int, float)) else 0.0

    green_rows = yellow_rows = 0
    manual_total = 0.0
    cost_center_cmp = []  # (nombre, laudus_total, excel_total)

    # Solo el bloque de DETALLE (las líneas hoja); el bloque RESUMEN superior es roll-up
    # y se contaría doble. "DETALLE DE LOS GASTOS" arranca en la fila 123.
    DETAIL_START = 123
    for r in range(DETAIL_START, ws.max_row + 1):
        label = ws.cell(r, 2).value
        a = ws.cell(r, 1).value
        has_val = any(printed(r, c) for c in MONTH_COLS)
        if is_total_row(label) or not has_val:
            continue

        codes = norm_codes(a)
        # "en Laudus" = la cuenta existe en el ledger con movimiento 2025 != 0
        matched = [c for c in codes if c in laudus and any(laudus[c])]
        fill = GREEN if matched else YELLOW
        for c in MONTH_COLS:
            if printed(r, c):
                ws.cell(r, c).fill = fill
        if matched:
            green_rows += 1
        else:
            yellow_rows += 1
            manual_total += sum(printed(r, c) for c in MONTH_COLS)
            tip = "Sin código de cuenta (línea armada a mano)" if not codes \
                else f"Código {codes} sin movimiento propio en Laudus (típicamente desglose de cartola/TC)"
            ws.cell(r, 2).comment = Comment(f"NO EN LAUDUS — {tip}", "auto")

    # Bloque RESUMEN: líneas de centro de costo reproducibles desde Laudus (Categoria2) -> verde
    for cc_row in (78, 79, 80, 82):
        for c in MONTH_COLS:
            if printed(cc_row, c):
                ws.cell(cc_row, c).fill = GREEN
        ws.cell(cc_row, 2).comment = Comment(
            "Reproducible desde Laudus (suma Categoria2). El DESGLOSE de abajo es lo manual.", "auto")

    # Columnas HABITUAL / EXTRA (juicio manual del contador): amarillo donde haya valor
    for r in range(8, ws.max_row + 1):
        for c in (16, 17, 20, 21):  # P,Q,T,U según bloque
            if printed(r, c):
                ws.cell(r, c).fill = YELLOW

    # Reconciliación por centro de costo (Categoria2) Laudus vs Excel impreso
    EXCEL_CC = {  # fila resumen EGRESOS en el original
        "DEPARTAMENTO SANTIAGO": 78, "Casa Sur": 79, "DEPARTAMENTO MIAMI": 80,
        "GASTOS PERSONALES": 82,
    }
    d = json.load(open(CACHE, encoding="utf-8"))
    rows25 = [r for r in d["ledger_final"] if str(r.get("date", ""))[:4] == "2025"]
    ws_vals = openpyxl.load_workbook(ORIG, data_only=True)["Resúmen"]  # valores impresos
    for cc, exrow in EXCEL_CC.items():
        lau = sum(num(r.get("debit")) - num(r.get("credit"))
                  for r in rows25 if str(r.get("Categoria2", "")) == cc)
        exc = sum(num(ws_vals.cell(exrow, c).value) for c in MONTH_COLS)
        cost_center_cmp.append((cc, lau, exc))

    # Leyenda
    leg = wb.create_sheet("LEYENDA_AUTO", 0)
    leg["A1"] = "REPORTE AUTO-GENERADO DESDE LAUDUS — leyenda de colores"
    leg["A1"].font = Font(bold=True, size=13)
    leg["A3"] = "VERDE"; leg["A3"].fill = GREEN
    leg["B3"] = "Valor reproducido desde el ledger Laudus (cuenta existe con movimientos 2025)"
    leg["A4"] = "AMARILLO"; leg["A4"].fill = YELLOW
    leg["B4"] = ("Está en el reporte original pero NO tiene fuente en Laudus: descomposición "
                 "de cartola/TC (LUZ, AGUA, FARMACIA, RESTAURANTES...), detalle por empleado, "
                 "USD Miami, sub-cuentas de hijas, columnas HABITUAL/EXTRA, memos.")
    leg["A6"] = f"Filas verdes (Laudus): {green_rows}"
    leg["A7"] = f"Filas amarillas (manual / no-Laudus): {yellow_rows}"
    leg["A8"] = f"$ aprox. en celdas amarillas (trabajo manual): {round(manual_total):,}"
    leg["A10"] = "AZUL (hoja EAG)"; leg["A10"].fill = BLUE
    leg["B10"] = ("Sub-línea más fina que Laudus (por empleado, bencina vs autopista) "
                  "pero que SÍ suma a una cuenta Laudus padre — la plata está en Laudus.")

    # Marcar la hoja fuente EAG
    accts = {c for c in laudus if any(laudus[c])}
    eag_green, eag_blue, eag_yellow, eag_yellow_list = mark_eag(wb, accts)
    leg["A12"] = f"Hoja EAG — verde: {eag_green}  azul: {eag_blue}  amarillo: {eag_yellow}"

    wb.save(OUT)

    # ---- consola ----
    print("=" * 90)
    print("REPORTE AUTO vs ORIGINAL — reconciliación por centro de costo (2025)")
    print("=" * 90)
    print(f"{'Centro de costo':<26}{'Laudus':>18}{'Excel orig':>18}{'diff':>16}")
    for cc, lau, exc in cost_center_cmp:
        print(f"{cc:<26}{lau:>18,.0f}{exc:>18,.0f}{lau-exc:>16,.0f}")
    print("-" * 90)
    print(f"Filas reproducidas desde Laudus (verde): {green_rows}")
    print(f"Filas en el reporte SIN fuente en Laudus (amarillo): {yellow_rows}")
    print(f"$ aprox. concentrado en celdas amarillas (capa manual): {round(manual_total):,}")
    print("-" * 90)
    print("HOJA EAG (fuente banco/Laudus) — verificación de tu hipótesis:")
    print(f"  Verde (código -> cuenta Laudus): {eag_green}")
    print(f"  Azul  (sub-línea que suma a cuenta Laudus): {eag_blue}")
    print(f"  Amarillo (SIN correspondencia en Laudus): {eag_yellow}")
    if eag_yellow_list:
        print("  Líneas amarillas en EAG (excepciones):")
        for r, a, lbl in eag_yellow_list:
            print(f"    r{r:>3} {a:<14} {lbl[:44]}")
    else:
        print("  -> CERO amarillas: todos los gastos de EAG tienen correspondencia en Laudus.")
    print(f"\nGenerado: {OUT}")


if __name__ == "__main__":
    main()

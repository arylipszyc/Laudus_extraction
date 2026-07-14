"""Reporte del Fondo Común (RUT2 · FFCC/JAB) — Story 13.1.

Reporte NUEVO, read-only, parametrizado por grupo de consolidación. **NO** reusa
`report_builder.build_report` (EAG-específico: `template_order.json`, prefijos
411/413/415/430, hijas). Comparte solo el toolkit openpyxl de bajo nivel (`_xlsx`).

Dos hojas:
  · **Gastos FFCC-JAB** — gastos por encabezado numérico mecánico (nivel 1 FFCC/JAB,
    nivel 2 = 2 primeros dígitos del código, etiqueta = `laudus_categoria2`),
    itemizado por cuenta, mensual. TC 871005/873005 lumpeada marcada en el cuerpo.
  · **Distribuciones** — estado de cuenta corriente por socio (saldo inicial +
    retiros − repartos = saldo al cierre), familiares separados de operativas, con
    marca de limitación honesta obligatoria y slots as-if para inversiones/offshore.

Decisiones (spec §Decisiones + resoluciones Valentina 2026-07-12 / Ary 2026-07-13):
los saldos son fieles a Laudus (12.5 = 0 diffs); las cuentas 115xxx son cuenta
corriente / patrimonio de socios (NO por cobrar); NO se corrige nada en el ledger.
"""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date

from openpyxl import Workbook

from backend.app.api.v1.reportes._xlsx import BOLD, DARK, LIGHT, WARN, ReportSheet

# TC de JAB/FGK lumpeadas (pago mensual sin desglose, estado 1 = igual que EAG) — FR55.
_TC_LUMP_CODES = {"871005", "873005"}
_TC_MARK = "  ⚠️ TC lump (pago mensual sin desglose)"

# Texto de la marca de limitación honesta obligatoria (AC3b / Valentina 2026-07-12).
_LIMITATION = (
    "⚠️ El patrimonio real del fondo NO es determinable desde Laudus: no están "
    "cargadas las posiciones de inversión (Indumotora, Sade, Molco, Leo Partnership) "
    "ni las propiedades/aviones/yates. La 'caja total' del fondo NO es usable como "
    "'lo que tiene'. Estas cuentas reflejan la cuenta corriente de cada socio "
    "(utilidad asignada vs. retirada), no su posición neta. El reporte NO afirma "
    "respaldo ni des-respaldo de los saldos a favor."
)


def _months_in_range(start: date, end: date):
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m, y = (1, y + 1) if m == 12 else (m + 1, y)
    return out


def _estado(saldo: float) -> str:
    if round(saldo) > 0:
        return "Debe al fondo"
    if round(saldo) < 0:
        return "A favor"
    return "—"


def build_report_rut2(start: date, end: date, report_rows: list[dict],
                      dist_rows: list[dict]) -> bytes:
    """Arma el xlsx del Fondo Común. `report_rows` = filas del grupo FondoComun
    (`report_rows_via_beancount`); `dist_rows` = `distribution_rows_via_beancount`."""
    months = _months_in_range(start, end)
    mindex = {ym: i for i, ym in enumerate(months)}
    nmon = len(months)

    wb = Workbook()
    _build_gastos_sheet(wb.active, start, end, report_rows, months, mindex, nmon)
    _build_distribuciones_sheet(wb.create_sheet("Distribuciones"), start, end, dist_rows)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_gastos_sheet(ws, start, end, report_rows, months, mindex, nmon):
    ws.title = "Gastos FFCC-JAB"
    sh = ReportSheet(ws, nmon, with_total=True)

    # tree[entity][prefix2] = {code: {"name","cat2","vals"[nmon]}}
    tree: dict = defaultdict(lambda: defaultdict(dict))
    for row in report_rows:
        acc = str(row.get("account", ""))
        if not acc.startswith("Expenses:"):
            continue
        parts = acc.split(":")
        entity = parts[1] if len(parts) > 1 else "?"
        code = str(row.get("accountnumber", ""))
        prefix2 = code[:2]
        ds = str(row.get("date", ""))[:10]
        try:
            ym = (int(ds[:4]), int(ds[5:7]))
        except ValueError:
            continue
        mi = mindex.get(ym)
        if mi is None:
            continue
        cell = tree[entity][prefix2].setdefault(
            code, {"name": str(row.get("accountName", "")) or code,
                   "cat2": str(row.get("Categoria2", "")), "vals": [0.0] * nmon})
        amt = float(row.get("debit") or 0) - float(row.get("credit") or 0)
        cell["vals"][mi] += amt

    sh.title("REPORTE DEL FONDO COMÚN (FFCC / JAB) — GASTOS", big=True)
    sh.note(f"Período: {start.isoformat()} a {end.isoformat()}  ·  Fuente: Laudus (RUT2, "
            f"vía Beancount — reconciliado 0 diffs @ 2026-06-30).")
    sh.note("Subtotales/totales son fórmulas Excel. Agrupación mecánica por dígitos del "
            "código (nivel 1 = 1er dígito, nivel 2 = 2 primeros).")
    sh.blank()
    sh.header_row([f"{m:02d}/{y}" for (y, m) in months])

    entity_total_rows: list[int] = []
    for entity in ("FFCC", "JAB"):
        if entity not in tree:
            continue
        sh.row(entity, bold=True, total=False)
        header_subtotal_rows: list[int] = []
        for prefix2 in sorted(tree[entity]):
            leaves = tree[entity][prefix2]
            cat2 = next(iter(leaves.values()))["cat2"] or "(sin categoría)"
            sh.row(f"{prefix2} · {cat2}", bold=True, total=False)
            first = last = None
            for code in sorted(leaves):
                leaf = leaves[code]
                label = f"{leaf['name']} · {code}"
                if code in _TC_LUMP_CODES:
                    label += _TC_MARK
                cur = sh.row(label, values=leaf["vals"], indent=True)
                first = first or cur
                last = cur
            if first:
                sub = sh.row(f"Subtotal {prefix2} · {cat2}",
                             formulas=sh.sum_formula(first, last), bold=True, fill=LIGHT)
                header_subtotal_rows.append(sub)
        if header_subtotal_rows:
            tot = sh.row(f"TOTAL GASTOS {entity}",
                         formulas=sh.add_formula(header_subtotal_rows), bold=True, fill=DARK)
            entity_total_rows.append(tot)
        sh.blank()

    if entity_total_rows:
        sh.row("TOTAL GASTOS FONDO COMÚN",
               formulas=sh.add_formula(entity_total_rows), bold=True, fill=DARK)

    sh.set_widths(46, 13)


def _build_distribuciones_sheet(ws, start, end, dist_rows):
    ws.title = "Distribuciones"
    # 4 columnas de valor; la 5ª (columna F) es texto "Estado" (se escribe aparte).
    sh = ReportSheet(ws, 4, with_total=False)

    sh.title("DISTRIBUCIONES — CUENTA CORRIENTE DE SOCIOS (FFCC / JAB)", big=True)
    sh.note(f"Período: {start.isoformat()} a {end.isoformat()}  ·  Fuente: Laudus (RUT2, "
            f"reconciliado 0 diffs @ 2026-06-30).")
    # Marca de limitación honesta obligatoria (AC3b) — en el cuerpo, no al pie.
    sh.note(_LIMITATION, italic=False, fill=WARN, bold=True)
    sh.note("Estas cuentas (cat. 'CUENTAS POR COBRAR') son, contablemente, cuenta corriente "
            "/ patrimonio de socios, no cobranzas. 'A favor' = utilidad asignada no retirada.")
    sh.blank()

    headers = ["Saldo inicial", "Retiros del período", "Repartos/abonos", "Saldo al cierre"]
    sh.header_row(headers)
    ws.cell(sh.r - 1, 6, "Estado").font = BOLD  # columna de texto extra

    def dist_block(title, rows):
        if not rows:
            return
        sh.row(title, bold=True)
        first = last = None
        for d in rows:
            cur = sh.row(
                f"{d['name']} · {d['code']}",
                values=[d["saldo_inicial"], d["retiros"], d["repartos"], d["saldo_cierre"]],
                indent=True)
            ws.cell(cur, 6, _estado(d["saldo_cierre"]))
            first = first or cur
            last = cur
        if first:
            sh.row(f"Subtotal {title.lower()}", formulas=sh.sum_formula(first, last),
                   bold=True, fill=LIGHT)
        sh.blank()

    dist_block("FAMILIARES", [d for d in dist_rows if not d["operational"]])
    dist_block("OPERATIVAS (cuentas de sistema ~0)", [d for d in dist_rows if d["operational"]])

    # Slots as-if — inversiones/offshore pendientes de carga (decisión Ary 2026-07-13).
    sh.title("POSICIONES DE INVERSIÓN Y CUENTAS OFFSHORE — PENDIENTE DE CARGA")
    sh.note("Estructura preparada para poblar cuando lleguen los saldos del custodio y las "
            "cuentas offshore. HOY estos renglones NO están cargados en Laudus; una vez "
            "poblados, reducen la limitación de arriba.", fill=WARN)
    sh.row("Posiciones de inversión (Indumotora, Sade, Molco, Leo Partnership, …)",
           values=[0, 0, 0, 0], indent=True)
    sh.row("Propiedades / aviones / yates (Vía Gris, Molco, Miami, Keiki Kai, …)",
           values=[0, 0, 0, 0], indent=True)
    sh.row("Cuentas offshore (fuera de Chile — sin saldo inicial cargado)",
           values=[0, 0, 0, 0], indent=True)

    sh.set_widths(40, 16)
    ws.column_dimensions["F"].width = 14

"""
dashboard.py — Dashboard contable familiar (Laudus → Google Sheets)

Vistas:
  1. Gastos / Ingresos  — ledger_final, con filtros de tiempo preconfigurados
  2. Activos / Pasivos / Patrimonio — balance_sheet_final, por corte mensual

Ejecutar:
    streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from config.gspread_config import get_spreadsheet

# ─────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Familiar",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 1.6rem; }
    div[data-testid="stTabs"] button { font-size: 1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────
# Carga de datos (caché 1 hora)
# ─────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data():
    sh = get_spreadsheet()
    if not sh:
        return None, None

    try:
        lf = pd.DataFrame(sh.worksheet("ledger_final").get_all_records())
    except Exception:
        lf = pd.DataFrame()

    try:
        bf = pd.DataFrame(sh.worksheet("balance_sheet_final").get_all_records())
    except Exception:
        bf = pd.DataFrame()

    return lf, bf


ledger_raw, balance_raw = load_data()

if ledger_raw is None:
    st.error("No se pudo conectar a Google Sheets. Verifica las credenciales en .env")
    st.stop()

# ─────────────────────────────────────
# Preparar ledger
# ─────────────────────────────────────
ledger_raw["date"] = pd.to_datetime(ledger_raw["date"], errors="coerce")
ledger_raw["debit"]  = pd.to_numeric(ledger_raw["debit"],  errors="coerce").fillna(0)
ledger_raw["credit"] = pd.to_numeric(ledger_raw["credit"], errors="coerce").fillna(0)

# Clasificar filas como INGRESO o EGRESO según Categoria1
INGRESO_CATS = [c for c in ledger_raw["Categoria1"].unique() if "INGRESO" in str(c).upper()]
EGRESO_CATS  = [c for c in ledger_raw["Categoria1"].unique() if "EGRESO" in str(c).upper() or "GASTO" in str(c).upper()]

def tipo_movimiento(cat):
    cat_up = str(cat).upper()
    if "INGRESO" in cat_up:
        return "Ingresos"
    if "EGRESO" in cat_up or "GASTO" in cat_up:
        return "Gastos"
    return "Otros"

ledger_raw["tipo"] = ledger_raw["Categoria1"].apply(tipo_movimiento)
ledger_raw["mes"]  = ledger_raw["date"].dt.to_period("M").astype(str)

# ─────────────────────────────────────
# Preparar balance
# ─────────────────────────────────────
balance_raw["debit_balance"]  = pd.to_numeric(balance_raw["debit_balance"],  errors="coerce").fillna(0)
balance_raw["credit_balance"] = pd.to_numeric(balance_raw["credit_balance"], errors="coerce").fillna(0)
balance_raw["query_date"] = pd.to_datetime(balance_raw["query_date"], errors="coerce")

# ─────────────────────────────────────
# Título y tabs
# ─────────────────────────────────────
st.title("📊 Dashboard Familiar")

tab1, tab2 = st.tabs(["💸  Gastos / Ingresos", "🏦  Activos / Pasivos / Patrimonio"])


# ══════════════════════════════════════════════════════
# TAB 1 — GASTOS / INGRESOS
# ══════════════════════════════════════════════════════
with tab1:

    # ── Botones de rango de tiempo ──
    hoy = date.today()
    # Último día del mes anterior (mes completo más reciente)
    fin_mes_anterior   = date(hoy.year, hoy.month, 1) - timedelta(days=1)
    # Primer día de cada rango (siempre inicio de mes)
    ini_ultimo_mes     = date(fin_mes_anterior.year, fin_mes_anterior.month, 1)
    ini_ultimos_3m     = date((fin_mes_anterior - relativedelta(months=2)).year,
                              (fin_mes_anterior - relativedelta(months=2)).month, 1)
    ini_ultimos_12m    = date((fin_mes_anterior - relativedelta(months=11)).year,
                              (fin_mes_anterior - relativedelta(months=11)).month, 1)
    ini_ytd            = date(hoy.year, 1, 1)

    col_btn = st.columns(5)
    rangos = {
        "Último mes":    (ini_ultimo_mes,  fin_mes_anterior),
        "Últimos 3 m":   (ini_ultimos_3m,  fin_mes_anterior),
        "Últimos 12 m":  (ini_ultimos_12m, fin_mes_anterior),
        "YTD":           (ini_ytd,         fin_mes_anterior),
        "Personalizado": None,
    }

    if "rango_sel" not in st.session_state:
        st.session_state.rango_sel = "Últimos 12 m"

    for i, nombre in enumerate(rangos):
        if col_btn[i].button(nombre, use_container_width=True,
                             type="primary" if st.session_state.rango_sel == nombre else "secondary"):
            st.session_state.rango_sel = nombre

    # Rango personalizado
    if st.session_state.rango_sel == "Personalizado":
        fecha_min = ledger_raw["date"].min().date()
        fecha_max = ledger_raw["date"].max().date()
        c1, c2 = st.columns(2)
        f_desde = c1.date_input("Desde", value=fecha_min, min_value=fecha_min, max_value=fecha_max)
        f_hasta = c2.date_input("Hasta", value=fecha_max, min_value=fecha_min, max_value=fecha_max)
    else:
        f_desde, f_hasta = rangos[st.session_state.rango_sel]

    # ── Filtro por persona / entidad ──
    personas = sorted(ledger_raw["Categoria1"].unique().tolist())
    persona_sel = st.multiselect(
        "Filtrar por categoría",
        personas,
        default=[c for c in personas if c in ["INGRESOS", "GASTOS - EGRESOS"]],
        key="persona_sel"
    )

    # ── Aplicar filtros ──
    mask = (
        (ledger_raw["date"].dt.date >= f_desde) &
        (ledger_raw["date"].dt.date <= f_hasta) &
        (ledger_raw["Categoria1"].isin(persona_sel))
    )
    df = ledger_raw[mask].copy()

    st.caption(f"Período: {f_desde} → {f_hasta}  |  {len(df):,} registros")
    st.divider()

    # ── KPI Cards ──
    total_ingresos = df[df["tipo"] == "Ingresos"]["credit"].sum()
    total_gastos   = df[df["tipo"] == "Gastos"]["debit"].sum()
    resultado_neto = total_ingresos - total_gastos
    n_cuentas      = df["accountnumber"].nunique()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Ingresos",  f"${total_ingresos:,.0f}")
    k2.metric("Total Gastos",    f"${total_gastos:,.0f}")
    k3.metric("Resultado Neto",  f"${resultado_neto:,.0f}",
              delta=f"{'Superávit' if resultado_neto >= 0 else 'Déficit'}")
    k4.metric("Cuentas activas", n_cuentas)

    st.divider()

    # ── Fila 2: Tendencia mensual + Donut de gastos ──
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Tendencia mensual")
        trend = (
            df.groupby(["mes", "tipo"])[["debit", "credit"]]
            .sum().reset_index().sort_values("mes")
        )
        ingresos_trend = trend[trend["tipo"] == "Ingresos"].rename(columns={"credit": "monto"})
        gastos_trend   = trend[trend["tipo"] == "Gastos"].rename(columns={"debit": "monto"})

        fig_line = go.Figure()
        fig_line.add_trace(go.Bar(
            x=gastos_trend["mes"], y=gastos_trend["monto"],
            name="Gastos", marker_color="#EF553B"
        ))
        fig_line.add_trace(go.Scatter(
            x=ingresos_trend["mes"], y=ingresos_trend["monto"],
            name="Ingresos", mode="lines+markers",
            line=dict(color="#00CC96", width=2)
        ))
        fig_line.update_layout(
            xaxis_title="Mes", yaxis_title="Monto",
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=10, l=0, r=0, b=0),
            barmode="group"
        )
        st.plotly_chart(fig_line, use_container_width=True)

    with col_r:
        st.subheader("Gastos por categoría")
        gastos_cat = (
            df[df["tipo"] == "Gastos"]
            .groupby("Categoria2")["debit"].sum()
            .reset_index().query("debit > 0")
            .sort_values("debit", ascending=False)
        )
        if not gastos_cat.empty:
            fig_donut = px.pie(
                gastos_cat, names="Categoria2", values="debit",
                hole=0.45,
            )
            fig_donut.update_traces(textposition="inside", textinfo="percent+label")
            fig_donut.update_layout(showlegend=False, margin=dict(t=10, l=0, r=0, b=0))
            st.plotly_chart(fig_donut, use_container_width=True)
        else:
            st.info("Sin datos de gastos en el período seleccionado.")

    st.divider()

    # ── Fila 3: Treemap ──
    st.subheader("Distribución de gastos (jerarquía)")
    tree_df = (
        df[df["tipo"] == "Gastos"]
        .groupby(["Categoria1", "Categoria2", "Categoria3"], as_index=False)["debit"]
        .sum().query("debit > 0")
    )

    # Capturar click del treemap para filtrar la tabla
    treemap_filtro = None   # label seleccionado (puede ser Cat1, Cat2 o Cat3)

    if not tree_df.empty:
        fig_tree = px.treemap(
            tree_df, path=["Categoria1", "Categoria2", "Categoria3"],
            values="debit", color="debit",
            color_continuous_scale="Reds",
        )
        fig_tree.update_traces(root_color="lightgrey")
        fig_tree.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=500)

        treemap_event = st.plotly_chart(
            fig_tree, use_container_width=True,
            on_select="rerun", key="treemap_click"
        )

        # Extraer la categoría clickeada
        points = (treemap_event.selection or {}).get("points", [])
        if points:
            treemap_filtro = points[0].get("label")

    st.divider()

    # ── Tabla de transacciones ──
    col_tabla_title, col_limpiar = st.columns([4, 1])
    col_tabla_title.subheader("Detalle de transacciones")

    # Mostrar filtro activo y botón para limpiarlo
    if treemap_filtro:
        col_limpiar.markdown("<br>", unsafe_allow_html=True)
        if col_limpiar.button("✕ Quitar filtro", key="limpiar_treemap"):
            treemap_filtro = None
            st.rerun()
        st.info(f"Filtrando por: **{treemap_filtro}**  — haz clic en otro sector o en 'Quitar filtro' para cambiar")

    buscar = st.text_input("Buscar por descripción o cuenta", key="buscar_ledger")

    tabla = df[[
        "date", "accountnumber", "accountName",
        "Categoria1", "Categoria2", "Categoria3", "description", "debit", "credit", "tipo"
    ]].copy()
    tabla["date"] = tabla["date"].dt.strftime("%Y-%m-%d")

    # Aplicar filtro del treemap (coincide contra cualquiera de los 3 niveles)
    if treemap_filtro:
        mask_tree = (
            (tabla["Categoria1"] == treemap_filtro) |
            (tabla["Categoria2"] == treemap_filtro) |
            (tabla["Categoria3"] == treemap_filtro)
        )
        tabla = tabla[mask_tree]

    tabla = tabla.rename(columns={
        "date": "Fecha", "accountnumber": "N° Cuenta", "accountName": "Cuenta",
        "Categoria1": "Cat. 1", "Categoria2": "Cat. 2", "Categoria3": "Cat. 3",
        "description": "Descripción", "debit": "Debe",
        "credit": "Haber", "tipo": "Tipo"
    })

    if buscar:
        mask_b = (
            tabla["Descripción"].str.contains(buscar, case=False, na=False) |
            tabla["N° Cuenta"].astype(str).str.contains(buscar, case=False, na=False)
        )
        tabla = tabla[mask_b]

    st.dataframe(
        tabla.sort_values("Fecha", ascending=False).reset_index(drop=True),
        use_container_width=True, height=350
    )


# ══════════════════════════════════════════════════════
# TAB 2 — ACTIVOS / PASIVOS / PATRIMONIO
# ══════════════════════════════════════════════════════
with tab2:

    # ── Selector de corte mensual ──
    fechas_disponibles = sorted(balance_raw["query_date"].dropna().unique())
    fechas_str = [f.strftime("%Y-%m-%d") for f in fechas_disponibles]

    if not fechas_str:
        st.warning("No hay datos de balance. Ejecuta sync.py primero.")
        st.stop()

    corte_sel = st.select_slider(
        "Corte mensual",
        options=fechas_str,
        value=fechas_str[-1],
    )

    bf = balance_raw[balance_raw["query_date"] == pd.to_datetime(corte_sel)].copy()

    st.caption(f"Balance al {corte_sel}  |  {len(bf):,} cuentas")
    st.divider()

    # Clasificar cuentas
    ACTIVO_CATS   = [c for c in bf["Categoria1"].unique() if "ACTIVO"   in str(c).upper() or "DISPONIBLE" in str(c).upper()]
    PASIVO_CATS   = [c for c in bf["Categoria1"].unique() if "PASIVO"   in str(c).upper()]
    # Patrimonio = todo lo demás (o calculado)
    activo_df  = bf[bf["Categoria1"].isin(ACTIVO_CATS)]
    pasivo_df  = bf[bf["Categoria1"].isin(PASIVO_CATS)]

    total_activo  = activo_df["debit_balance"].sum() - activo_df["credit_balance"].sum()
    total_pasivo  = pasivo_df["credit_balance"].sum() - pasivo_df["debit_balance"].sum()
    patrimonio    = total_activo - total_pasivo

    # ── KPI Cards ──
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Activos",   f"${total_activo:,.0f}")
    k2.metric("Total Pasivos",   f"${total_pasivo:,.0f}")
    k3.metric("Patrimonio Neto", f"${patrimonio:,.0f}",
              delta=f"{'Positivo' if patrimonio >= 0 else 'Negativo'}")

    st.divider()

    # ── Fila 2: Barras activo/pasivo + Donut activos ──
    col_l2, col_r2 = st.columns(2)

    with col_l2:
        st.subheader("Estructura financiera")
        estructura = pd.DataFrame({
            "Categoría": ["Activos", "Pasivos", "Patrimonio"],
            "Monto": [total_activo, total_pasivo, patrimonio]
        })
        fig_barras = px.bar(
            estructura, x="Categoría", y="Monto",
            color="Categoría",
            color_discrete_map={
                "Activos": "#00CC96",
                "Pasivos": "#EF553B",
                "Patrimonio": "#636EFA"
            },
            text_auto=True
        )
        fig_barras.update_layout(showlegend=False, margin=dict(t=10, l=0, r=0, b=0))
        st.plotly_chart(fig_barras, use_container_width=True)

    with col_r2:
        st.subheader("Composición de activos")
        activo_cat = (
            activo_df.groupby("Categoria2")["debit_balance"].sum()
            .reset_index().query("debit_balance > 0")
        )
        if not activo_cat.empty:
            fig_act = px.pie(
                activo_cat, names="Categoria2", values="debit_balance",
                hole=0.45,
            )
            fig_act.update_traces(textposition="inside", textinfo="percent+label")
            fig_act.update_layout(showlegend=False, margin=dict(t=10, l=0, r=0, b=0))
            st.plotly_chart(fig_act, use_container_width=True)

    st.divider()

    # ── Evolución histórica del patrimonio ──
    st.subheader("Evolución histórica del patrimonio")

    hist = []
    for fecha in fechas_disponibles:
        bh = balance_raw[balance_raw["query_date"] == fecha]
        a_cats = [c for c in bh["Categoria1"].unique() if "ACTIVO" in str(c).upper() or "DISPONIBLE" in str(c).upper()]
        p_cats = [c for c in bh["Categoria1"].unique() if "PASIVO" in str(c).upper()]
        a = bh[bh["Categoria1"].isin(a_cats)]
        p = bh[bh["Categoria1"].isin(p_cats)]
        ta = a["debit_balance"].sum() - a["credit_balance"].sum()
        tp = p["credit_balance"].sum() - p["debit_balance"].sum()
        hist.append({
            "fecha": fecha.strftime("%Y-%m-%d"),
            "Activos": ta,
            "Pasivos": tp,
            "Patrimonio": ta - tp
        })

    hist_df = pd.DataFrame(hist)
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Scatter(
        x=hist_df["fecha"], y=hist_df["Activos"],
        name="Activos", fill="tozeroy", line=dict(color="#00CC96")
    ))
    fig_hist.add_trace(go.Scatter(
        x=hist_df["fecha"], y=hist_df["Pasivos"],
        name="Pasivos", fill="tozeroy", line=dict(color="#EF553B")
    ))
    fig_hist.add_trace(go.Scatter(
        x=hist_df["fecha"], y=hist_df["Patrimonio"],
        name="Patrimonio", mode="lines+markers", line=dict(color="#636EFA", width=2)
    ))
    fig_hist.update_layout(
        xaxis_title="Mes", yaxis_title="Monto",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=10, l=0, r=0, b=0)
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    st.divider()

    # ── Tabla de cuentas ──
    st.subheader("Detalle de cuentas")
    tipo_filtro = st.radio("Ver", ["Todas", "Activos", "Pasivos"], horizontal=True)

    tabla_b = bf[[
        "account_number", "accountName", "Categoria1", "Categoria2",
        "debit_balance", "credit_balance"
    ]].copy()
    tabla_b = tabla_b.rename(columns={
        "account_number": "N° Cuenta", "accountName": "Cuenta",
        "Categoria1": "Cat. 1", "Categoria2": "Cat. 2",
        "debit_balance": "Saldo Deudor", "credit_balance": "Saldo Acreedor"
    })

    if tipo_filtro == "Activos":
        tabla_b = tabla_b[tabla_b["Cat. 1"].isin(ACTIVO_CATS)]
    elif tipo_filtro == "Pasivos":
        tabla_b = tabla_b[tabla_b["Cat. 1"].isin(PASIVO_CATS)]

    st.dataframe(tabla_b.reset_index(drop=True), use_container_width=True, height=350)

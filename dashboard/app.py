
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

DATOS = Path(__file__).resolve().parents[1] / "data" / "processed"
T = pd.Timestamp
AZUL, NARANJA, GRIS, VERDE, ROJO = "#1f5fa8", "#e07b00", "#8a8f98", "#2a9d8f", "#c0392b"
SUBGRUPOS = {"061": "Medicamentos y equipos", "062": "Servicios ambulatorios", "063": "Hospital"}
COLOR_SUB = {"Medicamentos y equipos": AZUL, "Servicios ambulatorios": NARANJA, "Hospital": VERDE}

# ----------------------------------------------------------------------------- datos
series = pd.read_parquet(DATOS / "ipc_series_oficiales.parquet")
suby = pd.read_parquet(DATOS / "subyacente.parquet").set_index("fecha")
comp = pd.read_parquet(DATOS / "salud_componentes.parquet")
ind_salud = pd.read_parquet(DATOS / "ipc_salud_indicadores.parquet")
contrib = pd.read_parquet(DATOS / "analisis_contribuciones.parquet")
indexacion = pd.read_parquet(DATOS / "analisis_indexacion.parquet")

_ancho = lambda col: series.pivot(index="fecha", columns="codigo", values=col)
IDX, MEN, INT = _ancho("indice"), _ancho("var_mensual"), _ancho("var_interanual")
ACUM = (IDX / IDX.loc[T(2020, 12, 1)] - 1) * 100
ACUM = ACUM.loc[T(2020, 12, 1):]                     # solo existe desde dic-2020
NOMBRES = series.drop_duplicates("codigo").set_index("codigo")["nombre"].to_dict()
NOMBRES["GEN"] = "IPC general"

PERIODOS = {
    "ventana": (T(2021, 1, 1), T(2026, 3, 1), "Ventana del trabajo (ene-2021 a mar-2026)"),
    "extra": (T(2021, 1, 1), T(2026, 8, 1), "Con extra hasta ago-2026"),
    "historia": (T(1999, 1, 1), T(2026, 8, 1), "Historia completa (1999 en adelante)"),
}
MEDIDAS = {
    "interanual": ("Inflación interanual (%)", INT),
    "mensual": ("Variación mensual (%)", MEN),
    "acum": ("Acumulada desde dic-2020 (%)", ACUM),
    "indice": ("Índice (base oct-2019 a sep-2020 = 100)", IDX),
}
COMPARADORES = ["GEN"] + [c for c in IDX.columns if c not in ("GEN", "06")]


def limpio(txt) -> str:
    return str(txt).strip()


# ----------------------------------------------------------------------------- pestana 1: evolucion
def _tramo(periodo, medida, cod):
    ini, fin, _ = PERIODOS[periodo]
    return MEDIDAS[medida][1][cod].loc[ini:fin].dropna()


def fig_evolucion(periodo: str, medida: str, comparador: str, ver_suby: bool) -> go.Figure:
    etiqueta = MEDIDAS[medida][0]
    fig = go.Figure()
    fig.add_scatter(x=_tramo(periodo, medida, "06").index, y=_tramo(periodo, medida, "06"),
                    name="Salud", line=dict(color=AZUL, width=3))
    s_comp = _tramo(periodo, medida, comparador)
    fig.add_scatter(x=s_comp.index, y=s_comp, name=NOMBRES[comparador], line=dict(color=NARANJA, width=2))
    if ver_suby and medida == "interanual":
        ini, fin, _ = PERIODOS[periodo]
        sb = suby["suby_interanual"].loc[ini:fin].dropna()
        fig.add_scatter(x=sb.index, y=sb, name="Inflación subyacente (general)",
                        line=dict(color=GRIS, width=2, dash="dash"))
    fig.update_layout(title=f"Salud frente a {NOMBRES[comparador]}: {etiqueta}", yaxis_title=etiqueta,
                      hovermode="x unified", legend=dict(orientation="h", y=-0.2), margin=dict(t=60))
    return fig


def fig_brecha(periodo: str, medida: str, comparador: str) -> go.Figure:
    dif = (_tramo(periodo, medida, "06") - _tramo(periodo, medida, comparador)).dropna()
    unidad = "puntos" if medida == "indice" else "puntos porcentuales"
    fig = go.Figure(go.Bar(x=dif.index, y=dif, marker_color=[AZUL if v >= 0 else NARANJA for v in dif],
                           name="Salud − comparador"))
    fig.add_hline(y=0, line_color=GRIS)
    fig.update_layout(title=f"Brecha: Salud menos {NOMBRES[comparador]} ({unidad}); azul = Salud por encima",
                      yaxis_title=unidad, margin=dict(t=60), showlegend=False)
    return fig


def tarjetas(periodo: str, comparador: str) -> html.Div:
    ini, fin, _ = PERIODOS[periodo]
    ultimo = INT["06"].loc[ini:fin].dropna().index.max()
    salud, comp_v = INT.loc[ultimo, "06"], INT.loc[ultimo, comparador]
    sb = suby["suby_interanual"].get(ultimo)
    datos = [("Salud", f"{salud:.2f}%"), (NOMBRES[comparador], f"{comp_v:.2f}%"),
             ("Brecha", f"{salud - comp_v:+.2f} pp"),
             ("Subyacente (general)", f"{sb:.2f}%" if pd.notna(sb) else "n.d.")]
    cajas = [html.Div([html.Div(t, style={"fontSize": "12px", "color": GRIS}),
                       html.Div(v, style={"fontSize": "22px", "fontWeight": "bold"})],
                      style=ESTILO_TARJETA) for t, v in datos]
    return html.Div([html.Div(f"Inflación interanual en {ultimo:%m/%Y}", style={"marginBottom": "6px"}),
                     html.Div(cajas, style={"display": "flex", "gap": "12px", "flexWrap": "wrap"})])


# ----------------------------------------------------------------------------- pestana 2: jerarquia de Salud
def fig_treemap() -> go.Figure:
    nom = comp.set_index("codigo")["nombre"].map(limpio)
    a = comp[comp["nivel"] == "articulo"].copy()
    for col in ["subgrupo_cod", "clase_cod", "subclase_cod"]:
        a[col.replace("_cod", "")] = a[col].map(nom)
    a["articulo"] = a["nombre"].map(limpio)
    fig = px.treemap(a, path=["subgrupo", "clase", "subclase", "articulo"], values="ponderacion",
                     color="tipo", color_discrete_map={"Bien": AZUL, "Servicio": NARANJA},
                     hover_data={"parte_de_salud_pct": ":.1f", "transable": True, "subyacente": True})
    fig.update_traces(textfont=dict(color="white"))
    fig.update_layout(title="Salud: peso de cada componente en la canasta (azul = bien, naranja = servicio)",
                      margin=dict(t=60, l=5, r=5, b=5))
    return fig


def opciones_nodos() -> list[dict]:
    c = comp.sort_values("codigo")
    return [{"label": f"{r.codigo} · {limpio(r.nombre)} ({r.nivel})", "value": r.codigo} for r in c.itertuples()]


def fig_nodo(cod: str, medida: str) -> go.Figure:
    col, titulo = {"indice": ("indice", "Índice"), "interanual": ("var_interanual", "Inflación interanual (%)"),
                   "mensual": ("var_mensual", "Variación mensual (%)")}[medida]
    d = ind_salud[ind_salud["codigo"] == cod].sort_values("fecha").dropna(subset=[col])
    ref = ind_salud[ind_salud["codigo"] == "06"].sort_values("fecha").dropna(subset=[col])
    fig = go.Figure()
    fig.add_scatter(x=d["fecha"], y=d[col], name=limpio(comp.set_index("codigo").loc[cod, "nombre"]),
                    line=dict(color=AZUL, width=3))
    if cod != "06":
        fig.add_scatter(x=ref["fecha"], y=ref[col], name="Salud (total)", line=dict(color=GRIS, dash="dash"))
    nota = " (disponible desde oct-2021)" if medida == "interanual" else ""
    fig.update_layout(title=f"{titulo}{nota}", yaxis_title=titulo, hovermode="x unified",
                      legend=dict(orientation="h", y=-0.2), margin=dict(t=60))
    return fig


def info_nodo(cod: str) -> html.Div:
    r = comp.set_index("codigo").loc[cod]
    filas = [("Nivel", r["nivel"]), ("Peso en la canasta", f"{r['ponderacion']:.3f}%"),
             ("Parte de Salud", f"{r['parte_de_salud_pct']:.1f}%")]
    if r["nivel"] == "articulo":
        filas += [("Tipo", r["tipo"]), ("Transable", r["transable"]), ("Inflación subyacente", r["subyacente"])]
    return html.Div([
        html.Div([html.Span(f"{k}: ", style={"color": GRIS}), html.Span(str(v), style={"fontWeight": "bold"})])
        for k, v in filas])


# ----------------------------------------------------------------------------- pestana 3: que mueve a Salud
def fig_aportes() -> go.Figure:
    sg = contrib[contrib["nivel"] == "subgrupo"]
    ventanas = list(contrib["ventana"].unique())
    peso = sg[sg["ventana"] == ventanas[0]].set_index("codigo")["ponderacion"]
    fig = go.Figure()
    for cod, nombre in SUBGRUPOS.items():
        y = [peso[cod] / peso.sum() * 100] + [
            sg[(sg["ventana"] == v) & (sg["codigo"] == cod)]["parte_pct"].iloc[0] for v in ventanas]
        fig.add_bar(x=["Peso en Salud"] + [v.replace(" (", "<br>(") for v in ventanas], y=y, name=nombre,
                    marker_color=COLOR_SUB[nombre],
                    text=[f"{v:.0f}%" for v in y], textposition="inside")
    fig.update_layout(barmode="stack", title="De dónde viene el aumento de Salud (% por subgrupo)",
                      yaxis_title="% del aumento de Salud", margin=dict(t=60), legend=dict(orientation="h", y=-0.3),
                      legend_traceorder="normal")
    return fig


def fig_top(ventana: str) -> go.Figure:
    d = contrib[(contrib["ventana"] == ventana) & (contrib["nivel"] == "articulo")].nlargest(10, "contribucion_pp")
    d = d.sort_values("contribucion_pp").copy()                       # de menor a mayor: el mayor queda arriba
    d["subgrupo"] = d["subgrupo_cod"].map(SUBGRUPOS)
    d["articulo"] = d["nombre"].map(limpio)
    var = d["var_salud_pct"].iloc[0]
    fig = px.bar(d, x="contribucion_pp", y="articulo", color="subgrupo", orientation="h",
                 color_discrete_map=COLOR_SUB, category_orders={"articulo": list(d["articulo"])},
                 labels={"contribucion_pp": "Aporte (puntos porcentuales)", "articulo": ""})
    fig.update_layout(title=f"Los 10 artículos que más aportan al aumento de Salud ({var:.1f}% en la ventana)",
                      margin=dict(t=60), legend=dict(orientation="h", y=-0.2))
    return fig


# ----------------------------------------------------------------------------- pestana 4: indexacion
def fig_tasas() -> go.Figure:
    d = indexacion.iloc[:4]
    x = [f"{r.ventana}<br>{r.periodo}" for r in d.itertuples()]
    fig = go.Figure()
    for col, nombre, color in [("reconocido_pct", "Reconocido por el CNSS", "#111111"), ("general_pct", "Solo IPC general", NARANJA),
                               ("salud_pct", "Solo IPC Salud", AZUL), ("promedio_pct", "Promedio (regla actual)", VERDE)]:
        fig.add_bar(x=x, y=d[col], name=nombre, marker_color=color, texttemplate="%{y:.2f}", textposition="outside")
    fig.update_layout(barmode="group", title="Indexación por ventana: lo reconocido frente a cada regla (%)",
                      yaxis_title="% sobre el per cápita", margin=dict(t=60), legend=dict(orientation="h", y=-0.3))
    return fig


def fig_montos() -> go.Figure:
    d = indexacion
    fig = go.Figure()
    for col, nombre, color in [("reconocido_rd", "Reconocido", "#111111"), ("si_general_rd", "Si fuera solo el general", NARANJA),
                               ("si_salud_rd", "Si fuera solo Salud", AZUL), ("si_promedio_rd", "Si fuera el promedio", VERDE)]:
        fig.add_bar(x=d["ventana"], y=d[col], name=nombre, marker_color=color)
    fig.update_layout(barmode="group", title="Montos mensuales en RD$ por ventana (ilustrativo)",
                      yaxis_title="RD$ por afiliado al mes", margin=dict(t=60), legend=dict(orientation="h", y=-0.35))
    return fig


def tabla_indexacion() -> html.Table:
    cols = [("ventana", "Ventana"), ("periodo", "Período"), ("reconocido_rd", "Reconocido RD$"), ("reconocido_pct", "Reconocido %"),
            ("general_pct", "General %"), ("salud_pct", "Salud %"), ("promedio_pct", "Promedio %")]
    cab = html.Tr([html.Th(n, style=ESTILO_CELDA) for _, n in cols])
    filas = [html.Tr([html.Td(f"{r[c]:,.2f}" if isinstance(r[c], float) else r[c], style=ESTILO_CELDA) for c, _ in cols])
             for _, r in indexacion.iterrows()]
    return html.Table([cab] + filas, style={"borderCollapse": "collapse", "fontSize": "13px", "width": "100%"})


def simular(base, regla: str, hasta: str) -> str:
    base = 1887.54 if base is None else float(base)
    fila = indexacion.set_index("ventana").loc[hasta]
    tasa = fila[f"{regla}_pct"]
    nombre = {"general": "solo IPC general", "salud": "solo IPC Salud", "promedio": "promedio de ambos"}[regla]
    fin = "marzo 2026" if "mar-2026" in hasta else "agosto 2026"
    return (f"Con la regla «{nombre}», la inflación desde abril 2025 hasta {fin} es {tasa:.2f}%, "
            f"es decir RD$ {base * tasa / 100:,.2f} al mes sobre un per cápita de RD$ {base:,.2f}.")


# ----------------------------------------------------------------------------- textos
FUENTES = """
**Fuentes (todas oficiales)**
- Banco Central de la República Dominicana: Cuadros de publicación IPC 2025 (3.1, 3.3 y 3.8), informes mensuales IPC de enero a marzo 2026 y documento metodológico del IPC (base octubre 2019 a septiembre 2020).
- Oficina Nacional de Estadística: IPC por artículos, octubre 2020 a agosto 2026 (coincide con los Cuadros del BCRD en los 63 meses en que se solapan).
- CNSS: resoluciones 278-06, 553-02, 581-03, 624-02 y 645-16. Ley 87-01, artículo 169.

**Cómo se calculó**
- Variaciones mensual, acumulada e interanual, e incidencia, para los 612 nodos de la canasta. Validado contra los informes oficiales de enero 2021 y enero a marzo 2026.
- El índice de cada nodo coincide con el promedio ponderado de sus hijos (diferencia máxima 0.001).
- Ejercicio de indexación: promedio de la variación del IPC general y del IPC Salud desde el mes previo a cada ventana hasta su último mes.

**Límites que conviene tener presentes**
- La tasa interanual de subgrupo, clase, subclase y artículo existe desde octubre 2021, porque el índice por artículos empieza en octubre 2020.
- El promedio reproduce los montos reconocidos con un error de hasta 0.45 puntos, no exacto. La fórmula exacta está en los informes técnicos de SISALRIL, que no son públicos.
- No se dispone de la estructura de gasto del PDSS por tipo de servicio, así que no se puede afirmar que el IPC de Salud subestime su costo.
- Seis celdas del bloque anual del Cuadro 3.3 (2013 a 2017) contienen errores; se usaron los índices.
- La subyacente de enero a marzo 2026 proviene de los informes mensuales del BCRD.
"""
ESTILO_TARJETA = {"border": "1px solid #d5d9e0", "borderRadius": "8px", "padding": "10px 16px", "minWidth": "150px", "background": "#f7f9fc"}
ESTILO_CELDA = {"border": "1px solid #d5d9e0", "padding": "6px 8px", "textAlign": "right"}
CAJA = {"maxWidth": "1200px", "margin": "0 auto", "padding": "10px 20px"}


# ----------------------------------------------------------------------------- aplicacion
app = Dash(__name__, title="IPC de Salud y per cápita del PDSS")
server = app.server

tab1 = html.Div([
    html.Div([
        html.Div([html.Label("Período"), dcc.RadioItems(id="periodo", value="ventana",
                  options=[{"label": v[2], "value": k} for k, v in PERIODOS.items()])]),
        html.Div([html.Label("Medida"), dcc.Dropdown(id="medida", value="interanual", clearable=False,
                  options=[{"label": v[0], "value": k} for k, v in MEDIDAS.items()], style={"width": "330px"})]),
        html.Div([html.Label("Comparar Salud con"), dcc.Dropdown(id="comparador", value="GEN", clearable=False,
                  options=[{"label": NOMBRES[c], "value": c} for c in COMPARADORES], style={"width": "300px"})]),
        html.Div([html.Label("Extra"), dcc.Checklist(id="ver_suby", value=[],
                  options=[{"label": " Mostrar inflación subyacente (solo interanual)", "value": "s"}])]),
    ], style={"display": "flex", "gap": "30px", "flexWrap": "wrap", "margin": "10px 0"}),
    html.Div(id="tarjetas"),
    dcc.Graph(id="g_evolucion"), dcc.Graph(id="g_brecha"),
], style=CAJA)

tab2 = html.Div([
    dcc.Graph(figure=fig_treemap(), style={"height": "560px"}),
    html.Hr(),
    html.Div([
        html.Div([html.Label("Componente de Salud"), dcc.Dropdown(id="nodo", value="06", clearable=False,
                  options=opciones_nodos(), style={"width": "560px"})]),
        html.Div([html.Label("Medida"), dcc.RadioItems(id="medida_nodo", value="indice", options=[
            {"label": " Índice", "value": "indice"}, {"label": " Inflación interanual", "value": "interanual"},
            {"label": " Variación mensual", "value": "mensual"}])]),
        html.Div(id="info_nodo", style=ESTILO_TARJETA),
    ], style={"display": "flex", "gap": "30px", "flexWrap": "wrap", "alignItems": "flex-start"}),
    dcc.Graph(id="g_nodo"),
], style=CAJA)

tab3 = html.Div([
    dcc.Graph(figure=fig_aportes()),
    html.Div([html.Label("Ventana"), dcc.Dropdown(id="ventana_top", value=contrib["ventana"].unique()[-1], clearable=False,
              options=[{"label": v, "value": v} for v in contrib["ventana"].unique()], style={"width": "420px"})]),
    dcc.Graph(id="g_top"),
], style=CAJA)

tab4 = html.Div([
    html.P("Cada ventana es el período de inflación que el CNSS reconoció en una resolución. La regla vigente promedia la "
           "variación del IPC general y del IPC Salud. Los montos son ilustrativos: se aplican al per cápita de cada resolución."),
    dcc.Graph(figure=fig_tasas()), dcc.Graph(figure=fig_montos()), tabla_indexacion(),
    html.H4("Simulador: inflación todavía sin reconocer"),
    html.Div([
        html.Div([html.Label("Per cápita (RD$)"), dcc.Input(id="sim_base", type="number", value=1887.54, step=0.01, debounce=True, style={"width": "150px"})]),
        html.Div([html.Label("Regla"), dcc.RadioItems(id="sim_regla", value="promedio", options=[
            {"label": " Promedio", "value": "promedio"}, {"label": " Solo general", "value": "general"},
            {"label": " Solo Salud", "value": "salud"}])]),
        html.Div([html.Label("Hasta"), dcc.RadioItems(id="sim_hasta", value="sin reconocer (a mar-2026)", options=[
            {"label": " Marzo 2026", "value": "sin reconocer (a mar-2026)"},
            {"label": " Agosto 2026 (extra)", "value": "sin reconocer (a ago-2026)"}])]),
    ], style={"display": "flex", "gap": "30px", "flexWrap": "wrap"}),
    html.P(id="sim_texto", style={"fontWeight": "bold", "marginTop": "12px"}),
], style=CAJA)

tab5 = html.Div([dcc.Markdown(FUENTES)], style=CAJA)

app.layout = html.Div([
    html.Div([html.H2("IPC de Salud y la indexación del per cápita del PDSS", style={"margin": "0"}),
              html.Div("República Dominicana · Enero 2021 a marzo 2026 · Fuente: Banco Central, CNSS", style={"color": GRIS})],
             style={"padding": "16px 20px", "borderBottom": "1px solid #d5d9e0"}),
    dcc.Tabs(children=[
        dcc.Tab(label="1. Evolución", children=tab1), dcc.Tab(label="2. Jerarquía de Salud", children=tab2),
        dcc.Tab(label="3. Qué mueve a Salud", children=tab3), dcc.Tab(label="4. Indexación", children=tab4),
        dcc.Tab(label="Fuentes y límites", children=tab5)]),
], style={"fontFamily": "Calibri, Arial, sans-serif"})


@app.callback(Output("g_evolucion", "figure"), Output("g_brecha", "figure"), Output("tarjetas", "children"),
              Input("periodo", "value"), Input("medida", "value"), Input("comparador", "value"), Input("ver_suby", "value"))
def actualizar_evolucion(periodo, medida, comparador, ver_suby):
    return fig_evolucion(periodo, medida, comparador, bool(ver_suby)), fig_brecha(periodo, medida, comparador), tarjetas(periodo, comparador)


@app.callback(Output("g_nodo", "figure"), Output("info_nodo", "children"), Input("nodo", "value"), Input("medida_nodo", "value"))
def actualizar_nodo(cod, medida):
    return fig_nodo(cod, medida), info_nodo(cod)


@app.callback(Output("g_top", "figure"), Input("ventana_top", "value"))
def actualizar_top(ventana):
    return fig_top(ventana)


@app.callback(Output("sim_texto", "children"), Input("sim_base", "value"), Input("sim_regla", "value"), Input("sim_hasta", "value"))
def actualizar_simulador(base, regla, hasta):
    return simular(base, regla, hasta)


if __name__ == "__main__":
    app.run(debug=False)

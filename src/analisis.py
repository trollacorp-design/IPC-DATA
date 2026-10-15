
from pathlib import Path

import pandas as pd

DATOS = Path("data/processed")
T = lambda y, m: pd.Timestamp(y, m, 1)

# Ventanas de indexacion reconocidas por el CNSS: (resolucion, primer mes, ultimo mes,
# monto de indexacion en RD$, per capita sobre el que se aplico). Fuente: textos de las resoluciones.
VENTANAS = [
    ("533-01", T(2019, 8), T(2021, 2), 94.46, 1167.81),
    ("553-02", T(2021, 3), T(2022, 3), 102.71, 1327.81),
    ("581-03", T(2022, 4), T(2023, 3), 81.71, 1555.14),
    ("624-02", T(2023, 4), T(2025, 3), 142.08, 1683.22),
]
ABIERTAS = [  # sin reconocer todavia (la 645-16 no incluye indexacion)
    ("sin reconocer (a mar-2026)", T(2025, 4), T(2026, 3), 1887.54),
    ("sin reconocer (a ago-2026)", T(2025, 4), T(2026, 8), 1887.54),
]


def mes_previo(f: pd.Timestamp) -> pd.Timestamp:
    return f - pd.DateOffset(months=1)


# ----------------------------------------------------------------------------- A. Salud vs general
def analisis_brecha(series: pd.DataFrame) -> pd.DataFrame:
    p = series.pivot(index="fecha", columns="codigo", values="var_interanual")[["GEN", "06"]]
    idx = series.pivot(index="fecha", columns="codigo", values="indice")[["GEN", "06"]]
    out = pd.DataFrame({"general": p["GEN"], "salud": p["06"]})
    out["brecha_pp"] = out["salud"] - out["general"]
    base = idx.loc[T(2020, 12)]
    out["acum_general"] = (idx["GEN"] / base["GEN"] - 1) * 100       # desde dic-2020
    out["acum_salud"] = (idx["06"] / base["06"] - 1) * 100
    return out.loc[T(2021, 1):T(2026, 3)].reset_index()


def resumen_brecha(b: pd.DataFrame) -> None:
    n = len(b)
    pos = (b["brecha_pp"] > 0).sum()
    cambios = b[(b["brecha_pp"] > 0) != (b["brecha_pp"] > 0).shift()].iloc[1:]
    print(f"A. SALUD CONTRA EL GENERAL ({b['fecha'].min():%Y-%m} a {b['fecha'].max():%Y-%m}, {n} meses)")
    print(f"   Meses con Salud por encima del general: {pos} de {n}")
    print("   Cambios de signo de la brecha:", ", ".join(f"{f:%Y-%m}" for f in cambios["fecha"]) or "ninguno")
    mn, mx = b.loc[b["brecha_pp"].idxmin()], b.loc[b["brecha_pp"].idxmax()]
    print(f"   Brecha minima: {mn['brecha_pp']:+.2f} pp ({mn['fecha']:%Y-%m}) | maxima: {mx['brecha_pp']:+.2f} pp ({mx['fecha']:%Y-%m})")
    u = b.iloc[-1]
    print(f"   Acumulado dic-2020 a mar-2026: general {u['acum_general']:.1f}% | Salud {u['acum_salud']:.1f}%")
    por_ano = b.groupby(b["fecha"].dt.year)["brecha_pp"].mean().round(2)
    print("   Brecha media por ano (pp):", ", ".join(f"{a}: {v:+.2f}" for a, v in por_ano.items()))


# ----------------------------------------------------------------------------- B. Que mueve a Salud
def contribuciones(largo: pd.DataFrame, base: pd.Timestamp, fin: pd.Timestamp, etiqueta: str) -> pd.DataFrame:
    """Aporte de cada nodo a la variacion de Salud entre dos fechas, en puntos porcentuales de Salud.
    c_i = peso_i x (indice_i fin - indice_i base) / (peso_Salud x indice_Salud base) x 100"""
    ancho = largo.pivot(index="fecha", columns="codigo", values="indice")
    info = largo.drop_duplicates("codigo").set_index("codigo")[["nombre", "nivel", "ponderacion", "subgrupo_cod"]]
    salud = info[(info.index.str.startswith("06")) & (info["nivel"].isin(["subgrupo", "articulo"]))].copy()
    w_s = info.loc["06", "ponderacion"]
    delta = ancho.loc[fin, salud.index] - ancho.loc[base, salud.index]
    salud["contribucion_pp"] = salud["ponderacion"] * delta / (w_s * ancho.loc[base, "06"]) * 100
    var_salud = (ancho.loc[fin, "06"] / ancho.loc[base, "06"] - 1) * 100
    for nivel in ["subgrupo", "articulo"]:      # los aportes de cada nivel deben sumar la variacion de Salud
        suma = salud.loc[salud["nivel"] == nivel, "contribucion_pp"].sum()
        assert abs(suma - var_salud) < 0.02, f"Los aportes ({nivel}) no suman la variacion de Salud"
    salud["parte_pct"] = salud["contribucion_pp"] / var_salud * 100
    salud["ventana"], salud["var_salud_pct"] = etiqueta, var_salud
    return salud.reset_index().rename(columns={"index": "codigo"})


def analisis_contribuciones(largo: pd.DataFrame) -> pd.DataFrame:
    ventanas = [(f"{r[0]} ({r[1]:%Y-%m} a {r[2]:%Y-%m})", mes_previo(r[1]), r[2]) for r in VENTANAS[1:]]
    ventanas += [("Abierta (2025-04 a 2026-03)", T(2025, 3), T(2026, 3)),
                 ("Completa (2021-01 a 2026-03)", T(2020, 12), T(2026, 3))]
    return pd.concat([contribuciones(largo, b, f, e) for e, b, f in ventanas], ignore_index=True)


def resumen_contribuciones(c: pd.DataFrame) -> None:
    print("\nB. QUE MUEVE A SALUD (parte de la variacion de Salud, % por subgrupo)")
    # Las columnas se eligen y nombran por CODIGO de subgrupo, nunca por posicion
    nombres = {"061": "Medicamentos y equipos", "062": "Servicios ambulatorios", "063": "Hospital"}
    for cod, nom in [("061", "Productos"), ("062", "Servicios para Pacientes"), ("063", "Servicios de Hospital")]:
        assert c.loc[c["codigo"] == cod, "nombre"].iloc[0].startswith(nom), f"Subgrupo {cod} no es '{nom}'"
    sg = c[c["nivel"] == "subgrupo"].pivot(index="ventana", columns="codigo", values="parte_pct")
    sg = sg.loc[c["ventana"].unique(), list(nombres)].rename(columns=nombres)
    sg.insert(0, "Salud %", [c[c["ventana"] == v]["var_salud_pct"].iloc[0] for v in sg.index])
    peso = c[(c["nivel"] == "subgrupo") & (c["ventana"] == c["ventana"].iloc[0])].set_index("codigo")["ponderacion"]
    fila_peso = pd.DataFrame([[float("nan")] + list((peso[list(nombres)] / peso.sum() * 100).values)],
                             columns=sg.columns, index=["Peso en Salud (%)"])
    print(pd.concat([fila_peso, sg]).round(1).to_string(na_rep=""))
    for v in ["Abierta (2025-04 a 2026-03)", "Completa (2021-01 a 2026-03)"]:
        a = c[(c["ventana"] == v) & (c["nivel"] == "articulo")].nlargest(5, "contribucion_pp")
        print(f"   Mayores aportes en '{v}':", "; ".join(f"{n.strip()[:28]} {p:.0f}%" for n, p in zip(a["nombre"], a["parte_pct"])))


# ----------------------------------------------------------------------------- C. Ejercicio de indexacion
def analisis_indexacion(series: pd.DataFrame) -> pd.DataFrame:
    idx = series.pivot(index="fecha", columns="codigo", values="indice")[["GEN", "06"]]

    def tasas(ini, fin):    # variacion desde el mes previo al primer mes de la ventana hasta su ultimo mes
        base = mes_previo(ini)
        g = (idx.loc[fin, "GEN"] / idx.loc[base, "GEN"] - 1) * 100
        s = (idx.loc[fin, "06"] / idx.loc[base, "06"] - 1) * 100
        return g, s, (g + s) / 2

    filas = []
    for res, ini, fin, monto, base_pc in VENTANAS:
        g, s, p = tasas(ini, fin)
        filas.append(dict(ventana=res, periodo=f"{ini:%Y-%m} a {fin:%Y-%m}", per_capita_base=base_pc,
                          reconocido_rd=monto, reconocido_pct=monto / base_pc * 100,
                          general_pct=g, salud_pct=s, promedio_pct=p, diferencia_pp=monto / base_pc * 100 - p,
                          si_general_rd=base_pc * g / 100, si_salud_rd=base_pc * s / 100, si_promedio_rd=base_pc * p / 100))
    for res, ini, fin, base_pc in ABIERTAS:
        g, s, p = tasas(ini, fin)
        filas.append(dict(ventana=res, periodo=f"{ini:%Y-%m} a {fin:%Y-%m}", per_capita_base=base_pc,
                          reconocido_rd=0.0, reconocido_pct=0.0, general_pct=g, salud_pct=s, promedio_pct=p,
                          diferencia_pp=float("nan"), si_general_rd=base_pc * g / 100,
                          si_salud_rd=base_pc * s / 100, si_promedio_rd=base_pc * p / 100))
    return pd.DataFrame(filas)


def resumen_indexacion(x: pd.DataFrame) -> None:
    print("\nC. EJERCICIO DE INDEXACION (tasa = desde el mes previo a la ventana hasta su ultimo mes)")
    cols = ["ventana", "periodo", "reconocido_pct", "general_pct", "salud_pct", "promedio_pct", "diferencia_pp"]
    print(x[cols].round(2).to_string(index=False))
    r = x.iloc[1:4]   # ventanas 553-02, 581-03 y 624-02: las que verificamos contra el texto
    print("\n   RD$ por ventana si se hubiera usado cada regla (ilustrativo, sobre el per capita de cada resolucion):")
    print(x[["ventana", "reconocido_rd", "si_general_rd", "si_salud_rd", "si_promedio_rd"]].round(2).to_string(index=False))
    print(f"   Suma 553-02 + 581-03 + 624-02: reconocido {r['reconocido_rd'].sum():.2f} | "
          f"solo general {r['si_general_rd'].sum():.2f} | solo Salud {r['si_salud_rd'].sum():.2f} | "
          f"promedio {r['si_promedio_rd'].sum():.2f}")
    print(f"   Error maximo del promedio contra lo reconocido (553-02, 581-03, 624-02): "
          f"{r['diferencia_pp'].abs().max():.2f} pp")


def main() -> None:
    series = pd.read_parquet(DATOS / "ipc_series_oficiales.parquet")
    largo = pd.read_parquet(DATOS / "ipc_largo.parquet")

    brecha = analisis_brecha(series)
    resumen_brecha(brecha)
    contrib = analisis_contribuciones(largo)
    resumen_contribuciones(contrib)
    indexacion = analisis_indexacion(series)
    resumen_indexacion(indexacion)

    brecha.to_parquet(DATOS / "analisis_brecha.parquet", index=False)
    contrib.to_parquet(DATOS / "analisis_contribuciones.parquet", index=False)
    indexacion.to_parquet(DATOS / "analisis_indexacion.parquet", index=False)


if __name__ == "__main__":
    main()

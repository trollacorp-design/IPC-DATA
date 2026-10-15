
from pathlib import Path

import pandas as pd

DATOS = Path("data/processed")
GRUPOS = [f"{i:02d}" for i in range(1, 13)]


def calcular(largo: pd.DataFrame) -> pd.DataFrame:
    # Matriz fecha x codigo: permite calcular todos los nodos a la vez
    ancho = largo.pivot(index="fecha", columns="codigo", values="indice")
    peso = largo.drop_duplicates("codigo").set_index("codigo")["ponderacion"]
    general = ancho["GEN"]

    var_mensual = ancho.pct_change() * 100
    var_interanual = ancho.pct_change(12) * 100

    # Acumulada: la base de cada ano es el diciembre del ano anterior
    diciembres = ancho[ancho.index.month == 12].copy()
    diciembres.index = diciembres.index.year + 1
    base = diciembres.reindex(ancho.index.year)
    base.index = ancho.index
    var_acumulada = (ancho / base - 1) * 100

    # Incidencia = peso x cambio del indice del nodo / indice general del periodo base.
    # Funciona en cualquier nivel porque la ponderacion es la parte de cada nodo en el total (100).
    inc_mensual = ancho.diff().mul(peso / 100).div(general.shift(1), axis=0) * 100
    inc_interanual = ancho.diff(12).mul(peso / 100).div(general.shift(12), axis=0) * 100

    salida = largo.copy()
    for nombre, tabla in [("var_mensual", var_mensual), ("var_acumulada", var_acumulada),
                          ("var_interanual", var_interanual), ("inc_mensual", inc_mensual),
                          ("inc_interanual", inc_interanual)]:
        plano = tabla.reset_index().melt(id_vars="fecha", var_name="codigo", value_name=nombre)
        salida = salida.merge(plano, on=["fecha", "codigo"], how="left")
    return salida


def validar(ind: pd.DataFrame) -> None:
    """Compara contra el informe oficial de enero 2021 y la grafica oficial de marzo 2026."""
    def valor(cod, fecha, col):
        f = (ind["codigo"] == cod) & (ind["fecha"] == pd.Timestamp(fecha))
        return ind.loc[f, col].iloc[0]

    # Informe del BCRD, enero 2021 (tabla "Inflacion e incidencia", 12 grupos)
    var_oficial = [1.06, 0.97, 0.26, 1.11, 0.30, 0.45, 2.08, -0.04, 0.10, 0.44, 0.90, 0.50]
    inc_oficial = [0.26, 0.02, 0.01, 0.14, 0.02, 0.02, 0.35, 0.00, 0.00, 0.01, 0.08, 0.05]
    for g, v, i in zip(GRUPOS, var_oficial, inc_oficial):
        assert abs(valor(g, "2021-01-01", "var_mensual") - v) < 0.006, f"var mensual grupo {g}"
        assert abs(valor(g, "2021-01-01", "inc_mensual") - i) < 0.006, f"incidencia grupo {g}"
    assert abs(valor("GEN", "2021-01-01", "var_mensual") - 0.97) < 0.006

    # Grafica oficial del BCRD: inflacion interanual general de marzo 2026 = 4.63%
    assert abs(valor("GEN", "2026-03-01", "var_interanual") - 4.63) < 0.006

    # Las incidencias de los 12 grupos deben sumar la variacion del IPC general
    g = ind[ind["codigo"].isin(GRUPOS)].groupby("fecha")
    suma_m = g["inc_mensual"].sum(min_count=12)
    suma_i = g["inc_interanual"].sum(min_count=12)
    gen = ind[ind["codigo"] == "GEN"].set_index("fecha")
    assert (suma_m - gen["var_mensual"]).abs().max() < 0.01
    assert (suma_i - gen["var_interanual"]).abs().max() < 0.01

    # Cobertura: la interanual existe desde oct 2021; la acumulada desde ene 2021
    sin_hist = ind["fecha"] < "2021-10-01"
    assert ind.loc[sin_hist, "var_interanual"].isna().all()
    assert ind.loc[~sin_hist, "var_interanual"].notna().all()
    assert abs(valor("06", "2021-01-01", "var_acumulada") - valor("06", "2021-01-01", "var_mensual")) < 1e-9
    print("Validaciones OK")


def main() -> None:
    largo = pd.read_parquet(DATOS / "ipc_largo.parquet")
    ind = calcular(largo)
    validar(ind)

    ind.to_parquet(DATOS / "ipc_indicadores.parquet", index=False)
    ind[ind["grupo_cod"] == "06"].to_parquet(DATOS / "ipc_salud_indicadores.parquet", index=False)
    print(f"Filas: {len(ind):,} | Columnas: {ind.shape[1]}")

    # Vista rapida: inflacion interanual (%) de Salud frente a la general, cada marzo
    marzos = ind[(ind["fecha"].dt.month == 3) & (ind["fecha"].dt.year >= 2022)
                 & ind["codigo"].isin(["GEN", "06"])]
    tabla = marzos.pivot(index="fecha", columns="nombre", values="var_interanual")
    print(tabla[["Indice General", "Salud"]].round(2).to_string())


if __name__ == "__main__":
    main()

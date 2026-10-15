
from pathlib import Path

import pandas as pd

RAW = Path("data/raw/ipc_articulos_base_2019-2020.xlsx")
OUT = Path("data/processed")

COLS_ID = ["grupo", "subgrupo", "clase", "subclase", "articulo"]
# Largo del codigo -> nivel de la jerarquia (ej. "0611101" tiene 7 digitos = articulo)
NIVEL_POR_LARGO = {2: "grupo", 3: "subgrupo", 4: "clase", 5: "subclase", 7: "articulo"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def cargar_ancho() -> pd.DataFrame:
    """Lee la hoja y le pone fechas reales a las columnas de meses."""
    df = pd.read_excel(RAW, sheet_name="2020-2026", header=3)
    df = df.dropna(how="all").reset_index(drop=True)

    n_meses = df.shape[1] - 6  # 5 columnas de jerarquia + ponderacion
    # Las etiquetas de ano del Excel estan mal colocadas, asi que las fechas se
    # construyen por POSICION: la primera columna de datos es octubre 2020.
    fechas = pd.date_range("2020-10-01", periods=n_meses, freq="MS")

    # Control: los nombres de mes del encabezado deben coincidir con esas fechas.
    # (pandas agrega ".1", ".2" a los nombres repetidos; el Excel trae espacios sobrantes)
    en_excel = [str(c).split(".")[0].strip().lower() for c in df.columns[6:]]
    esperado = [MESES[f.month - 1] for f in fechas]
    assert en_excel == esperado, "Los meses del encabezado no coinciden con las fechas"

    df.columns = COLS_ID + ["ponderacion"] + list(fechas)
    return df


def construir_metadatos(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por nodo: codigo, nombre, nivel, ponderacion y codigos/nombres de sus padres."""
    # Cada fila tiene llena solo la columna de su propio nivel; las demas estan vacias.
    etiqueta = df[COLS_ID].bfill(axis=1).iloc[:, 0].str.strip()

    codigo = etiqueta.str.extract(r"^(\d+)")[0]          # "0611 Productos..." -> "0611"
    nombre = etiqueta.str.replace(r"^\d+\s*", "", regex=True).str.strip()
    nivel = codigo.str.len().map(NIVEL_POR_LARGO)

    es_general = codigo.isna()                           # solo la fila "Indice General"
    assert not (nivel.isna() & ~es_general).any(), "Hay codigos con largo inesperado"
    nivel = nivel.where(~es_general, "general")
    codigo = codigo.where(~es_general, "GEN")

    meta = pd.DataFrame({"codigo": codigo, "nombre": nombre, "nivel": nivel,
                         "ponderacion": df["ponderacion"]})
    assert meta["codigo"].is_unique, "Hay codigos repetidos"

    # Los padres se obtienen por prefijo del codigo: "0611101" -> "06111" -> "0611" -> "061" -> "06"
    for n, col in [(2, "grupo"), (3, "subgrupo"), (4, "clase"), (5, "subclase")]:
        pref = meta["codigo"].where((meta["codigo"].str.len() >= n) & ~es_general).str[:n]
        meta[f"{col}_cod"] = pref
        meta[f"{col}_nombre"] = pref.map(meta.set_index("codigo")["nombre"])
    return meta


def a_formato_largo(df: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """De ancho (un mes por columna) a largo (una fila por nodo y mes)."""
    ancho = pd.concat([meta, df.iloc[:, 6:]], axis=1)
    largo = ancho.melt(id_vars=list(meta.columns), var_name="fecha", value_name="indice")
    largo["fecha"] = pd.to_datetime(largo["fecha"])
    return largo.sort_values(["codigo", "fecha"]).reset_index(drop=True)


def validar(largo: pd.DataFrame) -> None:
    """Compara contra cifras oficiales ya verificadas. Si algo no cuadra, se detiene."""
    def idx(cod, anio, mes):
        f = (largo["codigo"] == cod) & (largo["fecha"] == pd.Timestamp(anio, mes, 1))
        return largo.loc[f, "indice"].iloc[0]

    # Informe del BCRD de enero 2021 (indices con 2 decimales)
    for cod, a, m, oficial in [("06", 2020, 12, 104.77), ("06", 2021, 1, 105.24),
                               ("GEN", 2020, 12, 104.39), ("GEN", 2021, 1, 105.40)]:
        assert abs(idx(cod, a, m) - oficial) < 0.006, f"No cuadra {cod} {a}-{m:02d}"

    primer_mes = largo["fecha"].min()
    nodos = largo[largo["fecha"] == primer_mes]
    assert abs(nodos.loc[nodos["nivel"] == "grupo", "ponderacion"].sum() - 100) < 0.01
    salud = nodos[nodos["grupo_cod"] == "06"]
    assert abs(salud.loc[salud["nivel"] == "grupo", "ponderacion"].iloc[0] - 4.74) < 0.01
    assert abs(salud.loc[salud["nivel"] == "subgrupo", "ponderacion"].sum() - 4.74) < 0.01

    # Cuadro 03 del documento metodologico: Salud = 3 subgrupos, 6 clases, 7 subclases, 32 articulos
    conteo = salud["nivel"].value_counts().to_dict()
    assert conteo == {"grupo": 1, "subgrupo": 3, "clase": 6, "subclase": 7, "articulo": 32}, conteo
    assert largo.loc[largo["grupo_cod"] == "06", "indice"].notna().all()
    print("Validaciones OK")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = cargar_ancho()
    meta = construir_metadatos(df)
    largo = a_formato_largo(df, meta)
    validar(largo)

    largo.to_parquet(OUT / "ipc_largo.parquet", index=False)
    largo[largo["grupo_cod"] == "06"].to_parquet(OUT / "ipc_salud.parquet", index=False)
    largo[largo["nivel"].isin(["grupo", "general"])].to_parquet(OUT / "ipc_grupos.parquet", index=False)

    print(f"Filas: {len(largo):,} | Nodos: {largo['codigo'].nunique()} | "
          f"Periodo: {largo['fecha'].min():%Y-%m} a {largo['fecha'].max():%Y-%m}")
    resumen = largo[(largo["grupo_cod"] == "06")
                    & largo["nivel"].isin(["grupo", "subgrupo"])
                    & (largo["fecha"] == largo["fecha"].min())]
    print(resumen[["codigo", "nombre", "nivel", "ponderacion"]].to_string(index=False))

if __name__ == "__main__":
    main()

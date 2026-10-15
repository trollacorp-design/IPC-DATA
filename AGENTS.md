# Contexto del proyecto (leer completo antes de actuar)

## Qué es
Trabajo de investigación para optar a Analista Científico de Datos (ARS Primera, Inteligencia PDSS).
Tema: el rubro de Salud en el IPC del Banco Central (BCRD), enero 2021 a marzo 2026, y su uso para indexar el
per cápita base del PDSS (régimen contributivo del SFS). Se sustenta por teleconferencia: el autor debe poder
explicar cada decisión de datos y de código. Explica cada cambio en lenguaje simple.

## Entregables y restricciones
1. Ensayo PDF, máximo 4 páginas de cuerpo, Calibri 12, interlineado sencillo (bibliografía y anexos aparte).
2. Archivos Parquet con los datos usados (carpeta `data/processed`).
3. Dashboard web interactivo con código en GitHub. **Prohibido** Excel, Power BI, Tableau. Ya está hecho en Python con Dash.

## Entorno
Windows + PowerShell. Python con entorno virtual `.venv` (activar con `.venv\Scripts\activate`).
Correr siempre desde la raíz del proyecto (`IPC-DATA`). Librerías en `requirements.txt`.

## Scripts (orden de ejecución) y qué produce cada uno
| Script | Produce (en data/processed) |
|---|---|
| `src/limpiar_ipc.py` | ipc_largo, ipc_salud, ipc_grupos (612 nodos x 71 meses, oct-2020 a ago-2026) |
| `src/calcular_indicadores.py` | ipc_indicadores, ipc_salud_indicadores (var. mensual, acumulada, interanual, incidencias) |
| `src/integrar_cuadros.py` | ipc_series_oficiales (general + 12 grupos, 1999-2026), subyacente, anexo3_clasificacion, salud_componentes |
| `src/analisis.py` | analisis_brecha, analisis_contribuciones, analisis_indexacion |
| `dashboard/app.py` | app Dash en http://127.0.0.1:8050 (`python dashboard/app.py`) |
Cada script valida contra cifras oficiales y se detiene si algo no cuadra. No quitar esas validaciones.

## Fuentes (data/raw; nombres pueden tener espacios; los scripts buscan por patrón)
- `ipc_articulos_base_2019-2020.xlsx` (IPC por artículos, oct-2020 a ago-2026, hoja "2020-2026")
- `Cuadros Publicación IPC 2025.xlsx` (BCRD: cuadros 3.1, 3.3, 3.8, hasta dic-2025)
- `Anexos Publicación IPC base anual oct 2019 - sep 2020.xlsx` (Anexo 3: clasificación de artículos)
- `cipc_anual2025.pdf` e informes `Informe-IPC-2026-01/02/03.pdf` en `data/raw/pdfs` (respaldo y subyacente 2026)

## Cifras de referencia para verificar que nada se rompió
- Índice Salud dic-2020 = 104.77, ene-2021 = 105.24. Índice general dic-2020 = 104.39, ene-2021 = 105.40.
- Inflación interanual marzo 2026: general 4.63%, Salud 5.53%, subyacente 4.58%.
- Peso de Salud 4.74%: 3 subgrupos (061 = 3.31, 062 = 0.92, 063 = 0.51), 6 clases, 7 subclases, 32 artículos (todos subyacentes; 21 bienes, 11 servicios).
- Salud por encima del general: 37 de 63 meses; cambios de signo en 2021-02 y 2023-04.
- Indexación reconocida por el CNSS (RD$ y base): 553-02 = 102.71 sobre 1,327.81; 581-03 = 81.71 sobre 1,555.14; 624-02 = 142.08 sobre 1,683.22.
- Per cápita vigente: 1,887.54 (res. 624-02) y 1,938.18 (res. 645-16, que no incluye indexación).

## Decisiones tomadas
- Serie 2021: la oficial empalmada del BCRD. Ventana del ensayo: ene-2021 a mar-2026 (abr a ago-2026 solo como extra).
- Niveles bajos (subgrupo a artículo): interanual desde oct-2021 (el índice por artículos empieza en oct-2020).
- Regla de indexación (CNSS desde 2021): promedio de la variación del IPC general y del IPC Salud. El ejercicio la mide desde el mes previo
  a cada ventana hasta su último mes; reproduce lo reconocido con error máximo de 0.45 pp (no exacto).

## Límites que deben seguir visibles
No hay estructura de gasto del PDSS por tipo de servicio; no se puede afirmar que el IPC de Salud subestime su costo.
Seis celdas del bloque anual del Cuadro 3.3 (2013-2017) son erróneas; se usan los índices.

## Reglas de trabajo para el agente
- No inventar datos ni cifras. Si falta algo, decirlo.
- Si se cambia un cálculo, volver a correr los scripts en orden y comparar con las cifras de referencia.
- Etiquetar columnas por código, nunca por posición después de un pivot (ya causó errores dos veces).
- Hacer `git commit` con mensaje claro después de cada tarea.

## Pendiente
README, .gitignore, congelar versiones en requirements.txt, subir a GitHub, ensayo PDF y preparación de la sustentación.

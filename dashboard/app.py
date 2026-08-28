"""
app.py — Dashboard Streamlit of Unified Data Insights Platform.

Interactive dashboard for analyzing consolidated user and activity data.
Designed to explore KPIs, trends, distributions, and source coverage.

Uso:
    streamlit run dashboard/app.py

Arquitectura de filtros (v1.1.0):
    Un único DataFrame filtrado (df_filtered) alimenta todos los KPIs,
    gráficos y la tabla. Los filtros globales del sidebar son:
        Región | Fuente | Situación habitacional | Género | Rango de edad | Búsqueda

    Excepción: chart_registros_por_situacion recibe df_filtered_sin_sh
    (sin filtro de SH) porque esa variable constituye las categorías
    del propio gráfico. Conserva sus filtros locales de período.

DataProvider soportados:
    SQLiteDataProvider  → database/deficit_cero.db  (default)
    CSVDataProvider     → data/processed/usuarios_master.csv (fallback)

Project: Unified Data Insights Platform
Versión: 1.1.0
"""

import sys
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Agregar raíz del proyecto al path (compatible con Nuitka: usa resolve()
# para path absoluto y evita duplicados). En binario compilado el path
# lo gestiona el launcher, pero en desarrollo (streamlit run) es necesario.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.settings import DB_PATH, MASTER_CSV_PATH
from scripts.analytics import (
    AnalyticsResult,
    compute_analytics,
    get_master_dataframe,
)


# ── Paleta de colores ─────────────────────────────────────────────────────────

PALETTE: dict[str, str] = {
    "primary":   "#16543E",
    "secondary": "#22863A",
    "accent":    "#54D48F",
    "registro":  "#3B82F6",
    "talleres":  "#7C3AED",
    "zoom":      "#F59E0B",
    "minga":     "#10B981",
    "neutral":   "#6B7280",
    "border":    "#E5E7EB",
    "bg":        "#F8FAF9",
}

SOURCE_COLORS: list[str] = [
    PALETTE["registro"],
    PALETTE["talleres"],
    PALETTE["zoom"],
    PALETTE["minga"],
]

PLOTLY_TEMPLATE = "plotly_white"

# Paleta de situaciones habitacionales — compartida por chart_situacion_habitacional
# y chart_registros_por_situacion para coherencia visual entre ambos gráficos.
_SH_CATEGORIAS: list[tuple[str, str]] = [
    ("allegado",           "#7C3AED"),
    ("arriendo",           "#F59E0B"),
    ("campamento",         "#EC4899"),
    ("situacion_de_calle", "#EF4444"),
    ("vivienda_cedida",    "#1E3A8A"),
    ("vivienda_propia",    "#06B6D4"),
]
_SH_COLOR_MAP: dict[str, str] = {k: v for k, v in _SH_CATEGORIAS}

# Rangos de edad oficiales del proyecto
_RANGOS_EDAD: list[str] = [
    "18\u201329 años",
    "30\u201339 años",
    "40\u201349 años",
    "50\u201359 años",
    "60 años o más",
]
_RANGOS_EDAD_LIMITES: dict[str, tuple[int, int | None]] = {
    "18\u201329 años":   (18, 30),
    "30\u201339 años":   (30, 40),
    "40\u201349 años":   (40, 50),
    "50\u201359 años":   (50, 60),
    "60 años o más":     (60, None),
}


# ── DataProvider ──────────────────────────────────────────────────────────────

class DataProvider(ABC):
    """
    Abstracción de fuente de datos para el dashboard.

    Permite cambiar el backend (SQLite → PostgreSQL → Google Sheets)
    sin modificar ningún componente de visualización.
    """

    @abstractmethod
    def get_analytics(self) -> AnalyticsResult:
        """Retorna el AnalyticsResult con metadatos globales del run."""

    @abstractmethod
    def get_dataframe(self) -> pd.DataFrame:
        """Retorna el DataFrame completo de usuarios_master."""

    @property
    @abstractmethod
    def source_label(self) -> str:
        """Etiqueta descriptiva de la fuente."""


class SQLiteDataProvider(DataProvider):
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    def get_analytics(self) -> AnalyticsResult:
        return compute_analytics(db_path=self._db_path, csv_path=Path("__none__"))

    def get_dataframe(self) -> pd.DataFrame:
        df, _ = get_master_dataframe(db_path=self._db_path, csv_path=Path("__none__"))
        return df

    @property
    def source_label(self) -> str:
        return "SQLite local"


class CSVDataProvider(DataProvider):
    def __init__(self, csv_path: Path = MASTER_CSV_PATH) -> None:
        self._csv_path = csv_path

    def get_analytics(self) -> AnalyticsResult:
        return compute_analytics(db_path=Path("__none__"), csv_path=self._csv_path)

    def get_dataframe(self) -> pd.DataFrame:
        df, _ = get_master_dataframe(db_path=Path("__none__"), csv_path=self._csv_path)
        return df

    @property
    def source_label(self) -> str:
        return "CSV consolidado"


# ── Helpers puros ─────────────────────────────────────────────────────────────

def _fmt(n: int | float) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(n)


def _pct(num: int, den: int) -> str:
    if den == 0:
        return "—"
    return f"{(num / den * 100):.1f}%"


def apply_filters(
    df: pd.DataFrame,
    regiones: list[str],
    fuentes: list[str],
    situaciones: list[str],
    generos: list[str],
    rangos_edad: list[str],
    busqueda: str,
) -> pd.DataFrame:
    """
    Aplica los seis filtros globales al DataFrame maestro.

    Lógica: AND entre grupos de filtros, OR dentro de cada grupo.
    Los filtros vacíos se ignoran (equivale a seleccionar todos).

    Filtro de edad:
        Calculado desde fecha_nacimiento con la fecha de hoy.
        Usuarios sin fecha_nacimiento quedan excluidos cuando el filtro
        de rango de edad está activo — comportamiento correcto ya que
        no es posible clasificarlos.

    Args:
        df:          DataFrame completo de usuarios_master.
        regiones:    Regiones seleccionadas.
        fuentes:     Fuentes: "registro"|"talleres"|"asistencia"|"minga".
        situaciones: Valores de situacion_habitacional seleccionados.
        generos:     Valores de genero seleccionados.
        rangos_edad: Etiquetas de rangos de edad seleccionados.
        busqueda:    Texto libre para email, nombre o apellido.

    Returns:
        Subconjunto del DataFrame que cumple todos los filtros activos.
    """
    if df.empty:
        return df

    mask = pd.Series([True] * len(df), index=df.index)

    # Filtro por región
    if regiones and "region" in df.columns:
        mask &= df["region"].isin(regiones)

    # Filtro por fuente (OR interno)
    _flag = {
        "registro":   "tiene_registro_web",
        "talleres":   "inscrito_taller",
        "asistencia": "asistio_taller",
        "minga":      "uso_minga",
    }
    if fuentes:
        fuente_mask = pd.Series([False] * len(df), index=df.index)
        for f in fuentes:
            col = _flag.get(f)
            if col and col in df.columns:
                fuente_mask |= df[col].astype(bool)
        mask &= fuente_mask

    # Filtro por situación habitacional (OR interno)
    if situaciones and "situacion_habitacional" in df.columns:
        mask &= df["situacion_habitacional"].isin(situaciones)

    # Filtro por género (OR interno)
    if generos and "genero" in df.columns:
        mask &= df["genero"].isin(generos)

    # Filtro por rango de edad (OR interno, calculado desde fecha_nacimiento)
    if rangos_edad and "fecha_nacimiento" in df.columns:
        fechas_nac = pd.to_datetime(df["fecha_nacimiento"], errors="coerce")
        hoy = pd.Timestamp.now()
        edades = (hoy - fechas_nac).dt.days / 365.25

        edad_mask = pd.Series([False] * len(df), index=df.index)
        for rango_label in rangos_edad:
            limites = _RANGOS_EDAD_LIMITES.get(rango_label)
            if limites is None:
                continue
            edad_min, edad_max = limites
            if edad_max is None:
                edad_mask |= (edades >= edad_min) & edades.notna()
            else:
                edad_mask |= (edades >= edad_min) & (edades < edad_max) & edades.notna()
        mask &= edad_mask

    # Filtro por texto libre
    if busqueda.strip():
        term = busqueda.strip().lower()
        txt_mask = pd.Series([False] * len(df), index=df.index)
        for col in ["email", "nombre", "apellido"]:
            if col in df.columns:
                txt_mask |= (
                    df[col].fillna("").astype(str)
                    .str.lower().str.contains(term, regex=False)
                )
        mask &= txt_mask

    return df[mask].copy()


# ── CSS ───────────────────────────────────────────────────────────────────────

def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {PALETTE['bg']}; }}
        .kpi-card {{
            background: #FFFFFF;
            border-radius: 10px;
            padding: 18px 14px 14px;
            border: 1px solid {PALETTE['border']};
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            text-align: center;
            min-height: 108px;
        }}
        .kpi-value {{
            font-size: 2.1rem;
            font-weight: 700;
            color: {PALETTE['primary']};
            line-height: 1.1;
        }}
        .kpi-label {{
            font-size: 0.78rem;
            color: {PALETTE['neutral']};
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .kpi-delta {{
            font-size: 0.76rem;
            color: {PALETTE['secondary']};
            margin-top: 3px;
            font-weight: 500;
        }}
        .section-title {{
            font-size: 1rem;
            font-weight: 600;
            color: #1F2937;
            margin: 22px 0 10px;
            padding-bottom: 6px;
            border-bottom: 2px solid {PALETTE['border']};
        }}
        [data-testid="stSidebar"] {{
            background: #FFFFFF !important;
            border-right: 1px solid {PALETTE['border']};
        }}
        #MainMenu  {{ visibility: hidden; }}
        footer     {{ visibility: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Componentes KPI ───────────────────────────────────────────────────────────

def _kpi_card_html(value: str, label: str, delta: str = "") -> str:
    delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-label">{label}</div>'
        f'{delta_html}'
        f'</div>'
    )


def render_kpi_row(df: pd.DataFrame) -> None:
    """
    Renderiza la fila de 5 KPI cards calculados desde el DataFrame filtrado.

    Todos los valores reflejan el subconjunto activo según los filtros
    globales del sidebar — no el total global de la base de datos.

    Args:
        df: DataFrame ya filtrado por apply_filters().
    """
    n = len(df)

    def _flag_count(col: str) -> int:
        return int(df[col].astype(bool).sum()) if col in df.columns else 0

    n_inscritos = _flag_count("inscrito_taller")
    n_asistidos = _flag_count("asistio_taller")
    n_minga     = _flag_count("uso_minga")
    n_comunas   = int(df["comuna"].dropna().nunique()) if "comuna" in df.columns else 0
    n_regiones  = int(df["region"].dropna().nunique()) if "region" in df.columns else 0

    kpis = [
        (_fmt(n),           "Usuarios",            f"{n_regiones} regiones"),
        (_fmt(n_inscritos), "Inscritos taller",     _pct(n_inscritos, n)),
        (_fmt(n_asistidos), "Personas capacitadas", _pct(n_asistidos, n)),
        (_fmt(n_minga),     "Usaron Minga",         _pct(n_minga, n)),
        (_fmt(n_comunas),   "Comunas alcanzadas",   f"{n_regiones} regiones"),
    ]

    for col, (val, label, delta) in zip(st.columns(5), kpis):
        with col:
            st.markdown(_kpi_card_html(val, label, delta), unsafe_allow_html=True)


# ── Gráficos — todos reciben df: pd.DataFrame ─────────────────────────────────

def chart_usuarios_por_region(df: pd.DataFrame) -> go.Figure:
    """
    Horizontal bar chart — usuarios por región.

    Excluye regiones sin información para mostrar únicamente
    regiones válidas del DataFrame filtrado.
    """
    if df.empty or "region" not in df.columns:
        return go.Figure()

    regiones_validas = (
        df["region"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    regiones_validas = regiones_validas[
        ~regiones_validas.str.lower().isin([
            "",
            "sin datos",
            "nan",
            "none",
        ])
    ]

    counts = regiones_validas.value_counts()

    if counts.empty:
        return go.Figure()

    data = sorted(counts.items(), key=lambda x: x[1])

    regiones = [
        r.replace("region de ", "")
         .replace("región de ", "")
         .title()
        for r, _ in data
    ]

    valores = [v for _, v in data]

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=regiones,
            orientation="h",
            marker_color=PALETTE["primary"],
            text=valores,
            textposition="outside",
            cliponaxis=False,
        )
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=8, r=70, t=30, b=8),
        height=320,
        showlegend=False,
        xaxis_title=None,
        yaxis_title=None,
    )

    return fig


def chart_distribucion_fuentes(df: pd.DataFrame) -> go.Figure:
    """
    Bar chart — distribución de usuarios por fuente de origen.

    Muestra cuántos usuarios aparecen en cada fuente.
    Un usuario puede pertenecer a múltiples fuentes.
    """
    if df.empty:
        return go.Figure()

    labels = [
        "Registro Web",
        "Talleres",
        "Asistencia",
        "Minga",
    ]

    cols = [
        "tiene_registro_web",
        "inscrito_taller",
        "asistio_taller",
        "uso_minga",
    ]

    values = [
        int(df[c].astype(bool).sum()) if c in df.columns else 0
        for c in cols
    ]

    total = len(df)

    etiquetas = [
        f"{_fmt(v)}<br>({_pct(v, total)})"
        for v in values
    ]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=SOURCE_COLORS,
            text=etiquetas,
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
        )
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=8, r=20, t=35, b=8),
        height=320,
        showlegend=False,
        yaxis_title="Usuarios",
        xaxis_title=None,
    )

    return fig


def chart_inscritos_vs_asistidos(df: pd.DataFrame) -> go.Figure:
    """
    Bar chart — estado de participación en talleres. Comparativa inscripción vs asistencia a talleres.

    Clasifica cada usuario en uno de cuatro grupos desde el DataFrame filtrado:
    - Inscrito sin asistencia
    - Asistió sin inscripción
    - Inscrito y asistió
    - Sin participación
    """
    if df.empty:
        return go.Figure()

    inscrito = (
        df["inscrito_taller"].astype(bool)
        if "inscrito_taller" in df.columns
        else pd.Series([False] * len(df), index=df.index)
    )

    asistido = (
        df["asistio_taller"].astype(bool)
        if "asistio_taller" in df.columns
        else pd.Series([False] * len(df), index=df.index)
    )

    valores = [
        int((inscrito & ~asistido).sum()),
        int((~inscrito & asistido).sum()),
        int((inscrito & asistido).sum()),
        int((~inscrito & ~asistido).sum()),
    ]

    total = len(df)

    categorias = [
        "Inscrito<br>sin asistencia",
        "Asistió<br>sin inscripción",
        "Inscrito<br>y asistió",
        "Sin<br>participación",
    ]

    colores = [
        PALETTE["talleres"],
        PALETTE["zoom"],
        PALETTE["minga"],
        PALETTE["neutral"],
    ]

    etiquetas = [
        f"{_fmt(v)}<br>({_pct(v, total)})"
        for v in valores
    ]

    fig = go.Figure(
        go.Bar(
            x=categorias,
            y=valores,
            marker_color=colores,
            text=etiquetas,
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
        )
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=8, r=20, t=35, b=8),
        height=320,
        showlegend=False,
        yaxis_title="Usuarios",
        xaxis_title=None,
    )

    return fig


def chart_situacion_habitacional(df: pd.DataFrame) -> go.Figure:
    """
    Horizontal bar chart — distribución por situación habitacional.

    Usa la misma paleta de colores que chart_registros_por_situacion
    para mantener coherencia visual.

    Muestra cantidad y porcentaje sobre cada barra.
    """
    if df.empty or "situacion_habitacional" not in df.columns:
        return go.Figure()

    sh_norm = (
        df["situacion_habitacional"]
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    counts = sh_norm[
        sh_norm.notna()
        & ~sh_norm.isin(["sin_datos", "nan", "none"])
    ].value_counts()

    if counts.empty:
        return go.Figure()

    data = sorted(counts.items(), key=lambda x: x[1])

    labels = [k.replace("_", " ").title() for k, _ in data]
    valores = [v for _, v in data]
    colores = [_SH_COLOR_MAP.get(k, PALETTE["neutral"]) for k, _ in data]

    total = sum(valores)

    etiquetas = [
        f"{_fmt(v)}<br>({_pct(v, total)})"
        for v in valores
    ]

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=labels,
            orientation="h",
            marker_color=colores,
            text=etiquetas,
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
        )
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=8, r=90, t=30, b=8),
        height=320,
        showlegend=False,
        xaxis_title="Usuarios",
        yaxis_title=None,
    )

    return fig


def _build_periodos_disponibles(df: pd.DataFrame) -> list[str]:
    """
    Retorna la lista de períodos YYYY-MM disponibles en el DataFrame,
    ordenados cronológicamente, para los selectboxes Desde/Hasta.

    Usa fecha_creacion (fecha de alta en el registro RVC) como columna
    canónica. Fallback a fecha_primer_registro si no existe.
    fecha_primer_registro puede incluir fechas de fuentes secundarias
    (asistencia, minga) que distorsionan el eje temporal para usuarios
    sin registro web.
    """
    col = "fecha_creacion" if "fecha_creacion" in df.columns else "fecha_primer_registro"
    if col not in df.columns or df.empty:
        return []
    fechas = pd.to_datetime(df[col], errors="coerce").dropna()
    return sorted(fechas.dt.to_period("M").astype(str).unique().tolist())


def chart_registros_por_situacion(
    df: pd.DataFrame,
    periodo_desde: str,
    periodo_hasta: str,
) -> go.Figure:
    """
    Gráfico combinado: línea (inscritos RVC totales por mes) +
    barras apiladas (distribución por situación habitacional).

    Replica el gráfico "Inscritos RVC según situación habitacional"
    del equipo, con los datos del pipeline ETL.

    Recibe df_filtered_sin_sh (DataFrame filtrado sin el filtro de SH)
    porque situacion_habitacional es la variable de las categorías del
    propio gráfico — filtrar por ella colapsaría las barras.

    La línea incluye TODOS los usuarios con fecha_creacion en el período,
    hayan completado o no el campo situacion_habitacional.
    Las barras apiladas solo incluyen quienes completaron ese dato.
    La diferencia entre la línea y la altura total de las barras representa
    usuarios que nunca completaron el Paso 2 — diferencia esperada y correcta.

    Args:
        df:            DataFrame filtrado (sin filtro SH).
        periodo_desde: Período de inicio 'YYYY-MM'.
        periodo_hasta: Período de fin 'YYYY-MM'.
    """
    col_fecha = "fecha_creacion" if "fecha_creacion" in df.columns else "fecha_primer_registro"

    if df.empty or col_fecha not in df.columns:
        return go.Figure()

    fechas = pd.to_datetime(df[col_fecha], errors="coerce")
    df_work = df.loc[fechas.notna()].copy()
    df_work["_periodo"] = fechas.loc[fechas.notna()].dt.to_period("M").astype(str)
    df_work = df_work[
        (df_work["_periodo"] >= periodo_desde) &
        (df_work["_periodo"] <= periodo_hasta)
    ]

    if df_work.empty:
        return go.Figure()

    totales = (
        df_work.groupby("_periodo")
        .size()
        .reset_index(name="total")
        .sort_values("_periodo")
    )
    periodos_ordenados = totales["_periodo"].tolist()

    _MESES_ES = {
        "01": "enero",   "02": "febrero", "03": "marzo",
        "04": "abril",   "05": "mayo",    "06": "junio",
        "07": "julio",   "08": "agosto",  "09": "septiembre",
        "10": "octubre", "11": "noviembre","12": "diciembre",
    }

    def _fmt_periodo(p: str) -> str:
        try:
            anio, mes = p.split("-")
            return f"{_MESES_ES.get(mes, mes)} {anio[2:]}"
        except Exception:
            return p

    etiquetas = [_fmt_periodo(p) for p in periodos_ordenados]
    fig = go.Figure()

    if "situacion_habitacional" in df_work.columns:
        df_sh = df_work[df_work["situacion_habitacional"].notna()].copy()
        df_sh["_sh_norm"] = (
            df_sh["situacion_habitacional"]
            .astype(str).str.strip().str.lower().str.replace(" ", "_")
        )
        cats_presentes = set(df_sh["_sh_norm"].unique())

        for cat_key, color in _SH_CATEGORIAS:
            if cat_key not in cats_presentes:
                continue
            conteos_cat = (
                df_sh[df_sh["_sh_norm"] == cat_key]
                .groupby("_periodo").size()
                .reindex(periodos_ordenados, fill_value=0)
            )
            fig.add_trace(go.Bar(
                x=etiquetas,
                y=conteos_cat.values,
                name=cat_key.replace("_", " ").title(),
                marker_color=color,
                yaxis="y",
            ))

    fig.add_trace(go.Scatter(
        x=etiquetas,
        y=totales["total"].tolist(),
        mode="lines+markers",
        name="Inscritos mensual",
        line=dict(color="#1E3A8A", width=2.5),
        marker=dict(size=5),
        yaxis="y",
    ))

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        barmode="stack",
        margin=dict(l=8, r=8, t=8, b=8),
        height=360,
        legend=dict(
            orientation="v",
            x=1.02, y=1,
            xanchor="left",
            font=dict(size=11),
        ),
        yaxis=dict(title=None),
        xaxis=dict(title=None, tickangle=-45),
    )
    return fig


def chart_top_comunas(df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """
    Horizontal bar chart — Top N comunas.

    Considera únicamente usuarios que completaron el Paso 2
    (situación habitacional).
    """
    if (
        df.empty
        or "comuna" not in df.columns
        or "situacion_habitacional" not in df.columns
    ):
        return go.Figure()

    # Sólo usuarios que completaron Paso 2
    df = df[df["situacion_habitacional"].notna()].copy()

    if df.empty:
        return go.Figure()

    total = len(df)

    if "region" in df.columns:
        top = (
            df.groupby("comuna")
            .agg(
                count=("comuna", "count"),
                region=("region", lambda x: x.mode().iloc[0] if not x.mode().empty else None),
            )
            .reset_index()
            .sort_values("count", ascending=False)
            .head(top_n)
            .sort_values("count", ascending=True)
        )
    else:
        top = (
            df["comuna"]
            .value_counts()
            .head(top_n)
            .reset_index()
        )
        top.columns = ["comuna", "count"]
        top = top.sort_values("count", ascending=True)

    if top.empty:
        return go.Figure()

    labels = top["comuna"].tolist()
    valores = top["count"].tolist()

    textos = [
        _pct(v, total)
        for v in valores
    ]

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=labels,
            orientation="h",
            marker_color=PALETTE["secondary"],
            text=textos,
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
        )
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=8, r=90, t=30, b=8),
        height=max(280, len(top) * 30),
        showlegend=False,
        xaxis_title="Usuarios",
        yaxis_title=None,
    )

    return fig


def chart_genero(df: pd.DataFrame) -> go.Figure:
    """
    Donut chart — distribución por género.

    Calcula los conteos desde el DataFrame filtrado.
    """
    if df.empty or "genero" not in df.columns:
        return go.Figure()

    etiq = {
        "masculino":       "Masculino",
        "femenino":        "Femenino",
        "otro":            "Otro",
        "no_especificado": "No especif.",
        "sin datos":       "Sin datos",
    }

    colores = [
        "#3B82F6",
        "#EC4899",
        "#8B5CF6",
        "#9CA3AF",
        "#D1D5DB",
    ]

    counts = df["genero"].fillna("sin datos").value_counts()

    labels = [etiq.get(k, k) for k in counts.index]
    values = counts.values.tolist()

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.50,
            marker_colors=colores[:len(labels)],
            texttemplate="%{label}<br>%{value:,} (%{percent})",
            textinfo="none",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Usuarios: %{value:,}<br>"
                "Porcentaje: %{percent}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        margin=dict(l=8, r=8, t=30, b=8),
        height=300,
        showlegend=False,
    )

    return fig


# ── Tabla interactiva ─────────────────────────────────────────────────────────

def render_data_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Sin registros con los filtros aplicados.")
        return

    cols_display = {
        "email":                  "Email",
        "nombre":                 "Nombre",
        "apellido":               "Apellido",
        "region":                 "Region",
        "comuna":                 "Comuna",
        "genero":                 "Genero",
        "situacion_habitacional": "Situacion hab.",
        "tiene_registro_web":     "Registro",
        "inscrito_taller":        "Inscrito",
        "asistio_taller":         "Asistio",
        "uso_minga":              "Minga",
        "match_confidence":       "Confianza",
        "fuentes":                "Fuentes",
    }
    cols_ok  = {k: v for k, v in cols_display.items() if k in df.columns}
    df_vista = df[list(cols_ok.keys())].rename(columns=cols_ok)

    bool_cols = {
        "Registro": st.column_config.CheckboxColumn("Registro Web"),
        "Inscrito": st.column_config.CheckboxColumn("Inscrito taller"),
        "Asistio":  st.column_config.CheckboxColumn("Asistio taller"),
        "Minga":    st.column_config.CheckboxColumn("Uso Minga"),
    }
    col_config = {k: v for k, v in bool_cols.items() if k in df_vista.columns}

    st.dataframe(
        df_vista,
        use_container_width=True,
        height=420,
        column_config=col_config,
    )
    st.caption(f"Mostrando {len(df_vista):,} registros — clic en encabezado para ordenar")

    csv_bytes = df_vista.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label=f"Descargar {len(df_vista):,} registros (.csv)",
        data=csv_bytes,
        file_name="usuarios_filtrados.csv",
        mime="text/csv",
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar(
    df: pd.DataFrame,
) -> tuple[list, list, list, list, list, str]:
    """
    Renderiza el sidebar con logo y los seis filtros globales.

    Filtros:
        Región                — desde valores únicos del DataFrame
        Fuente de datos       — opciones fijas (registro/talleres/asistencia/minga)
        Situación habitacional — desde valores únicos del DataFrame
        Género                — desde valores únicos del DataFrame con etiquetas
        Rango de edad         — 5 rangos fijos definidos por el proyecto
        Búsqueda              — texto libre sobre email/nombre/apellido

    Returns:
        Tupla (regiones, fuentes, situaciones, generos, rangos_edad, busqueda).
    """
    with st.sidebar:
        logo_path = Path(__file__).parent / "assets" / "logo.png"
        st.image(str(logo_path), use_container_width=True)
        st.markdown(
            f'<hr style="margin:8px 0 10px;border-color:{PALETTE["border"]};">',
            unsafe_allow_html=True,
        )

        st.markdown("**Filtros globales**")

        # ── Región ────────────────────────────────────────────────────────
        regiones_disponibles: list[str] = []
        if "region" in df.columns:
            regiones_disponibles = sorted(df["region"].dropna().unique().tolist())

        regiones = st.multiselect(
            "Region",
            options=regiones_disponibles,
            placeholder="Todas las regiones",
            key="region_filter",
        )

        # ── Fuente ────────────────────────────────────────────────────────
        fuentes = st.multiselect(
            "Fuente de datos",
            options=["registro", "talleres", "asistencia", "minga"],
            format_func=lambda x: {
                "registro":   "Registro Web",
                "talleres":   "Talleres",
                "asistencia": "Asistencia Talleres",
                "minga":      "Chatbot Minga",
            }.get(x, x),
            placeholder="Todas las fuentes",
            key="fuente_filter",
        )

        # ── Situación habitacional ─────────────────────────────────────────
        sh_disponibles: list[str] = []
        if "situacion_habitacional" in df.columns:
            sh_disponibles = sorted(df["situacion_habitacional"].dropna().unique().tolist())

        situaciones = st.multiselect(
            "Situacion habitacional",
            options=sh_disponibles,
            format_func=lambda x: x.replace("_", " ").title(),
            placeholder="Todas las situaciones",
            key="sh_filter",
        )

        # ── Género ────────────────────────────────────────────────────────
        _genero_etiq = {
            "masculino":       "Masculino",
            "femenino":        "Femenino",
            "otro":            "Otro",
            "no_especificado": "No especificado",
        }
        generos_disponibles: list[str] = []
        if "genero" in df.columns:
            generos_disponibles = sorted(df["genero"].dropna().unique().tolist())

        generos = st.multiselect(
            "Genero",
            options=generos_disponibles,
            format_func=lambda x: _genero_etiq.get(x, x.title()),
            placeholder="Todos los géneros",
            key="genero_filter",
        )

        # ── Rango de edad ─────────────────────────────────────────────────
        # Calculado desde fecha_nacimiento. Usuarios sin esa columna
        # quedan excluidos cuando el filtro está activo.
        tiene_fecha_nac = "fecha_nacimiento" in df.columns and df["fecha_nacimiento"].notna().any()

        rangos_edad = st.multiselect(
            "Rango de edad",
            options=_RANGOS_EDAD if tiene_fecha_nac else [],
            placeholder="Todos los rangos" if tiene_fecha_nac else "Sin datos de edad",
            disabled=not tiene_fecha_nac,
            key="edad_filter",
        )

        # ── Botón limpiar filtros ────────────────────────────────────────
        def _clear_filters():
            st.session_state["region_filter"] = []
            st.session_state["fuente_filter"] = []
            st.session_state["sh_filter"] = []
            st.session_state["genero_filter"] = []
            st.session_state["edad_filter"] = []

        if st.button("🧹 Limpiar filtros", use_container_width=True,
                      on_click=_clear_filters):
            st.rerun()

        # ── Búsqueda ──────────────────────────────────────────────────────
        # busqueda = st.text_input("Buscar", placeholder="email o nombre...")
        busqueda = ""
        
        st.markdown(
            f"""
            <hr style="margin:14px 0 8px;border-color:{PALETTE['border']};">
            <div style="font-size:0.7rem;color:{PALETTE['neutral']};
                        text-align:center;line-height:1.7;">
                Unified Data Insights Platform<br>
                ETL Pipeline v1.1.0
            </div>
            """,
            unsafe_allow_html=True,
        )

    return regiones, fuentes, situaciones, generos, rangos_edad, busqueda


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """
    Función principal del dashboard.

    Arquitectura de datos (v1.1.0):
        1. df = DataFrame completo desde el DataProvider.
        2. Sidebar → 6 filtros globales.
        3. df_filtered = apply_filters(df, todos los filtros).
           Alimenta: KPIs, todos los gráficos, tabla.
        4. df_filtered_sin_sh = apply_filters(df, sin filtro SH).
           Alimenta exclusivamente: chart_registros_por_situacion,
           porque SH es la variable de las categorías del gráfico.
        5. analytics → solo para metadatos del header (generated_at,
           total global, source_label). No se usa para computar gráficos.
    """
    st.set_page_config(
        page_title="Unified Data Insights Platform",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_css()

    provider: DataProvider = (
        SQLiteDataProvider() if DB_PATH.exists() else CSVDataProvider()
    )

    analytics = provider.get_analytics()
    df        = provider.get_dataframe()

    # ── Filtros globales ──────────────────────────────────────────────────
    regiones, fuentes, situaciones, generos, rangos_edad, busqueda = render_sidebar(df)

    # DataFrame con todos los filtros activos — alimenta la mayoría de gráficos
    df_filtered = apply_filters(
        df, regiones, fuentes, situaciones, generos, rangos_edad, busqueda
    )

    # DataFrame sin filtro de SH — para chart_registros_por_situacion
    # (SH es la variable de las categorías del gráfico, no un filtro)
    df_filtered_sin_sh = apply_filters(
        df, regiones, fuentes, [], generos, rangos_edad, busqueda
    )

    # ── Header ────────────────────────────────────────────────────────────
    col_h, col_m = st.columns([4, 1])
    with col_h:
        st.markdown(
            f'<h1 style="color:{PALETTE["primary"]};margin-bottom:2px;">'
            f"Unified Data Insights Platform — Panel de Datos</h1>",
            unsafe_allow_html=True,
        )
        fecha = analytics.generated_at[:16].replace("T", " ")
        st.caption(
            f"Fuente: **{provider.source_label}** · "
            f"Calculado: {fecha} · "
            f"{_fmt(analytics.total_usuarios)} usuarios en base de datos"
        )
    with col_m:
        if not df_filtered.empty and "match_confidence" in df_filtered.columns:
            n_high = int((df_filtered["match_confidence"] == "HIGH").sum())
            st.metric(
                "Confianza alta",
                _pct(n_high, len(df_filtered)),
                help="Porcentaje de registros con match por email (HIGH)",
            )

    st.divider()

    # ── Sin datos ─────────────────────────────────────────────────────────
    if df.empty or analytics.total_usuarios == 0:
        st.warning(
            "No hay datos disponibles. "
            "Ejecuta `python main.py` para poblar la base de datos.",
            icon="⚠️",
        )
        st.stop()

    if df_filtered.empty:
        st.info("Ningún usuario coincide con los filtros activos.")
        st.stop()

    # ── KPI Cards — desde df_filtered ────────────────────────────────────
    render_kpi_row(df_filtered)
    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)

    # ── Seccion 1: Territorial y fuentes ──────────────────────────────────
    st.markdown(
        '<div class="section-title">Distribucion territorial y por fuente</div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(chart_usuarios_por_region(df_filtered), use_container_width=True)
    with c2:
        st.plotly_chart(chart_distribucion_fuentes(df_filtered), use_container_width=True)

    # ── Seccion 2: Talleres y situacion habitacional ───────────────────────
    st.markdown(
        '<div class="section-title">Participacion en talleres y situacion habitacional</div>',
        unsafe_allow_html=True,
    )
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(chart_inscritos_vs_asistidos(df_filtered), use_container_width=True)
    with c4:
        st.plotly_chart(chart_situacion_habitacional(df_filtered), use_container_width=True)

    # ── Seccion 3: Registros por situacion habitacional ───────────────────
    # Usa df_filtered_sin_sh (filtros globales excepto SH)
    # Conserva filtros locales de período (Desde/Hasta)
    st.markdown(
        '<div class="section-title">Inscritos RVC segun situacion habitacional</div>',
        unsafe_allow_html=True,
    )

    periodos_disponibles = _build_periodos_disponibles(df_filtered_sin_sh)

    if periodos_disponibles:
        _MESES_LABEL = {
            "01": "ene", "02": "feb", "03": "mar", "04": "abr",
            "05": "may", "06": "jun", "07": "jul", "08": "ago",
            "09": "sep", "10": "oct", "11": "nov", "12": "dic",
        }

        def _label_periodo(p: str) -> str:
            try:
                a, m = p.split("-")
                return f"{_MESES_LABEL.get(m, m)}/{a[2:]}"
            except Exception:
                return p

        etiquetas_filtro = [_label_periodo(p) for p in periodos_disponibles]
        col_desde, col_hasta, _ = st.columns([1, 1, 4])

        with col_desde:
            idx_desde = st.selectbox(
                "Desde",
                options=range(len(periodos_disponibles)),
                format_func=lambda i: etiquetas_filtro[i],
                index=0,
                key="filtro_desde",
            )
        with col_hasta:
            idx_hasta = st.selectbox(
                "Hasta",
                options=range(len(periodos_disponibles)),
                format_func=lambda i: etiquetas_filtro[i],
                index=len(periodos_disponibles) - 1,
                key="filtro_hasta",
            )

        p_desde = periodos_disponibles[idx_desde]
        p_hasta = periodos_disponibles[idx_hasta]

        if p_desde > p_hasta:
            st.warning("El período 'Desde' debe ser anterior o igual a 'Hasta'.")
        else:
            st.plotly_chart(
                chart_registros_por_situacion(df_filtered_sin_sh, p_desde, p_hasta),
                use_container_width=True,
            )
    else:
        st.info("Sin datos de fecha disponibles para el gráfico temporal.")

    # ── Seccion 4: Comunas y genero ────────────────────────────────────────
    st.markdown(
        '<div class="section-title">Top comunas | Distribucion por genero</div>',
        unsafe_allow_html=True,
    )
    c5, c6 = st.columns([3, 2])
    with c5:
        st.plotly_chart(chart_top_comunas(df_filtered), use_container_width=True)
    with c6:
        st.plotly_chart(chart_genero(df_filtered), use_container_width=True)

    # ── Seccion 5: Tabla interactiva ──────────────────────────────────────
    # Oculto para la versión de Déficit Cero.
    #
    # st.markdown(
    #     '<div class="section-title">Explorador de datos</div>',
    #     unsafe_allow_html=True,
    # )
    # render_data_table(df_filtered)


if __name__ == "__main__":
    main()

"""
analytics.py — Capa de métricas y KPIs del pipeline ETL.

Responsabilidad: leer la tabla maestra desde SQLite (o CSV como fallback)
y calcular todos los indicadores que consume el dashboard.

Esta capa NO escribe datos.
Esta capa NO ejecuta transformaciones.
Esta capa SÍ puede leerse directamente desde el dashboard (Fase 7).

Fuentes de datos soportadas (en orden de prioridad):
    1. SQLite   → database/deficit_cero.db (tabla usuarios_master)
    2. CSV      → data/processed/usuarios_master.csv (fallback)

Proyecto: Déficit Cero — Community Data Pipeline
Versión: 1.1.0
"""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import DB_PATH, MASTER_CSV_PATH
from scripts.utils import get_logger


# ── Clase de resultado ────────────────────────────────────────────────────────

@dataclass
class AnalyticsResult:
    """
    Resultado completo del cálculo de métricas sobre usuarios_master.

    Todos los campos son serializables a JSON para facilitar la integración
    con el dashboard y futuros endpoints API.

    Atributos:
        total_usuarios:              Total de filas en usuarios_master.
        usuarios_registro:           Usuarios con tiene_registro_web=True.
        usuarios_inscritos_taller:   Usuarios con inscrito_taller=True.
        usuarios_asistidos_taller:   Usuarios con asistio_taller=True.
        usuarios_minga:              Usuarios con uso_minga=True.
        usuarios_multifuente:        Usuarios presentes en 2+ fuentes.
        comunas_unicas:              Número de comunas distintas.
        regiones_unicas:             Número de regiones distintas.
        tasa_asistencia_promedio:    Promedio de tasa_asistencia (sin nulls).
        por_region:                  Conteo de usuarios por región.
        top_comunas:                 Top N comunas por volumen de usuarios.
        por_genero:                  Distribución de usuarios por género.
        por_situacion_habitacional:  Distribución por situación habitacional.
        distribucion_fuentes:        Conteos por fuente y combinaciones.
        inscritos_vs_asistidos:      Comparativa inscripción vs asistencia.
        distribucion_confidence:     Conteo por match_confidence.
        timeline_registros:          Usuarios por período (mes/año).
        generated_at:                Timestamp ISO de cuándo se calculó.
        data_source:                 'sqlite' | 'csv' | 'empty'.
        total_rows_source:           Filas leídas de la fuente de datos.
    """

    # KPI cards (enteros directos)
    total_usuarios: int
    usuarios_registro: int
    usuarios_inscritos_taller: int
    usuarios_asistidos_taller: int
    usuarios_minga: int
    usuarios_multifuente: int
    comunas_unicas: int
    regiones_unicas: int
    tasa_asistencia_promedio: Optional[float]

    # Distribuciones territoriales
    por_region: dict[str, int]
    top_comunas: list[dict]         # [{comuna, region, count, pct}]

    # Distribuciones demográficas
    por_genero: dict[str, int]
    por_situacion_habitacional: dict[str, int]

    # Distribución por fuentes
    distribucion_fuentes: dict[str, int]

    # Comparativa inscripción vs asistencia a talleres
    inscritos_vs_asistidos: dict[str, int]

    # Match confidence
    distribucion_confidence: dict[str, int]

    # Evolución temporal
    timeline_registros: list[dict]  # [{periodo, count}]

    # Metadatos de la consulta
    generated_at: str
    data_source: str
    total_rows_source: int


# ── Carga de datos ────────────────────────────────────────────────────────────

def get_master_dataframe(
    db_path: Path = DB_PATH,
    csv_path: Path = MASTER_CSV_PATH,
) -> tuple[pd.DataFrame, str]:
    """
    Carga usuarios_master desde SQLite o CSV como fallback.

    Intenta primero la DB SQLite. Si no existe o falla la consulta,
    intenta el CSV consolidado. Si ambos fallan, retorna DataFrame vacío.

    Args:
        db_path:  Ruta a la base de datos SQLite.
        csv_path: Ruta al CSV consolidado.

    Returns:
        Tupla (DataFrame, fuente_usada) donde fuente_usada es
        'sqlite' | 'csv' | 'empty'.
    """
    logger = get_logger("analytics")

    # Intento 1 — SQLite
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            df = pd.read_sql_query("SELECT * FROM usuarios_master;", conn)
            conn.close()
            logger.info(
                f"Datos cargados desde SQLite | "
                f"filas: {len(df)} | ruta: {db_path.name}"
            )
            return df, "sqlite"
        except Exception as exc:
            logger.warning(f"No se pudo leer desde SQLite: {exc} — intentando CSV")

    # Intento 2 — CSV fallback
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
            logger.info(
                f"Datos cargados desde CSV | "
                f"filas: {len(df)} | ruta: {csv_path.name}"
            )
            return df, "csv"
        except Exception as exc:
            logger.error(f"No se pudo leer el CSV: {exc}")

    logger.error(
        "Sin fuente de datos disponible. "
        "Ejecutar el pipeline ETL antes de calcular métricas."
    )
    return pd.DataFrame(), "empty"


# ── Helpers privados ──────────────────────────────────────────────────────────

def _safe_int(val) -> int:
    """Convierte un valor a int de forma segura, retorna 0 si falla."""
    try:
        return int(val) if pd.notna(val) else 0
    except (ValueError, TypeError):
        return 0


def _safe_pct(numerador: int, denominador: int, decimals: int = 1) -> float:
    """Calcula un porcentaje de forma segura. Retorna 0.0 si denominador es 0."""
    if denominador == 0:
        return 0.0
    return round((numerador / denominador) * 100, decimals)


def _value_counts_to_dict(
    series: pd.Series,
    top_n: Optional[int] = None,
    normalize_nulls: bool = True,
) -> dict[str, int]:
    """
    Convierte value_counts() a dict ordenado por frecuencia descendente.

    Args:
        series:          Serie pandas a contar.
        top_n:           Si se especifica, retorna solo los top N valores.
        normalize_nulls: Si True, reemplaza valores NaN/None con 'Sin datos'.

    Returns:
        Diccionario {valor: conteo} ordenado por conteo descendente.
    """
    s = series.copy()
    if normalize_nulls:
        s = s.fillna("Sin datos")
    counts = s.value_counts()
    if top_n:
        counts = counts.head(top_n)
    return {str(k): int(v) for k, v in counts.items()}


# ── Funciones de cómputo ──────────────────────────────────────────────────────

def _compute_totales(df: pd.DataFrame) -> dict:
    """
    Calcula los KPI totales (conteos simples de flags booleanos).

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Diccionario con todos los totales principales.
    """
    total = len(df)

    def _flag_count(col: str) -> int:
        if col not in df.columns:
            return 0
        return int(df[col].astype(bool).sum())

    # Multifuente: suma de flags booleanos >= 2
    flag_cols = [
        c for c in
        ["tiene_registro_web", "inscrito_taller", "asistio_taller", "uso_minga"]
        if c in df.columns
    ]
    if flag_cols:
        fuentes_por_usuario = df[flag_cols].astype(bool).sum(axis=1)
        multifuente = int((fuentes_por_usuario >= 2).sum())
    else:
        multifuente = 0

    # Tasa de asistencia promedio
    if "tasa_asistencia" in df.columns:
        tasas = pd.to_numeric(df["tasa_asistencia"], errors="coerce").dropna()
        tasa_prom = round(float(tasas.mean()), 4) if len(tasas) > 0 else None
    else:
        tasa_prom = None

    # Territoriales
    comunas_unicas = (
        int(df["comuna"].dropna().nunique()) if "comuna" in df.columns else 0
    )
    regiones_unicas = (
        int(df["region"].dropna().nunique()) if "region" in df.columns else 0
    )

    return {
        "total_usuarios":            total,
        "usuarios_registro":         _flag_count("tiene_registro_web"),
        "usuarios_inscritos_taller": _flag_count("inscrito_taller"),
        "usuarios_asistidos_taller": _flag_count("asistio_taller"),
        "usuarios_minga":            _flag_count("uso_minga"),
        "usuarios_multifuente":      multifuente,
        "comunas_unicas":            comunas_unicas,
        "regiones_unicas":           regiones_unicas,
        "tasa_asistencia_promedio":  tasa_prom,
    }


def _compute_por_region(df: pd.DataFrame) -> dict[str, int]:
    """
    Conteo de usuarios por región, ordenado de mayor a menor.

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Diccionario {region: count} ordenado descendente.
    """
    if "region" not in df.columns:
        return {}
    return _value_counts_to_dict(df["region"])


def _compute_top_comunas(
    df: pd.DataFrame,
    top_n: int = 10,
) -> list[dict]:
    """
    Lista de las top N comunas por número de usuarios, con región y porcentaje.

    Args:
        df:    DataFrame de usuarios_master.
        top_n: Número de comunas a retornar.

    Returns:
        Lista de dicts [{comuna, region, count, pct}] ordenada por count desc.
    """
    if "comuna" not in df.columns:
        return []

    total = len(df)
    cols_disponibles = [c for c in ["comuna", "region"] if c in df.columns]

    if "region" in df.columns:
        # Obtener la región más frecuente por comuna (para usuarios sin región)
        top = (
            df.groupby("comuna")
            .agg(
                count=("comuna", "count"),
                region=("region", lambda x: x.mode().iloc[0] if len(x) > 0 else None),
            )
            .reset_index()
            .sort_values("count", ascending=False)
            .head(top_n)
        )
    else:
        top = (
            df["comuna"].value_counts()
            .head(top_n)
            .reset_index()
            .rename(columns={"count": "count", "comuna": "comuna"})
        )
        top["region"] = None

    resultado: list[dict] = []
    for _, row in top.iterrows():
        comuna = str(row["comuna"]) if pd.notna(row.get("comuna")) else "Sin datos"
        if comuna == "Sin datos":
            continue
        resultado.append({
            "comuna":  comuna,
            "region":  str(row["region"]) if pd.notna(row.get("region")) else "Sin datos",
            "count":   int(row["count"]),
            "pct":     _safe_pct(int(row["count"]), total),
        })

    return resultado


def _compute_por_genero(df: pd.DataFrame) -> dict[str, int]:
    """
    Distribución de usuarios por género normalizado.

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Diccionario {genero: count}.
    """
    if "genero" not in df.columns:
        return {}
    return _value_counts_to_dict(df["genero"])


def _compute_por_situacion_habitacional(df: pd.DataFrame) -> dict[str, int]:
    """
    Distribución por situación habitacional.

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Diccionario {situacion: count} ordenado descendente.
    """
    if "situacion_habitacional" not in df.columns:
        return {}
    return _value_counts_to_dict(df["situacion_habitacional"])


def _compute_distribucion_fuentes(df: pd.DataFrame) -> dict[str, int]:
    """
    Distribución de usuarios por fuente de origen y combinaciones.

    Calcula tanto conteos individuales por flag como combinaciones
    (usuarios presentes en exactamente 1, 2, 3 o 4 fuentes).

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Diccionario con conteos por fuente y por número de fuentes.
    """
    flag_cols = {
        "registro": "tiene_registro_web",
        "talleres": "inscrito_taller",
        "zoom":     "asistio_taller",
        "minga":    "uso_minga",
    }

    resultado: dict[str, int] = {}

    # Conteo individual por fuente
    for label, col in flag_cols.items():
        if col in df.columns:
            resultado[label] = int(df[col].astype(bool).sum())

    # Conteo por número de fuentes
    cols_presentes = [col for col in flag_cols.values() if col in df.columns]
    if cols_presentes:
        n_fuentes = df[cols_presentes].astype(bool).sum(axis=1)
        for n in range(0, len(cols_presentes) + 1):
            resultado[f"exactamente_{n}_fuentes"] = int((n_fuentes == n).sum())
        resultado["multifuente_2_o_mas"] = int((n_fuentes >= 2).sum())
        resultado["multifuente_3_o_mas"] = int((n_fuentes >= 3).sum())
        resultado["solo_una_fuente"]     = int((n_fuentes == 1).sum())

    return resultado


def _compute_inscritos_vs_asistidos(df: pd.DataFrame) -> dict[str, int]:
    """
    Comparativa entre inscripción a talleres y asistencia efectiva.

    Segmentos:
        solo_inscritos:  Inscrito pero no asistió (inscrito_taller=1, asistio_taller=0)
        solo_asistidos:  Asistió sin inscripción previa (match secundario Zoom)
        ambos:           Inscrito Y asistió
        ninguno:         Ni inscrito ni asistió a talleres

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Diccionario con los 4 segmentos + totales de cada flag.
    """
    tiene_inscrito = "inscrito_taller" in df.columns
    tiene_asistido = "asistio_taller"  in df.columns

    if not tiene_inscrito and not tiene_asistido:
        return {}

    inscrito = df["inscrito_taller"].astype(bool) if tiene_inscrito else pd.Series([False] * len(df))
    asistido = df["asistio_taller"].astype(bool)  if tiene_asistido else pd.Series([False] * len(df))

    return {
        "total_inscritos":    int(inscrito.sum()),
        "total_asistidos":    int(asistido.sum()),
        "solo_inscritos":     int((inscrito & ~asistido).sum()),
        "solo_asistidos":     int((~inscrito & asistido).sum()),
        "ambos":              int((inscrito & asistido).sum()),
        "ninguno":            int((~inscrito & ~asistido).sum()),
        "tasa_conversion_pct": _safe_pct(
            int((inscrito & asistido).sum()),
            int(inscrito.sum()),
        ),
    }


def _compute_distribucion_confidence(df: pd.DataFrame) -> dict[str, int]:
    """
    Distribución de registros por nivel de confianza del cruce.

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Diccionario {HIGH|LOW|UNMATCHED: count}.
    """
    if "match_confidence" not in df.columns:
        return {}
    return _value_counts_to_dict(df["match_confidence"], normalize_nulls=False)


def _compute_timeline_registros(df: pd.DataFrame) -> list[dict]:
    """
    Evolución temporal de usuarios por mes de fecha_primer_registro.

    Agrupa por período 'YYYY-MM' y cuenta usuarios, ordenado
    cronológicamente ascendente.

    Args:
        df: DataFrame de usuarios_master.

    Returns:
        Lista de dicts [{periodo, count, acumulado}] ordenada por período.
    """
    if "fecha_primer_registro" not in df.columns:
        return []

    fechas = pd.to_datetime(df["fecha_primer_registro"], errors="coerce").dropna()
    if fechas.empty:
        return []

    periodos = fechas.dt.to_period("M").astype(str)
    conteo = periodos.value_counts().sort_index()

    acumulado = 0
    resultado: list[dict] = []
    for periodo, count in conteo.items():
        acumulado += int(count)
        resultado.append({
            "periodo":    str(periodo),
            "count":      int(count),
            "acumulado":  acumulado,
        })

    return resultado


def _empty_result(data_source: str = "empty") -> AnalyticsResult:
    """
    Retorna un AnalyticsResult vacío cuando no hay datos disponibles.

    Args:
        data_source: Fuente que produjo el resultado vacío.

    Returns:
        AnalyticsResult con todos los campos en 0 / [] / {}.
    """
    import datetime
    return AnalyticsResult(
        total_usuarios=0,
        usuarios_registro=0,
        usuarios_inscritos_taller=0,
        usuarios_asistidos_taller=0,
        usuarios_minga=0,
        usuarios_multifuente=0,
        comunas_unicas=0,
        regiones_unicas=0,
        tasa_asistencia_promedio=None,
        por_region={},
        top_comunas=[],
        por_genero={},
        por_situacion_habitacional={},
        distribucion_fuentes={},
        inscritos_vs_asistidos={},
        distribucion_confidence={},
        timeline_registros=[],
        generated_at=datetime.datetime.now().isoformat(),
        data_source=data_source,
        total_rows_source=0,
    )


# ── Función pública principal ─────────────────────────────────────────────────

def compute_analytics(
    db_path: Path = DB_PATH,
    csv_path: Path = MASTER_CSV_PATH,
    top_comunas_n: int = 10,
) -> AnalyticsResult:
    """
    Función principal de la capa de analytics.

    Carga usuarios_master desde SQLite (o CSV como fallback) y calcula
    todos los indicadores que consume el dashboard.

    Args:
        db_path:       Ruta a la base de datos SQLite.
        csv_path:      Ruta al CSV consolidado (fallback).
        top_comunas_n: Número de comunas a incluir en el ranking.

    Returns:
        AnalyticsResult con todos los indicadores calculados.
        Nunca lanza excepciones al caller — errores retornan _empty_result().
    """
    import datetime
    logger = get_logger("analytics")

    separador = "═" * 55
    logger.info(f"\n{separador}\n  Analytics | calculando KPIs\n{separador}")

    try:
        df, data_source = get_master_dataframe(db_path, csv_path)

        if df.empty:
            logger.warning("Sin datos disponibles — retornando AnalyticsResult vacío")
            return _empty_result(data_source)

        total_rows = len(df)
        logger.info(f"Fuente: {data_source} | filas: {total_rows}")

        # Calcular todos los indicadores
        totales        = _compute_totales(df)
        por_region     = _compute_por_region(df)
        top_comunas    = _compute_top_comunas(df, top_n=top_comunas_n)
        por_genero     = _compute_por_genero(df)
        por_sh         = _compute_por_situacion_habitacional(df)
        dist_fuentes   = _compute_distribucion_fuentes(df)
        ins_vs_asis    = _compute_inscritos_vs_asistidos(df)
        dist_conf      = _compute_distribucion_confidence(df)
        timeline       = _compute_timeline_registros(df)

        result = AnalyticsResult(
            # KPIs principales
            total_usuarios=totales["total_usuarios"],
            usuarios_registro=totales["usuarios_registro"],
            usuarios_inscritos_taller=totales["usuarios_inscritos_taller"],
            usuarios_asistidos_taller=totales["usuarios_asistidos_taller"],
            usuarios_minga=totales["usuarios_minga"],
            usuarios_multifuente=totales["usuarios_multifuente"],
            comunas_unicas=totales["comunas_unicas"],
            regiones_unicas=totales["regiones_unicas"],
            tasa_asistencia_promedio=totales["tasa_asistencia_promedio"],
            # Distribuciones
            por_region=por_region,
            top_comunas=top_comunas,
            por_genero=por_genero,
            por_situacion_habitacional=por_sh,
            distribucion_fuentes=dist_fuentes,
            inscritos_vs_asistidos=ins_vs_asis,
            distribucion_confidence=dist_conf,
            timeline_registros=timeline,
            # Metadatos
            generated_at=datetime.datetime.now().isoformat(),
            data_source=data_source,
            total_rows_source=total_rows,
        )

        logger.info(
            f"Analytics completado | "
            f"usuarios={result.total_usuarios} | "
            f"regiones={result.regiones_unicas} | "
            f"comunas={result.comunas_unicas} | "
            f"fuente={data_source}"
        )
        return result

    except Exception as exc:
        logger.critical(
            f"Error inesperado en compute_analytics(): {exc}",
            exc_info=True,
        )
        return _empty_result("empty")

"""
consolidate.py — Capa de consolidación del pipeline ETL.

Responsabilidad: recibe los DataFrames transformados de las 4 fuentes
y genera la tabla maestra usuarios_master con un registro por email.

Pipeline interno:
    1.  Extracción segura de cada DataFrame del diccionario de entrada
    2.  Agregación de talleres por email (conteos, títulos)
    3.  Agregación de minga por email (conteos, perfil financiero)
    4.  Agregación de asistencia — email-based + sin-email (matching secundario)
    5.  Preparación del resumen de registro
    6.  Merge outer de las 4 fuentes por email
    7.  Cálculo de flags de participación
    8.  Cálculo de tasa de asistencia
    9.  Cálculo de fecha_primer_registro
    10. Generación de columna fuentes (JSON list)
    11. Generación de nombre_key en tabla maestra
    12. Matching secundario para registros de asistencia sin email
    13. Limpieza y esquema final

Esta capa NO lee archivos CSV.
Esta capa NO escribe en base de datos (eso es Fase 5).

Proyecto: Déficit Cero — Community Data Pipeline
Versión: 1.1.0
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from unidecode import unidecode

from config.mappings import PRIORITY_FIELDS
from scripts.utils import get_logger


# ── Constantes ─────────────────────────────────────────────────────────────────

MASTER_SCHEMA: list[str] = [
    # Identificación
    "email",
    "match_confidence",
    "nombre_key",
    "member_id_rcv",
    # Datos personales
    "nombre",
    "apellido",
    "genero",
    "fecha_nacimiento",
    "whatsapp",
    "nacionalidad",
    # Territorialidad
    "region",
    "comuna",
    # Situación habitacional (registro)
    "situacion_habitacional",
    "pertenece_comite",
    "cuantas_personas_viven",
    "estado_registro",
    # Perfil financiero (minga)
    "subsidio_recomendado",
    "rsh",
    "tiene_propiedad",
    "tiene_subsidio",
    "ingresos",
    "ahorro",
    # Flags de participación
    "tiene_registro_web",
    "inscrito_taller",
    "asistio_taller",
    "uso_minga",
    # Conteos
    "num_talleres_inscritos",
    "num_talleres_asistidos",
    "num_conversaciones_minga",
    "tasa_asistencia",
    # Metadatos
    "fuentes",
    "fecha_primer_registro",
    "fecha_etl",
]

# Campos personales — el consolidado de asistencia no aporta nombre/apellido
# al master (MEMBER_SCREEN_NAME es opcional y no estructurado). Se elimina
# el coalesce que existía para zoom_nombre / zoom_apellido.
_PERSONAL_COALESCE_COLS: list[str] = []


# ── Clase de resultado ─────────────────────────────────────────────────────────

@dataclass
class ConsolidateResult:
    """
    Resultado completo de la capa de consolidación.

    Atributos:
        df:                         DataFrame maestro usuarios_master.
        total_usuarios:             Total de filas únicas en el master.
        usuarios_registro:          Usuarios con tiene_registro_web = True.
        usuarios_inscritos_taller:  Usuarios con inscrito_taller = True.
        usuarios_asistieron_taller: Usuarios con asistio_taller = True.
        usuarios_minga:             Usuarios con uso_minga = True.
        usuarios_multifuente:       Usuarios presentes en 2 o más fuentes.
        low_confidence_matches:     Registros unidos por nombre_key (LOW).
        unmatched_records:          Registros sin email y sin match.
        warnings:                   Advertencias del proceso.
    """

    df: pd.DataFrame
    total_usuarios: int
    usuarios_registro: int
    usuarios_inscritos_taller: int
    usuarios_asistieron_taller: int
    usuarios_minga: int
    usuarios_multifuente: int
    low_confidence_matches: int
    unmatched_records: int
    warnings: list[str]


# ── Helpers privados ───────────────────────────────────────────────────────────

def _safe_df(dataframes: dict[str, pd.DataFrame], key: str) -> pd.DataFrame:
    """
    Obtiene un DataFrame del diccionario de entrada de forma segura.
    Retorna DataFrame vacío si la clave no existe o el valor es None.
    """
    df = dataframes.get(key)
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    return df.copy()


def _build_nombre_key(nombre: Optional[str], apellido: Optional[str]) -> Optional[str]:
    """
    Genera clave normalizada para matching secundario por nombre+apellido.

    Algoritmo:
        1. Concatenar nombre + " " + apellido (si apellido existe)
        2. unidecode() — elimina tildes y caracteres especiales
        3. lowercase + strip
        4. Eliminar caracteres no alfanuméricos ni espacios
        5. Colapsar espacios múltiples
        6. Reemplazar espacios por "_"

    Ejemplos:
        ("María", "González")   → "maria_gonzalez"
        ("José Luis", "Soto")   → "jose_luis_soto"
        ("Carlos", None)        → "carlos"
        (None, None)            → None

    Args:
        nombre:   Primer nombre o nombres.
        apellido: Apellido(s) o None.

    Returns:
        Clave normalizada o None si nombre es None.
    """
    if not nombre or pd.isna(nombre):
        return None

    partes = str(nombre).strip()
    if apellido and not pd.isna(apellido):
        partes = f"{partes} {str(apellido).strip()}"

    normalizado = unidecode(partes).lower().strip()
    normalizado = re.sub(r"[^a-z0-9\s]", "", normalizado)
    normalizado = "_".join(normalizado.split())

    return normalizado if normalizado else None


def _first_valid(series_list: list[pd.Series]) -> pd.Series:
    """
    Aplica coalesce entre varias Series: retorna el primer valor no-nulo
    de izquierda a derecha para cada índice.

    Args:
        series_list: Lista de Series con el mismo índice, en orden de prioridad.

    Returns:
        Serie con el primer valor no-nulo por posición.
    """
    result = series_list[0].copy()
    for s in series_list[1:]:
        result = result.combine_first(s)
    return result


# ── Funciones de agregación ────────────────────────────────────────────────────

def _aggregate_talleres(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Agrega registros de talleres por email.

    Un usuario puede tener múltiples inscripciones (una por taller).
    Produce un registro por email con conteos y lista de talleres.

    Columnas de salida:
        email, num_talleres_inscritos, talleres_titulos, fecha_inscripcion_min

    Args:
        df:     DataFrame de talleres transformado.
        logger: Logger del módulo.

    Returns:
        DataFrame agregado con un registro por email.
    """
    if df.empty or "email" not in df.columns:
        logger.warning("Talleres: DataFrame vacío o sin columna email — omitiendo agregación")
        return pd.DataFrame(
            columns=["email", "num_talleres_inscritos",
                     "talleres_titulos", "fecha_inscripcion_min"]
        )

    df_valid = df[df["email"].notna()].copy()
    if df_valid.empty:
        return pd.DataFrame(
            columns=["email", "num_talleres_inscritos",
                     "talleres_titulos", "fecha_inscripcion_min"]
        )

    def _collect_titulos(series: pd.Series) -> Optional[str]:
        titulos = list(series.dropna().unique())
        return json.dumps(titulos, ensure_ascii=False) if titulos else None

    agg_kwargs: dict = {
        "num_talleres_inscritos": pd.NamedAgg(
            column="taller_titulo" if "taller_titulo" in df_valid.columns else "email",
            aggfunc="nunique",
        ),
    }

    if "taller_titulo" in df_valid.columns:
        agg_kwargs["talleres_titulos"] = pd.NamedAgg(
            column="taller_titulo",
            aggfunc=_collect_titulos,
        )

    if "fecha_inscripcion" in df_valid.columns:
        agg_kwargs["fecha_inscripcion_min"] = pd.NamedAgg(
            column="fecha_inscripcion",
            aggfunc="min",
        )

    agg = df_valid.groupby("email").agg(**agg_kwargs).reset_index()

    if "talleres_titulos" not in agg.columns:
        agg["talleres_titulos"] = None
    if "fecha_inscripcion_min" not in agg.columns:
        agg["fecha_inscripcion_min"] = pd.NaT

    logger.info(
        f"Talleres agregados | emails únicos: {len(agg)} | "
        f"inscripciones totales: {len(df_valid)}"
    )
    return agg


def _aggregate_minga(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Agrega registros de Minga por email.

    Un usuario puede tener múltiples conversaciones.
    Para campos de perfil financiero se toma el valor de la conversación
    más reciente (sort desc por fecha_conversacion, keep first).

    Columnas de salida:
        email, num_conversaciones_minga, subsidio_recomendado, rsh,
        tiene_propiedad, tiene_subsidio, ingresos, ahorro,
        nacionalidad, fecha_minga_min

    Args:
        df:     DataFrame de minga transformado.
        logger: Logger del módulo.

    Returns:
        DataFrame agregado con un registro por email.
    """
    if df.empty or "email" not in df.columns:
        logger.warning("Minga: DataFrame vacío o sin columna email — omitiendo agregación")
        return pd.DataFrame(
            columns=["email", "num_conversaciones_minga", "fecha_minga_min"]
        )

    df_valid = df[df["email"].notna()].copy()
    if df_valid.empty:
        return pd.DataFrame(
            columns=["email", "num_conversaciones_minga", "fecha_minga_min"]
        )

    if "fecha_conversacion" in df_valid.columns:
        df_valid = df_valid.sort_values("fecha_conversacion", ascending=False)

    perfil_cols = [
        "subsidio_recomendado", "rsh", "tiene_propiedad",
        "tiene_subsidio", "ingresos", "ahorro",
        "nacionalidad", "con_quien_postula",
    ]
    perfil_cols_presentes = [c for c in perfil_cols if c in df_valid.columns]

    agg_kwargs: dict = {
        "num_conversaciones_minga": pd.NamedAgg(column="email", aggfunc="count"),
    }

    for col in perfil_cols_presentes:
        agg_kwargs[col] = pd.NamedAgg(column=col, aggfunc="first")

    if "fecha_conversacion" in df_valid.columns:
        agg_kwargs["fecha_minga_min"] = pd.NamedAgg(
            column="fecha_conversacion", aggfunc="min"
        )

    agg = df_valid.groupby("email").agg(**agg_kwargs).reset_index()

    if "fecha_minga_min" not in agg.columns:
        agg["fecha_minga_min"] = pd.NaT

    logger.info(
        f"Minga agregado | emails únicos: {len(agg)} | "
        f"conversaciones totales: {len(df_valid)}"
    )
    return agg


def _aggregate_asistencia(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Agrega registros del consolidado histórico de asistencia a talleres
    por email y separa los que no tienen email (para matching secundario).

    La fuente es consolidado_asistencia.csv, que reemplaza a zoom_asistencia.csv
    y representa el histórico completo de asistencia desde 2023 — incluyendo
    talleres presenciales, virtuales y otras modalidades.

    A diferencia de la fuente Zoom anterior, esta fuente no tiene metadatos
    de sesión (hora entrada/salida, duración). El conteo num_talleres_asistidos
    refleja inscripciones únicas a talleres distintos (por taller_entry_id).

    Retorna dos DataFrames:
        1. asistencia_email_agg: registros con email, agregados por email
        2. asistencia_no_email:  registros sin email (para matching secundario)

    Columnas de asistencia_email_agg:
        email, num_talleres_asistidos, fecha_asistencia_min

    Args:
        df:     DataFrame de asistencia transformado.
        logger: Logger del módulo.

    Returns:
        Tupla (asistencia_email_agg, asistencia_no_email).
    """
    empty_agg = pd.DataFrame(
        columns=["email", "num_talleres_asistidos", "fecha_asistencia_min"]
    )

    if df.empty:
        logger.warning("Asistencia: DataFrame vacío")
        return empty_agg, pd.DataFrame()

    mask_email = df["email"].notna() & (df["email"].astype(str).str.strip() != "")
    df_con_email = df[mask_email].copy()
    df_sin_email = df[~mask_email].copy()

    logger.info(
        f"Asistencia | con_email: {len(df_con_email)} | "
        f"sin_email: {len(df_sin_email)}"
    )

    if df_con_email.empty:
        return empty_agg, df_sin_email

    agg_kwargs: dict = {
        "num_talleres_asistidos": pd.NamedAgg(
            column="taller_entry_id" if "taller_entry_id" in df_con_email.columns
            else "email",
            aggfunc="nunique",
        ),
    }

    if "fecha_taller" in df_con_email.columns:
        agg_kwargs["fecha_asistencia_min"] = pd.NamedAgg(
            column="fecha_taller", aggfunc="min"
        )

    agg = df_con_email.groupby("email").agg(**agg_kwargs).reset_index()

    if "fecha_asistencia_min" not in agg.columns:
        agg["fecha_asistencia_min"] = pd.NaT

    logger.info(f"Asistencia email-based agregado | emails únicos: {len(agg)}")
    return agg, df_sin_email


def _build_registro_summary(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Prepara el resumen de Registro RCV para el merge.

    Selecciona y renombra las columnas relevantes para el master.
    Registro ya está deduplicado por email desde la Fase 3.

    Args:
        df:     DataFrame de registro transformado.
        logger: Logger del módulo.

    Returns:
        DataFrame de registro con columnas renombradas para el merge.
    """
    if df.empty:
        logger.warning("Registro: DataFrame vacío")
        return pd.DataFrame(columns=["email"])

    col_renames: dict[str, str] = {}
    if "member_id" in df.columns:
        col_renames["member_id"] = "member_id_rcv"

    df_summary = df.copy()
    if col_renames:
        df_summary = df_summary.rename(columns=col_renames)

    logger.info(f"Registro summary preparado | registros: {len(df_summary)}")
    return df_summary


# ── Funciones de construcción del master ──────────────────────────────────────

def _merge_all_sources(
    df_reg: pd.DataFrame,
    df_tal_agg: pd.DataFrame,
    df_asi_agg: pd.DataFrame,
    df_min_agg: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Une las 4 fuentes agregadas en un único DataFrame usando outer join por email.

    Orden de merge:
        registro ⟕ talleres_agg ⟕ asistencia_agg ⟕ minga_agg

    Usuarios presentes en cualquier fuente tendrán una fila en el resultado.
    Columnas de fuentes ausentes quedan como NaN.

    Args:
        df_reg:     Registro RCV (ya deduplicado).
        df_tal_agg: Talleres agregados por email.
        df_asi_agg: Asistencia agregada por email (solo con email).
        df_min_agg: Minga agregado por email.
        logger:     Logger del módulo.

    Returns:
        DataFrame unificado con todos los emails de todas las fuentes.
    """
    def _safe_merge(left: pd.DataFrame, right: pd.DataFrame, label: str) -> pd.DataFrame:
        if right.empty or "email" not in right.columns:
            logger.info(f"Merge {label}: fuente vacía, conservando left sin cambios")
            return left
        merged = pd.merge(left, right, on="email", how="outer")
        logger.info(
            f"Merge {label} | filas: {len(left)} + {len(right)} → {len(merged)}"
        )
        return merged

    if df_reg.empty or "email" not in df_reg.columns:
        logger.warning("Registro vacío — iniciando merge desde DataFrame mínimo")
        df_master = pd.DataFrame(columns=["email"])
    else:
        df_master = df_reg.copy()

    df_master = _safe_merge(df_master, df_tal_agg, "talleres")
    df_master = _safe_merge(df_master, df_asi_agg, "asistencia")
    df_master = _safe_merge(df_master, df_min_agg, "minga")

    logger.info(
        f"Merge completo | total emails únicos en master: {len(df_master)}"
    )
    return df_master


def _coalesce_personal_fields(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Aplica coalesce en campos personales compartidos entre fuentes.

    La fuente de asistencia (consolidado_asistencia.csv) no aporta
    nombre/apellido estructurados al master — MEMBER_SCREEN_NAME es
    opcional y no se usa para construir campos personales del usuario.
    Por este motivo, _PERSONAL_COALESCE_COLS está vacío y esta función
    es un no-op que se conserva por compatibilidad arquitectónica.

    Args:
        df:     DataFrame maestro post-merge.
        logger: Logger del módulo.

    Returns:
        DataFrame sin modificaciones (no-op en la configuración actual).
    """
    df = df.copy()

    for field in _PERSONAL_COALESCE_COLS:
        asistencia_col = f"asistencia_{field}"
        if field in df.columns and asistencia_col in df.columns:
            antes_nulos = int(df[field].isna().sum())
            df[field] = df[field].combine_first(df[asistencia_col])
            despues_nulos = int(df[field].isna().sum())
            recuperados = antes_nulos - despues_nulos
            if recuperados > 0:
                logger.info(
                    f"Coalesce '{field}': recuperados {recuperados} valores "
                    f"desde asistencia"
                )
            df.drop(columns=[asistencia_col], inplace=True)

    return df


def _compute_participation_flags(
    df: pd.DataFrame,
    df_registro: pd.DataFrame,
    df_talleres: pd.DataFrame,
    df_asistencia_email: pd.DataFrame,
    df_minga: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Calcula flags booleanos de participación por fuente.

    Flags generados:
        tiene_registro_web: email presente en registro
        inscrito_taller:    email presente en talleres
        asistio_taller:     email presente en consolidado de asistencia
        uso_minga:          email presente en minga

    La presencia se determina por el set de emails de cada fuente,
    no por columnas del master (más robusto ante merges parciales).

    Args:
        df:                   DataFrame maestro.
        df_registro:          DataFrame de registro transformado.
        df_talleres:          DataFrame de talleres transformado.
        df_asistencia_email:  DataFrame de asistencia (solo registros con email).
        df_minga:             DataFrame de minga transformado.
        logger:               Logger del módulo.

    Returns:
        DataFrame con columnas de flags añadidas.
    """
    df = df.copy()

    def _email_set(source_df: pd.DataFrame) -> set:
        if source_df.empty or "email" not in source_df.columns:
            return set()
        return set(source_df["email"].dropna().unique())

    emails_registro   = _email_set(df_registro)
    emails_talleres   = _email_set(df_talleres)
    emails_asistencia = _email_set(df_asistencia_email)
    emails_minga      = _email_set(df_minga)

    df["tiene_registro_web"] = df["email"].isin(emails_registro)
    df["inscrito_taller"]    = df["email"].isin(emails_talleres)
    df["asistio_taller"]     = df["email"].isin(emails_asistencia)
    df["uso_minga"]          = df["email"].isin(emails_minga)

    logger.info(
        f"Flags calculados | "
        f"registro={df['tiene_registro_web'].sum()} | "
        f"inscritos={df['inscrito_taller'].sum()} | "
        f"asistidos={df['asistio_taller'].sum()} | "
        f"minga={df['uso_minga'].sum()}"
    )
    return df


def _compute_tasa_asistencia(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Calcula la tasa de asistencia por usuario.

    Fórmula:
        tasa_asistencia = num_talleres_asistidos / num_talleres_inscritos

    Casos especiales:
        - num_talleres_inscritos == 0 → tasa = None (no aplica)
        - num_talleres_asistidos > num_talleres_inscritos → tasa puede ser > 1.0
          (asistió a talleres en los que no se inscribió formalmente)
          Se conserva el valor real sin truncar.

    Args:
        df:     DataFrame maestro con columnas de conteos.
        logger: Logger del módulo.

    Returns:
        DataFrame con columna tasa_asistencia añadida.
    """
    df = df.copy()

    cols_presentes = (
        "num_talleres_inscritos" in df.columns
        and "num_talleres_asistidos" in df.columns
    )

    if not cols_presentes:
        df["tasa_asistencia"] = None
        logger.warning("tasa_asistencia no calculada — faltan columnas de conteo")
        return df

    inscritos = pd.to_numeric(df["num_talleres_inscritos"],  errors="coerce").fillna(0)
    asistidos = pd.to_numeric(df["num_talleres_asistidos"], errors="coerce").fillna(0)

    df["tasa_asistencia"] = np.where(
        inscritos > 0,
        (asistidos / inscritos).round(4),
        None,
    )

    con_tasa = df["tasa_asistencia"].notna().sum()
    logger.info(
        f"Tasa asistencia calculada | usuarios con tasa: {con_tasa} | "
        f"sin inscripción formal: {(inscritos == 0).sum()}"
    )
    return df


def _compute_fecha_primer_registro(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Calcula la fecha_primer_registro como el mínimo entre todas las fechas
    de las distintas fuentes.

    Fuentes de fecha consideradas (si existen en el DataFrame):
        fecha_creacion        → Registro RCV
        fecha_inscripcion_min → Talleres (inscripciones)
        fecha_asistencia_min  → Asistencia (consolidado histórico)
        fecha_minga_min       → Minga

    Args:
        df:     DataFrame maestro.
        logger: Logger del módulo.

    Returns:
        DataFrame con columna fecha_primer_registro añadida.
    """
    df = df.copy()

    date_cols = [
        c for c in [
            "fecha_creacion",
            "fecha_inscripcion_min",
            "fecha_asistencia_min",
            "fecha_minga_min",
        ]
        if c in df.columns
    ]

    if not date_cols:
        df["fecha_primer_registro"] = pd.NaT
        logger.warning("fecha_primer_registro: ninguna columna de fecha disponible")
        return df

    date_df = pd.DataFrame(index=df.index)
    for col in date_cols:
        date_df[col] = pd.to_datetime(df[col], errors="coerce")

    df["fecha_primer_registro"] = date_df.min(axis=1)

    con_fecha = df["fecha_primer_registro"].notna().sum()
    logger.info(
        f"fecha_primer_registro calculada | con fecha: {con_fecha} | "
        f"sin fecha: {df['fecha_primer_registro'].isna().sum()}"
    )
    return df


def _compute_fuentes_column(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Genera la columna 'fuentes' como JSON list de las fuentes de cada usuario.

    Ejemplo:
        usuario en registro + asistencia → '["registro", "asistencia"]'
        usuario solo en talleres         → '["talleres"]'

    Args:
        df:     DataFrame maestro con flags de participación.
        logger: Logger del módulo.

    Returns:
        DataFrame con columna fuentes añadida.
    """
    df = df.copy()

    flag_to_source = {
        "tiene_registro_web": "registro",
        "inscrito_taller":    "talleres",
        "asistio_taller":     "asistencia",
        "uso_minga":          "minga",
    }

    def _build_fuentes(row: pd.Series) -> str:
        fuentes = [
            source
            for flag, source in flag_to_source.items()
            if row.get(flag, False)
        ]
        return json.dumps(fuentes, ensure_ascii=False)

    flags_disponibles = [f for f in flag_to_source if f in df.columns]
    if not flags_disponibles:
        df["fuentes"] = json.dumps([])
        logger.warning("fuentes: ningún flag de participación disponible")
        return df

    df["fuentes"] = df.apply(_build_fuentes, axis=1)

    top_fuentes = df["fuentes"].value_counts().head(5).to_dict()
    logger.info(f"Columna fuentes generada | top combinaciones: {top_fuentes}")
    return df


def _generate_nombre_key_column(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Genera la columna nombre_key en el master usando nombre + apellido.

    Necesaria para el matching secundario: los registros de asistencia
    sin email se buscarán en el master por esta clave.

    Args:
        df:     DataFrame maestro con columnas nombre y apellido.
        logger: Logger del módulo.

    Returns:
        DataFrame con columna nombre_key añadida (o sobreescrita).
    """
    df = df.copy()

    nombre_col   = df["nombre"]   if "nombre"   in df.columns else pd.Series([None] * len(df))
    apellido_col = df["apellido"] if "apellido" in df.columns else pd.Series([None] * len(df))

    df["nombre_key"] = [
        _build_nombre_key(n, a)
        for n, a in zip(nombre_col, apellido_col)
    ]

    con_key = df["nombre_key"].notna().sum()
    logger.info(
        f"nombre_key generado | con clave: {con_key} | "
        f"sin clave (nombre nulo): {df['nombre_key'].isna().sum()}"
    )
    return df


def _apply_secondary_matching(
    df_master: pd.DataFrame,
    df_asistencia_no_email: pd.DataFrame,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, int, int]:
    """
    Aplica matching secundario para registros de asistencia sin email.

    Estrategia:
        1. Construir lookup de nombre_key → índice en master
        2. Para cada registro sin email en asistencia:
           a. Si nombre_key coincide con un registro del master:
              → Actualizar asistio_taller=True, incrementar num_talleres_asistidos
              → Marcar match como LOW confidence en esa fila
           b. Si no hay match:
              → Agregar como fila nueva con email=None, match_confidence=UNMATCHED

    Args:
        df_master:               DataFrame maestro post-merge primario.
        df_asistencia_no_email:  Registros de asistencia sin email.
        logger:                  Logger del módulo.

    Returns:
        Tupla (df_master_actualizado, low_confidence_count, unmatched_count).
    """
    if df_asistencia_no_email.empty:
        logger.info("Matching secundario: sin registros de asistencia sin email")
        return df_master, 0, 0

    df_master = df_master.copy()
    low_count = 0
    unmatched_count = 0
    unmatched_rows: list[dict] = []

    if "nombre_key" not in df_master.columns:
        logger.warning(
            "Matching secundario: nombre_key no presente en master — "
            "todos los registros sin email serán UNMATCHED"
        )
        unmatched_count = len(df_asistencia_no_email)
        return df_master, 0, unmatched_count

    nombre_key_index: dict[str, int] = {
        key: idx
        for idx, key in df_master["nombre_key"].dropna().items()
    }

    for _, row in df_asistencia_no_email.iterrows():
        # Intentar construir nombre_key desde nombre_asistente si existe
        nombre_asistente = row.get("nombre_asistente")
        nk = None
        if nombre_asistente and pd.notna(nombre_asistente):
            partes = str(nombre_asistente).strip().split()
            if len(partes) >= 2:
                nk = _build_nombre_key(partes[0], " ".join(partes[1:]))
            elif len(partes) == 1:
                nk = _build_nombre_key(partes[0], None)

        if nk and nk in nombre_key_index:
            master_idx = nombre_key_index[nk]
            df_master.at[master_idx, "asistio_taller"] = True

            current_asistidos = df_master.at[master_idx, "num_talleres_asistidos"]
            df_master.at[master_idx, "num_talleres_asistidos"] = (
                (int(current_asistidos) + 1)
                if pd.notna(current_asistidos)
                else 1
            )

            current_conf = df_master.at[master_idx, "match_confidence"]
            if current_conf != "HIGH":
                df_master.at[master_idx, "match_confidence"] = "LOW"

            low_count += 1
            logger.debug(
                f"Match secundario | nombre_key='{nk}' → master_idx={master_idx}"
            )

        else:
            nombre_raw = row.get("nombre_asistente", "")
            nueva_fila: dict = {
                "email":                    None,
                "match_confidence":         "UNMATCHED",
                "nombre_key":               nk,
                "nombre":                   nombre_raw,
                "apellido":                 None,
                "tiene_registro_web":       False,
                "inscrito_taller":          False,
                "asistio_taller":           True,
                "uso_minga":                False,
                "num_talleres_inscritos":   0,
                "num_talleres_asistidos":   1,
                "num_conversaciones_minga": 0,
                "fuentes":                  json.dumps(["asistencia"]),
            }
            unmatched_rows.append(nueva_fila)
            unmatched_count += 1

    if unmatched_rows:
        df_unmatched = pd.DataFrame(unmatched_rows)
        df_master = pd.concat([df_master, df_unmatched], ignore_index=True)
        logger.info(
            f"Matching secundario | LOW: {low_count} | "
            f"UNMATCHED agregados: {unmatched_count}"
        )

    return df_master, low_count, unmatched_count


def _finalize_schema(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Asegura que el DataFrame maestro tenga todas las columnas del esquema
    final, en el orden correcto.

    Columnas faltantes se añaden con valor None/NaN.
    Columnas extra (columnas intermedias del proceso) se descartan.
    Añade columna fecha_etl con el timestamp del run.

    Args:
        df:     DataFrame maestro previo a la finalización.
        logger: Logger del módulo.

    Returns:
        DataFrame con esquema final limpio.
    """
    df = df.copy()

    df["fecha_etl"] = pd.Timestamp.now()

    if "match_confidence" not in df.columns:
        df["match_confidence"] = "HIGH"
    else:
        df["match_confidence"] = df["match_confidence"].fillna("HIGH")

    cols_faltantes = [c for c in MASTER_SCHEMA if c not in df.columns]
    if cols_faltantes:
        logger.info(f"Columnas añadidas con None: {cols_faltantes}")
    for col in cols_faltantes:
        df[col] = None

    extra_cols = [
        c for c in df.columns
        if c not in MASTER_SCHEMA
        and c in (
            "talleres_titulos",
            "fecha_inscripcion_min",
            "fecha_minga_min",
            "fecha_asistencia_min",
        )
    ]
    cols_final = MASTER_SCHEMA + extra_cols
    cols_existentes = [c for c in cols_final if c in df.columns]
    df = df[cols_existentes]

    logger.info(
        f"Schema finalizado | columnas: {len(df.columns)} | filas: {len(df)}"
    )
    return df


# ── Función pública principal ──────────────────────────────────────────────────

def consolidate(dataframes: dict[str, pd.DataFrame]) -> ConsolidateResult:
    """
    Función principal de la capa de consolidación.

    Toma los DataFrames transformados de las 4 fuentes y genera la tabla
    maestra usuarios_master con un registro por email (o por nombre_key
    para los registros de asistencia UNMATCHED sin email).

    Args:
        dataframes: Diccionario con las 4 fuentes transformadas.
                    Claves esperadas: "registro", "talleres", "minga", "asistencia"
                    Valores: pd.DataFrame retornados por transform().
                    Fuentes ausentes o vacías se omiten sin error.

    Returns:
        ConsolidateResult con el DataFrame maestro y métricas de consolidación.
        Nunca lanza excepciones al caller.
    """
    logger = get_logger("consolidate")
    warnings: list[str] = []

    separador = "═" * 55
    logger.info(
        f"\n{separador}\n"
        f"  Consolidate | fuentes: {list(dataframes.keys())}\n"
        f"{separador}"
    )

    try:
        # 1 ── Extraer DataFrames de forma segura
        df_registro  = _safe_df(dataframes, "registro")
        df_talleres  = _safe_df(dataframes, "talleres")
        df_minga     = _safe_df(dataframes, "minga")
        df_asistencia = _safe_df(dataframes, "asistencia")

        for key, df in [
            ("registro",   df_registro),
            ("talleres",   df_talleres),
            ("minga",      df_minga),
            ("asistencia", df_asistencia),
        ]:
            if df.empty:
                msg = f"Fuente '{key}' vacía o ausente — se omitirá en la consolidación"
                logger.warning(msg)
                warnings.append(msg)

        # 2 ── Agregar fuentes multi-fila
        df_tal_agg                          = _aggregate_talleres(df_talleres, logger)
        df_min_agg                          = _aggregate_minga(df_minga, logger)
        df_asi_agg, df_asistencia_no_email  = _aggregate_asistencia(df_asistencia, logger)

        # 3 ── Preparar resumen de registro
        df_reg_summary = _build_registro_summary(df_registro, logger)

        # 4 ── Merge outer de las 4 fuentes
        df_master = _merge_all_sources(
            df_reg_summary, df_tal_agg, df_asi_agg, df_min_agg, logger
        )

        # 5 ── Coalesce de campos personales (no-op con fuente asistencia)
        df_master = _coalesce_personal_fields(df_master, logger)

        # 6 ── Flags de participación
        df_master = _compute_participation_flags(
            df_master, df_registro, df_talleres,
            df_asi_agg, df_minga, logger
        )

        # 7 ── Rellenar conteos NaN con 0
        for count_col in [
            "num_talleres_inscritos",
            "num_talleres_asistidos",
            "num_conversaciones_minga",
        ]:
            if count_col in df_master.columns:
                df_master[count_col] = (
                    pd.to_numeric(df_master[count_col], errors="coerce")
                    .fillna(0)
                    .astype("Int64")
                )

        # 8 ── Tasa de asistencia
        df_master = _compute_tasa_asistencia(df_master, logger)

        # 9 ── Fecha primer registro
        df_master = _compute_fecha_primer_registro(df_master, logger)

        # 10 ── Columna fuentes (JSON)
        df_master = _compute_fuentes_column(df_master, logger)

        # 11 ── nombre_key en master
        df_master = _generate_nombre_key_column(df_master, logger)

        # Inicializar match_confidence antes del matching secundario.
        # _apply_secondary_matching necesita leer y escribir esta columna.
        # _finalize_schema la inicializaría después, pero es demasiado tarde.
        if "match_confidence" not in df_master.columns:
            df_master["match_confidence"] = "HIGH"

        # 12 ── Matching secundario para registros de asistencia sin email
        df_master, low_conf, unmatched = _apply_secondary_matching(
            df_master, df_asistencia_no_email, logger
        )

        # 13 ── Recalcular fuentes después del matching secundario
        df_master = _compute_fuentes_column(df_master, logger)

        # 14 ── Schema final
        df_master = _finalize_schema(df_master, logger)

        # ── Métricas finales ───────────────────────────────────────────────────
        total       = len(df_master)
        n_registro  = int(df_master.get("tiene_registro_web",  pd.Series(dtype=bool)).sum())
        n_inscritos = int(df_master.get("inscrito_taller",     pd.Series(dtype=bool)).sum())
        n_asistidos = int(df_master.get("asistio_taller",      pd.Series(dtype=bool)).sum())
        n_minga     = int(df_master.get("uso_minga",           pd.Series(dtype=bool)).sum())

        flags_cols = [
            "tiene_registro_web", "inscrito_taller",
            "asistio_taller", "uso_minga",
        ]
        flags_presentes = [c for c in flags_cols if c in df_master.columns]
        if flags_presentes:
            fuente_count  = df_master[flags_presentes].astype(bool).sum(axis=1)
            n_multifuente = int((fuente_count >= 2).sum())
        else:
            n_multifuente = 0

        logger.info(
            f"\nConsolidación completada:\n"
            f"  Total usuarios:     {total}\n"
            f"  Registro web:       {n_registro}\n"
            f"  Inscritos taller:   {n_inscritos}\n"
            f"  Asistieron taller:  {n_asistidos}\n"
            f"  Usaron Minga:       {n_minga}\n"
            f"  Multifuente (2+):   {n_multifuente}\n"
            f"  Match LOW:          {low_conf}\n"
            f"  UNMATCHED:          {unmatched}"
        )

        return ConsolidateResult(
            df=df_master,
            total_usuarios=total,
            usuarios_registro=n_registro,
            usuarios_inscritos_taller=n_inscritos,
            usuarios_asistieron_taller=n_asistidos,
            usuarios_minga=n_minga,
            usuarios_multifuente=n_multifuente,
            low_confidence_matches=low_conf,
            unmatched_records=unmatched,
            warnings=warnings,
        )

    except Exception as exc:
        logger.critical(
            f"Error inesperado en consolidate() | error={exc}",
            exc_info=True,
        )
        return ConsolidateResult(
            df=pd.DataFrame(),
            total_usuarios=0,
            usuarios_registro=0,
            usuarios_inscritos_taller=0,
            usuarios_asistieron_taller=0,
            usuarios_minga=0,
            usuarios_multifuente=0,
            low_confidence_matches=0,
            unmatched_records=0,
            warnings=[f"CRITICAL: {exc}"],
        )

"""
transform.py — Capa de transformación del pipeline ETL.

Responsabilidad: recibe un DataFrame extraído por cualquier extractor
y retorna un DataFrame limpio, normalizado y listo para consolidación.

Esta capa NO lee archivos CSV.
Esta capa NO une fuentes entre sí.
Esta capa NO escribe en base de datos.

Proyecto: Déficit Cero — Community Data Pipeline
Versión: 1.1.0
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from config.mappings import (
    COLUMN_MAPPING,
    GENDER_NORMALIZATION,
    SOURCE_DATE_COLUMNS,
)
from scripts.utils import get_logger


# ── Constantes del módulo ──────────────────────────────────────────────────────

# Valores que representan "nulo" en los datos fuente
NULL_LIKE_VALUES: frozenset[str] = frozenset(
    {"nan", "none", "null", "n/a", "na", "-", "s/d", ""}
)

# Regex para validación básica de formato de email
EMAIL_REGEX: re.Pattern = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Columnas de texto → aplicar strip + title case (nombres propios)
_STR_TITLE_COLS: list[str] = [
    "nombre", "apellido", "nombre_pantalla", "nombre_asistente",
]

# Columnas de texto → aplicar strip + lowercase (clasificaciones)
_STR_LOWER_COLS: list[str] = [
    "region", "comuna", "situacion_habitacional",
    "estado_registro", "nacionalidad", "rol",
]

# Columnas de texto → aplicar solo strip (identificadores)
_STR_STRIP_COLS: list[str] = [
    "whatsapp", "member_id", "taller_titulo",
]

# Columnas numéricas por fuente.
# La fuente "asistencia" (consolidado_asistencia.csv) no tiene columnas
# numéricas que requieran conversión: taller_entry_id es texto, fecha_taller
# se parsea como fecha, email y nombre_asistente son texto.
_NUMERIC_COLS: dict[str, list[str]] = {
    "registro":   ["cuantas_personas_viven"],
    "talleres":   [],
    "minga":      ["num_mensajes", "edad_minga"],
    "asistencia": [],
}

# Columnas de fecha adicionales por fuente (complementan SOURCE_DATE_COLUMNS).
# La fuente "asistencia" tiene fecha_taller como columna principal de fecha,
# definida en SOURCE_DATE_COLUMNS["asistencia"]. No tiene fechas adicionales.
# NOTA: fecha_taller ya llega parseada como datetime64 desde
# AsistenciaTalleresExtractor — el parseo aquí es seguro pero redundante
# (pandas no reparsea un datetime64 existente).
_EXTRA_DATE_COLS: dict[str, list[str]] = {
    "registro":   ["fecha_nacimiento", "fecha_paso2"],
    "talleres":   [],
    "minga":      [],
    "asistencia": [],
}


# ── Clase de resultado ─────────────────────────────────────────────────────────

@dataclass
class TransformResult:
    """
    Resultado completo de la capa de transformación para una fuente.

    Atributos:
        df:                     DataFrame transformado, listo para consolidación.
        source_name:            Nombre de la fuente procesada.
        rows_input:             Filas en el DataFrame de entrada.
        rows_output:            Filas en el DataFrame de salida.
        rows_dropped_no_email:  Filas eliminadas por email inválido o ausente.
        rows_dropped_duplicate: Filas eliminadas por duplicado de email.
        warnings:               Advertencias generadas durante la transformación.
        quality_score:          Score de calidad del 0.0 al 1.0.
    """

    df: pd.DataFrame
    source_name: str
    rows_input: int
    rows_output: int
    rows_dropped_no_email: int
    rows_dropped_duplicate: int
    warnings: list[str]
    quality_score: float


# ── Funciones privadas ─────────────────────────────────────────────────────────

def _validate_input(
    df: pd.DataFrame,
    source_name: str,
    logger: logging.Logger,
) -> list[str]:
    """
    Verifica que el DataFrame de entrada sea utilizable.

    Comprueba: DataFrame no vacío, fuente conocida, columna email presente
    y columnas de metadatos del extractor presentes.

    Args:
        df:          DataFrame recibido del extractor.
        source_name: Nombre de la fuente (debe existir en COLUMN_MAPPING).
        logger:      Logger del módulo.

    Returns:
        Lista de warnings generados. Vacía si todo está correcto.
    """
    warnings_list: list[str] = []

    logger.info(f"Validando entrada | fuente={source_name}")

    if df is None or df.empty:
        msg = f"DataFrame de entrada vacío para fuente '{source_name}'"
        logger.warning(msg)
        warnings_list.append(msg)
        return warnings_list

    logger.info(f"Shape de entrada: {df.shape} | columnas: {df.columns.tolist()}")

    if source_name not in COLUMN_MAPPING:
        msg = f"Fuente '{source_name}' no encontrada en COLUMN_MAPPING"
        logger.warning(msg)
        warnings_list.append(msg)

    if "email" not in df.columns:
        msg = f"Columna 'email' ausente en fuente '{source_name}'"
        logger.warning(msg)
        warnings_list.append(msg)

    for meta_col in ("_source_name", "_source_file", "_extracted_at"):
        if meta_col not in df.columns:
            msg = f"Metadato '{meta_col}' ausente — verificar extractor"
            logger.warning(msg)
            warnings_list.append(msg)

    return warnings_list


def _normalize_emails(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Normaliza la columna 'email': convierte a string, aplica strip y
    lowercase, reemplaza valores nulos canónicos y valida el formato
    con regex.

    Los emails con formato inválido se reemplazan con pd.NA pero la fila
    NO se elimina aquí — eso ocurre en _drop_invalid_emails().

    Args:
        df:     DataFrame con columna 'email'.
        logger: Logger del módulo.

    Returns:
        DataFrame con columna 'email' normalizada.
    """
    if "email" not in df.columns:
        logger.warning("Columna 'email' no encontrada — omitiendo normalización")
        return df

    df = df.copy()
    nulos_antes = int(df["email"].isna().sum())

    # 1. Normalizar formato
    df["email"] = df["email"].astype(str).str.strip().str.lower()

    # 2. Marcar strings que representan nulo como pd.NA real
    df["email"] = df["email"].replace(list(NULL_LIKE_VALUES), pd.NA)

    # 3. Validar formato con regex
    mask_no_nulo = df["email"].notna()
    mask_invalido = mask_no_nulo & ~df["email"].str.match(EMAIL_REGEX, na=False)
    n_invalidos = int(mask_invalido.sum())

    if n_invalidos > 0:
        ejemplos = df.loc[mask_invalido, "email"].head(3).tolist()
        logger.warning(
            f"Emails con formato inválido: {n_invalidos} | ejemplos: {ejemplos}"
        )
        df.loc[mask_invalido, "email"] = pd.NA

    nulos_despues = int(df["email"].isna().sum())
    validos = int(df["email"].notna().sum())

    logger.info(
        f"Emails normalizados | válidos={validos} | "
        f"nulos_antes={nulos_antes} → nulos_después={nulos_despues} | "
        f"invalidados_por_formato={n_invalidos}"
    )

    return df


def _drop_invalid_emails(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, int]:
    """
    Elimina filas donde el email es NaN tras la normalización.

    IMPORTANTE — excepción para la fuente 'asistencia':
        Las filas de consolidado_asistencia.csv sin email son válidas porque
        corresponden a asistentes registrados manualmente sin cuenta de
        plataforma (match_confidence LOW/UNMATCHED). La función transform()
        omite llamar a _drop_invalid_emails() cuando source_name == 'asistencia',
        preservando esas filas para el matching secundario por nombre que
        ocurre en consolidate.py (_apply_secondary_matching).

    Args:
        df:     DataFrame con 'email' ya normalizado.
        logger: Logger del módulo.

    Returns:
        Tupla (DataFrame_limpio, cantidad_filas_eliminadas).
    """
    if "email" not in df.columns:
        return df, 0

    total_antes = len(df)
    df_limpio = df[df["email"].notna()].copy()
    eliminadas = total_antes - len(df_limpio)

    if eliminadas > 0:
        logger.info(f"Eliminadas {eliminadas} filas por email ausente o inválido")
    else:
        logger.info("Sin filas eliminadas por email — todos son válidos")

    return df_limpio, eliminadas


def _normalize_strings(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Limpia y normaliza columnas de texto según tres categorías:

    - Nombre propio (nombre, apellido, nombre_asistente): strip + title case
    - Clasificación (region, comuna, etc.): strip + lowercase
    - Identificador (whatsapp, member_id): solo strip

    En todas, reemplaza valores nulos canónicos (nan, none, n/a, -, s/d)
    por pd.NA real.

    Args:
        df:     DataFrame a normalizar.
        logger: Logger del módulo.

    Returns:
        DataFrame con columnas de texto normalizadas.
    """
    df = df.copy()
    cols_procesadas = 0

    for col in _STR_TITLE_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
            df[col] = df[col].replace(list(NULL_LIKE_VALUES), pd.NA)
            cols_procesadas += 1

    for col in _STR_LOWER_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.lower()
            df[col] = df[col].replace(list(NULL_LIKE_VALUES), pd.NA)
            cols_procesadas += 1

    for col in _STR_STRIP_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(list(NULL_LIKE_VALUES), pd.NA)
            cols_procesadas += 1

    logger.info(f"Strings normalizados | columnas procesadas: {cols_procesadas}")
    return df


def _normalize_gender(
    df: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Estandariza la columna 'genero' usando GENDER_NORMALIZATION de mappings.py.

    Valores resultantes posibles:
        masculino | femenino | otro | no_especificado

    Si la columna no existe en el DataFrame, retorna sin cambios.

    Args:
        df:     DataFrame con columna 'genero' (opcional).
        logger: Logger del módulo.

    Returns:
        DataFrame con 'genero' estandarizado.
    """
    if "genero" not in df.columns:
        logger.info("Columna 'genero' no presente — omitiendo normalización")
        return df

    df = df.copy()

    df["genero"] = (
        df["genero"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(GENDER_NORMALIZATION)
        .fillna("no_especificado")
    )

    distribucion = df["genero"].value_counts().to_dict()
    logger.info(f"Género normalizado | distribución: {distribucion}")

    return df


def _normalize_dates(
    df: pd.DataFrame,
    source_name: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Parsea columnas de fecha y hora según la fuente.

    Usa dayfirst=True para compatibilidad con formatos chilenos DD/MM/YYYY.
    Emite WARNING si más del 50% de los valores resultan NaT, lo que indica
    posible incompatibilidad de formato en el CSV fuente.

    NOTA sobre la fuente 'asistencia':
        fecha_taller ya llega como datetime64 desde AsistenciaTalleresExtractor
        (que aplica normalize_fecha_taller con detección de patrón estricta).
        pd.to_datetime sobre un datetime64 es seguro pero redundante — producirá
        0% NaT y el log correspondiente sin efectos secundarios.

    Args:
        df:          DataFrame con columnas de fecha.
        source_name: Nombre de la fuente para determinar columnas a parsear.
        logger:      Logger del módulo.

    Returns:
        DataFrame con fechas convertidas a datetime (NaT si no convertibles).
    """
    df = df.copy()

    # Columna principal de fecha para esta fuente
    col_principal: Optional[str] = SOURCE_DATE_COLUMNS.get(source_name)
    cols_a_parsear: list[str] = []

    if col_principal:
        cols_a_parsear.append(col_principal)

    cols_a_parsear.extend(_EXTRA_DATE_COLS.get(source_name, []))

    for col in cols_a_parsear:
        if col not in df.columns:
            logger.debug(f"Columna de fecha '{col}' no presente — omitiendo")
            continue

        if df[col].notna().sum() == 0:
            logger.debug(f"Columna '{col}' completamente vacía — omitiendo parseo")
            continue

        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

        nat_count = int(df[col].isna().sum())
        nat_pct = (nat_count / len(df)) * 100 if len(df) > 0 else 0.0

        if nat_pct > 50:
            logger.warning(
                f"Columna '{col}': {nat_pct:.1f}% de valores no parseables (NaT) — "
                f"verificar formato de fecha en CSV fuente"
            )
        else:
            logger.info(
                f"Fecha parseada | col={col} | NaT={nat_count} ({nat_pct:.1f}%)"
            )

    return df


def _normalize_numerics(
    df: pd.DataFrame,
    source_name: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Convierte columnas numéricas según la fuente.

    Caso especial — 'edad_minga' en Minga:
        El CSV puede contener strings como '32 años' o '45 años de edad'.
        Se extraen los dígitos con regex antes de convertir a numérico.

    Args:
        df:          DataFrame con columnas numéricas a convertir.
        source_name: Nombre de la fuente.
        logger:      Logger del módulo.

    Returns:
        DataFrame con columnas numéricas convertidas.
    """
    df = df.copy()
    cols = _NUMERIC_COLS.get(source_name, [])

    for col in cols:
        if col not in df.columns:
            logger.debug(f"Columna numérica '{col}' no presente — omitiendo")
            continue

        nulos_antes = int(df[col].isna().sum())

        if col == "edad_minga":
            # Extraer dígitos antes de convertir (maneja "32 años", etc.)
            def _extraer_numero(valor) -> Optional[float]:
                if pd.isna(valor):
                    return None
                match = re.search(r"(\d+)", str(valor))
                return float(match.group(1)) if match else None

            df[col] = df[col].apply(_extraer_numero)

        df[col] = pd.to_numeric(df[col], errors="coerce")

        # Convertir a entero nullable cuando corresponde
        if col in ("cuantas_personas_viven", "num_mensajes", "edad_minga"):
            try:
                df[col] = df[col].astype("Int64")
            except (ValueError, TypeError):
                logger.warning(
                    f"No se pudo convertir '{col}' a Int64 — conservando float"
                )

        nulos_despues = int(df[col].isna().sum())
        no_convertibles = nulos_despues - nulos_antes

        if no_convertibles > 0:
            logger.warning(
                f"Columna '{col}': {no_convertibles} valores no convertibles a numérico"
            )
        else:
            logger.info(
                f"Numérico convertido | col={col} | nulos_finales={nulos_despues}"
            )

    return df


def _deduplicate(
    df: pd.DataFrame,
    source_name: str,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, int]:
    """
    Elimina duplicados dentro de la fuente según la estrategia de cada una.

    Estrategias:
        registro:   deduplicar por email, conservar el más antiguo
                    (fecha_creacion ascendente).
        talleres:   deduplicar por formulario_entry_id (ID único por inscripción).
                    Un usuario puede inscribirse a múltiples talleres — emails
                    repetidos son filas legítimas. taller_entry_id NO es la
                    clave correcta (es el ID del taller, no de la inscripción).
        minga:      no deduplicar — múltiples conversaciones por usuario
                    son válidas e informativas.
        asistencia: no deduplicar aquí — la deduplicación por
                    (taller_entry_id, email, fecha_taller) ya ocurrió dentro
                    de AsistenciaTalleresExtractor antes de que llegue a transform.

    Args:
        df:          DataFrame a deduplicar.
        source_name: Nombre de la fuente.
        logger:      Logger del módulo.

    Returns:
        Tupla (DataFrame_deduplicado, cantidad_filas_eliminadas).
    """
    total_antes = len(df)
    eliminadas = 0

    if source_name == "registro":
        if "email" not in df.columns:
            logger.warning(
                "No se puede deduplicar 'registro' sin columna 'email'"
            )
            return df, 0

        if "fecha_creacion" in df.columns:
            df = df.sort_values(
                "fecha_creacion", ascending=True, na_position="last"
            )

        df = df.drop_duplicates(subset="email", keep="first").copy()
        eliminadas = total_antes - len(df)

        if eliminadas:
            logger.info(
                f"Deduplicación registro | eliminados {eliminadas} duplicados por email"
            )
        else:
            logger.info("Deduplicación registro | sin duplicados encontrados")

    elif source_name == "talleres":
        # Deduplicar por formulario_entry_id: identificador único por inscripción.
        # taller_entry_id NO es el campo correcto — es el ID del taller,
        # compartido por todos sus inscritos. Usarlo como clave de dedup
        # colapsaría 11.000+ inscripciones en ~47 filas (una por taller).
        if "formulario_entry_id" in df.columns:
            df = df.drop_duplicates(subset="formulario_entry_id", keep="first").copy()
            eliminadas = total_antes - len(df)

        emails_unicos = (
            df["email"].nunique() if "email" in df.columns else 0
        )
        logger.info(
            f"Talleres | filas={len(df)} | emails_únicos={emails_unicos} | "
            f"dups_formulario_id_eliminados={eliminadas}"
        )

    elif source_name in ("minga", "asistencia"):
        # minga: múltiples conversaciones por usuario son válidas.
        # asistencia: la deduplicación ya la hizo AsistenciaTalleresExtractor
        # por (taller_entry_id, email, fecha_taller). Transform no deduplica.
        emails_unicos = (
            df["email"].dropna().nunique() if "email" in df.columns else 0
        )
        logger.info(
            f"{source_name} | sin deduplicación adicional | filas={len(df)} | "
            f"emails_únicos={emails_unicos}"
        )

    else:
        # Fuente desconocida — fallback seguro por email
        if "email" in df.columns:
            df = df.drop_duplicates(subset="email", keep="first").copy()
            eliminadas = total_antes - len(df)
        logger.warning(
            f"Fuente desconocida '{source_name}' — deduplicación por email como fallback"
        )

    return df, eliminadas


def _compute_quality_score(
    rows_input: int,
    rows_output: int,
    rows_dropped_no_email: int,
    rows_dropped_duplicate: int,
    warnings: list[str],
) -> float:
    """
    Calcula un score de calidad del 0.0 al 1.0 para el DataFrame.

    Fórmula:
        base_score = rows_output / rows_input
        penalidad  = len(warnings) * 0.02   (2% por cada warning)
        score      = max(0.0, min(1.0, base_score - penalidad))

    Interpretación:
        >= 0.90  →  Alta calidad
        0.70-0.89 → Calidad media, revisar warnings
        < 0.70   →  Baja calidad, intervención recomendada

    Args:
        rows_input:             Filas de entrada.
        rows_output:            Filas de salida.
        rows_dropped_no_email:  Filas eliminadas por email inválido.
        rows_dropped_duplicate: Filas eliminadas por duplicado.
        warnings:               Lista de advertencias generadas.

    Returns:
        Score entre 0.0 y 1.0, redondeado a 4 decimales.
    """
    if rows_input == 0:
        return 0.0

    base_score = rows_output / rows_input
    penalidad = len(warnings) * 0.02
    score = max(0.0, min(1.0, base_score - penalidad))

    return round(score, 4)


# ── Función pública principal ──────────────────────────────────────────────────

def transform(df: pd.DataFrame, source_name: str) -> TransformResult:
    """
    Función principal de la capa de transformación.

    Orquesta las funciones privadas en el siguiente orden:
        validación → emails → drop_invalid → strings → género →
        fechas → numéricos → deduplicación → quality_score

    La fuente 'asistencia' recibe tratamiento especial: sus filas sin email
    son conservadas (match_confidence LOW/UNMATCHED) para el matching
    secundario por nombre_asistente que ocurre en consolidate.py
    (_apply_secondary_matching). Esta es la misma semántica que tenía
    la fuente 'zoom' en v1.0.0.

    Args:
        df:          DataFrame recibido del extractor.
        source_name: Nombre de la fuente
                     ("registro" | "talleres" | "minga" | "asistencia").

    Returns:
        TransformResult con DataFrame transformado y métricas de calidad.
        Nunca lanza excepciones al caller — errores críticos se capturan
        y retornan un TransformResult con df vacío y quality_score=0.0.
    """
    logger = get_logger("transform")

    separador = "=" * 55
    logger.info(f"\n{separador}\n  Transform | fuente={source_name}\n{separador}")

    rows_input = 0
    dropped_no_email = 0
    dropped_duplicate = 0

    try:
        rows_input = len(df) if df is not None else 0

        # 1 ── Validar entrada
        warnings = _validate_input(df, source_name, logger)

        if df is None or df.empty:
            logger.warning(
                f"DataFrame vacío recibido — retornando TransformResult vacío "
                f"para '{source_name}'"
            )
            return TransformResult(
                df=pd.DataFrame(),
                source_name=source_name,
                rows_input=0,
                rows_output=0,
                rows_dropped_no_email=0,
                rows_dropped_duplicate=0,
                warnings=warnings,
                quality_score=0.0,
            )

        # 2 ── Normalizar emails
        df = _normalize_emails(df, logger)

        # 3 ── Eliminar emails inválidos.
        # La fuente 'asistencia' es la excepción: conserva filas sin email
        # porque corresponden a asistentes sin cuenta de plataforma, que
        # serán procesados por matching secundario en consolidate.py.
        if source_name != "asistencia":
            df, dropped_no_email = _drop_invalid_emails(df, logger)
        else:
            logger.info(
                "Fuente 'asistencia' — conservando filas sin email "
                "para matching secundario por nombre_asistente"
            )

        # 4 ── Normalizar strings
        df = _normalize_strings(df, logger)

        # 5 ── Normalizar género
        df = _normalize_gender(df, logger)

        # 6 ── Normalizar fechas
        df = _normalize_dates(df, source_name, logger)

        # 7 ── Normalizar numéricos
        df = _normalize_numerics(df, source_name, logger)

        # 8 ── Deduplicar
        df, dropped_duplicate = _deduplicate(df, source_name, logger)

        rows_output = len(df)

        # 9 ── Calcular quality score
        quality_score = _compute_quality_score(
            rows_input=rows_input,
            rows_output=rows_output,
            rows_dropped_no_email=dropped_no_email,
            rows_dropped_duplicate=dropped_duplicate,
            warnings=warnings,
        )

        nivel = (
            "ALTA"  if quality_score >= 0.90 else
            "MEDIA" if quality_score >= 0.70 else
            "BAJA"
        )

        logger.info(
            f"Transform completado | fuente={source_name} | "
            f"entrada={rows_input} | salida={rows_output} | "
            f"sin_email={dropped_no_email} | duplicados={dropped_duplicate} | "
            f"quality={quality_score:.2%} ({nivel})"
        )

        return TransformResult(
            df=df,
            source_name=source_name,
            rows_input=rows_input,
            rows_output=rows_output,
            rows_dropped_no_email=dropped_no_email,
            rows_dropped_duplicate=dropped_duplicate,
            warnings=warnings,
            quality_score=quality_score,
        )

    except Exception as exc:
        logger.critical(
            f"Error inesperado en transform() | fuente={source_name} | "
            f"error={exc}",
            exc_info=True,
        )
        return TransformResult(
            df=pd.DataFrame(),
            source_name=source_name,
            rows_input=rows_input,
            rows_output=0,
            rows_dropped_no_email=0,
            rows_dropped_duplicate=0,
            warnings=[f"CRITICAL: {exc}"],
            quality_score=0.0,
        )

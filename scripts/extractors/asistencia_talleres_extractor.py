"""
asistencia_talleres_extractor.py — Extractor de asistencia histórica a talleres.

Lee consolidado_asistencia.csv, mantenido manualmente en Google Sheets y
exportado mensualmente. Representa el histórico completo de asistencia a
talleres desde 2023, incluyendo talleres presenciales, virtuales y otras
modalidades.

Reemplaza por completo la fuente zoom_asistencia.csv.

Columnas de entrada:
    TALLER_ENTRY_ID, TALLER_TITLE, FECHA_TALLER, MEMBER_EMAIL, MEMBER_SCREEN_NAME

Columnas de salida (tras mapeo):
    taller_entry_id, taller_titulo, fecha_taller, email, nombre_asistente

Proyecto: Unified Data Insights Platform
"""

import re
import sys
from pathlib import Path

import pandas as pd

# Soporte para ejecución desde source (desarrollo). En binario Nuitka
# este import no es necesario porque los módulos están embebidos.
_ROOT_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from scripts.extractors.base_extractor import BaseExtractor
from config.settings import DATA_RAW_DIR


ASISTENCIA_FILE = DATA_RAW_DIR / "consolidado_asistencia.csv"

_DATE_PATTERNS = [
    (re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"), "%Y-%m-%d",  "ISO"),
    (re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"),        "%d/%m/%Y",  "DD/MM/YYYY"),
    (re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$"),        "%d-%m-%Y",  "DD-MM-YYYY"),
]


def _parse_single_date(raw: str) -> pd.Timestamp | None:
    value = str(raw).strip()
    if not value or value.lower() in ("nan", "nat", "none", ""):
        return None
    for pattern, fmt, _ in _DATE_PATTERNS:
        if pattern.match(value):
            normalized = value
            if fmt == "%Y-%m-%d":
                normalized = value.replace("/", "-")
            elif fmt == "%d/%m/%Y":
                normalized = value.replace("-", "/")
            elif fmt == "%d-%m-%Y":
                normalized = value.replace("/", "-")
            try:
                return pd.Timestamp(normalized)
            except Exception:
                continue
    return None


def normalize_fecha_taller(series: pd.Series, logger) -> pd.Series:
    """
    Normaliza FECHA_TALLER aceptando tres formatos:
        ISO:         YYYY-MM-DD   (ej. 2026-05-28)
        Chile barra: DD/MM/YYYY   (ej. 28/5/2026)
        Chile guión: DD-MM-YYYY   (ej. 28-5-2026)

    Clasifica cada valor por patrón antes de convertir — no delega
    en la inferencia automática de pandas, que puede producir NaT
    en silencio o parsear días/meses en orden incorrecto.

    Valores que no coinciden con ningún formato conocido se registran
    individualmente en el log con su valor exacto.
    """
    resultados = []
    fallos: list[tuple[int, str]] = []

    for idx, raw in enumerate(series):
        ts = _parse_single_date(str(raw))
        if ts is None and pd.notna(raw) and str(raw).strip():
            fallos.append((idx, str(raw).strip()))
        resultados.append(ts)

    if fallos:
        logger.warning(
            f"FECHA_TALLER: {len(fallos)} valor(es) no reconocidos. "
            f"Formatos aceptados: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY. "
            f"Primeros 5 no parseados: {[v for _, v in fallos[:5]]}"
        )
    else:
        logger.info("FECHA_TALLER: todos los valores parseados correctamente.")

    return pd.Series(resultados, index=series.index, dtype="datetime64[ns]")


class AsistenciaTalleresExtractor(BaseExtractor):
    """
    Extractor para el consolidado histórico de asistencia a talleres.

    Hereda de BaseExtractor (detección de encoding, reparación de CSV,
    detección de delimitador, mapeo de columnas, logging estandarizado).

    Agrega:
        - Normalización robusta de FECHA_TALLER con 3 formatos aceptados
        - Deduplicación por (taller_entry_id, email, fecha_taller)
        - Limpieza de nombre_asistente (strip, nulo si vacío)
        - Métricas de calidad en el log al finalizar
    """

    def __init__(self, file_path: Path = ASISTENCIA_FILE) -> None:
        super().__init__(source_name="asistencia", file_path=file_path)

    def extract(self) -> pd.DataFrame:
        """
        Flujo de extracción:
            1. Validar que el archivo exista y no esté vacío.
            2. Leer el CSV (BaseExtractor: encoding, comillas, delimitador).
            3. Aplicar mapeo de columnas.
            4. Normalizar FECHA_TALLER.
            5. Limpiar nombre_asistente.
            6. Agregar metadatos de fuente (_source_name, _source_file).
            7. Deduplicar por (taller_entry_id, email, fecha_taller).
            8. Registrar métricas de calidad.

        Returns:
            DataFrame con una fila por asistencia única (taller × email × fecha).
            DataFrame vacío si el archivo no existe o la lectura falla.
        """
        self.logger.info(
            f"Iniciando extracción | fuente='asistencia' | "
            f"archivo='{self.file_path.name}'"
        )

        if not self.validate_file():
            return pd.DataFrame()

        df = self._read_csv_with_fallback()
        if df.empty:
            self.logger.error("El CSV produjo un DataFrame vacío.")
            return pd.DataFrame()

        self.logger.info(
            f"CSV leído | filas_raw={len(df)} | "
            f"columnas={df.columns.tolist()}"
        )

        df = self._apply_column_mapping(df)

        if "fecha_taller" in df.columns:
            df["fecha_taller"] = normalize_fecha_taller(
                df["fecha_taller"], self.logger
            )
        else:
            self.logger.warning(
                "Columna 'fecha_taller' ausente tras el mapeo. "
                "Verificar que FECHA_TALLER existe en el CSV y está "
                "definida en config/mappings.py bajo 'asistencia'."
            )

        if "nombre_asistente" in df.columns:
            df["nombre_asistente"] = (
                df["nombre_asistente"]
                .astype(str)
                .str.strip()
                .replace({"": None, "nan": None})
            )

        df = self._add_source_metadata(df)

        filas_antes = len(df)
        dedup_cols = [
            c for c in ["taller_entry_id", "email", "fecha_taller"]
            if c in df.columns
        ]

        if len(dedup_cols) == 3:
            email_norm = (
                df["email"].astype(str).str.strip().str.lower()
                .replace({"nan": None})
            )
            df = df.copy()
            df["_email_dedup"] = email_norm
            df = df.drop_duplicates(
                subset=["taller_entry_id", "_email_dedup", "fecha_taller"],
                keep="first",
            ).drop(columns=["_email_dedup"])
        elif len(dedup_cols) == 2:
            self.logger.warning(
                "Deduplicando por (taller_entry_id, email) únicamente — "
                "fecha_taller no disponible. Asistencias a distintas fechas "
                "del mismo ciclo podrían colapsarse."
            )
            df = df.drop_duplicates(subset=dedup_cols, keep="first")
        else:
            self.logger.warning(
                f"Columnas insuficientes para deduplicar ({dedup_cols}). "
                f"Se conservan todas las filas."
            )

        duplicados_eliminados = filas_antes - len(df)

        n_emails_validos = (
            df["email"].astype(str).str.strip()
            .str.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
            .sum()
            if "email" in df.columns else 0
        )
        n_sin_email     = len(df) - n_emails_validos
        n_talleres      = df["taller_entry_id"].nunique() if "taller_entry_id" in df.columns else 0
        n_fechas        = df["fecha_taller"].dropna().nunique() if "fecha_taller" in df.columns else 0
        n_emails_unicos = (
            df["email"].astype(str).str.strip().str.lower().nunique()
            if "email" in df.columns else 0
        )
        n_sin_nombre    = (
            df["nombre_asistente"].isna().sum()
            if "nombre_asistente" in df.columns else 0
        )

        self.logger.info(
            f"Extracción completada | "
            f"filas_raw={filas_antes} | "
            f"duplicados_eliminados={duplicados_eliminados} | "
            f"filas_finales={len(df)} | "
            f"talleres_unicos={n_talleres} | "
            f"fechas_unicas={n_fechas} | "
            f"emails_unicos={n_emails_unicos} | "
            f"emails_sin_formato_valido={n_sin_email} | "
            f"sin_nombre={n_sin_nombre}"
        )

        self._df = df
        return df
"""
Módulo base para los extractores de datos.

Define la clase abstracta `BaseExtractor` que sirve como contrato
y proporciona funcionalidad común para todos los extractores de fuentes de datos.
"""
import abc
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

from config import settings
from config import mappings
from scripts.utils import get_logger


class BaseExtractor(abc.ABC):
    """
    Clase base abstracta para los extractores de datos.

    Cada extractor para una fuente de datos específica debe heredar de esta clase
    e implementar el método abstracto `extract`.
    """

    def __init__(self, source_name: str, file_path: Path):
        """
        Inicializa el extractor.

        Args:
            source_name: El nombre de la fuente (debe ser una clave en `mappings.COLUMN_MAPPING`).
            file_path: La ruta al archivo CSV de origen.
        """
        self.source_name: str = source_name
        self.file_path: Path = file_path
        self.logger: logging.Logger = get_logger(f"extractor.{self.source_name}")
        self._raw_df: pd.DataFrame = pd.DataFrame()
        self._df: pd.DataFrame = pd.DataFrame()

    def validate_file(self) -> bool:
        """
        Verifica que el archivo exista y no esté vacío.

        Returns:
            True si el archivo es válido, False en caso contrario.
        """
        if not self.file_path.exists():
            self.logger.error(f"El archivo no existe: {self.file_path}")
            return False
        if self.file_path.stat().st_size == 0:
            self.logger.error(f"El archivo está vacío: {self.file_path}")
            return False
        self.logger.info(f"Archivo validado exitosamente: {self.file_path}")
        return True

    def _detect_delimiter(self) -> str:
        """
        Intenta detectar el delimitador del CSV leyendo las primeras líneas.

        Returns:
            El delimitador detectado. Por defecto, ','.
        """
        try:
            with open(self.file_path, "r", encoding=settings.ENCODING_PRIMARY) as f:
                sample = "".join([next(f) for _ in range(5)])
        except (UnicodeDecodeError, StopIteration):
            sample = ""

        counts = {delim: sample.count(delim) for delim in settings.CSV_DELIMITERS}
        
        if counts and max(counts.values()) > 0:
            delimiter = max(counts, key=counts.get)
            self.logger.info(f"Delimitador detectado: '{delimiter}'")
            return delimiter

        self.logger.warning("No se pudo detectar el delimitador. Usando ',' por defecto.")
        return ","

    def _read_csv_with_fallback(self) -> pd.DataFrame:
        """
        Lee el archivo CSV, intentando con un encoding primario y luego con uno de fallback.

        Returns:
            Un DataFrame de pandas con los datos del archivo.
        """
        delimiter = self._detect_delimiter()
        try:
            df = pd.read_csv(self.file_path, encoding=settings.ENCODING_PRIMARY, sep=delimiter)
            self.logger.info(f"Archivo leído con encoding primario '{settings.ENCODING_PRIMARY}'.")
        except UnicodeDecodeError:
            self.logger.warning(
                f"Falló la lectura con '{settings.ENCODING_PRIMARY}'. "
                f"Reintentando con fallback '{settings.ENCODING_FALLBACK}'."
            )
            try:
                df = pd.read_csv(self.file_path, encoding=settings.ENCODING_FALLBACK, sep=delimiter)
                self.logger.info(f"Archivo leído con encoding de fallback '{settings.ENCODING_FALLBACK}'.")
            except Exception as e:
                self.logger.critical(f"No se pudo leer el archivo CSV ni con el encoding de fallback: {e}")
                return pd.DataFrame()
        except Exception as e:
            self.logger.critical(f"Error inesperado al leer el archivo CSV: {e}")
            return pd.DataFrame()

        # Limpieza crítica de nombres de columnas
        df.columns = df.columns.str.strip()
        return df

    def _apply_column_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aplica el mapeo de columnas definido en `config/mappings.py`.

        Args:
            df: El DataFrame al que se le aplicará el mapeo.

        Returns:
            El DataFrame con las columnas renombradas.
        """
        mapping = mappings.COLUMN_MAPPING.get(self.source_name, {})
        if not mapping:
            self.logger.error(f"No se encontró mapeo de columnas para la fuente '{self.source_name}'.")
            return df

        # Columnas que se esperan según el mapping
        expected_cols = set(mapping.keys())
        # Columnas que realmente existen en el DataFrame
        actual_cols = set(df.columns)

        # Columnas esperadas que no se encontraron en el archivo
        missing_cols = expected_cols - actual_cols
        if missing_cols:
            self.logger.warning(f"Columnas esperadas no encontradas: {sorted(list(missing_cols))}")

        # Columnas en el archivo que no están en el mapping
        extra_cols = actual_cols - expected_cols
        if extra_cols:
            self.logger.info(f"Columnas extra encontradas (no se renombrarán): {sorted(list(extra_cols))}")

        # Renombrar solo las columnas que existen en el DataFrame
        rename_dict = {k: v for k, v in mapping.items() if k in actual_cols}
        df = df.rename(columns=rename_dict)
        self.logger.info(f"Mapeo de columnas aplicado. {len(rename_dict)} columnas renombradas.")
        return df

    def _add_source_metadata(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Añade columnas de metadatos para trazabilidad.

        Args:
            df: El DataFrame al que se le añadirán los metadatos.

        Returns:
            El DataFrame con las columnas de metadatos.
        """
        df["_source_name"] = self.source_name
        df["_source_file"] = self.file_path.name
        df["_extracted_at"] = datetime.now(timezone.utc).isoformat()
        return df

    def get_raw_dataframe(self) -> pd.DataFrame:
        """Retorna el DataFrame crudo antes de cualquier transformación."""
        return self._raw_df.copy()

    def get_shape_info(self) -> dict:
        """
        Retorna un diccionario con información sobre la forma y contenido del DataFrame.
        """
        if self._df.empty:
            return {
                "source": self.source_name,
                "rows": 0,
                "columns": 0,
                "columns_list": [],
                "has_email_column": False,
                "null_email_count": 0,
                "file_size_kb": 0,
            }
        
        has_email = "email" in self._df.columns
        return {
            "source": self.source_name,
            "rows": len(self._df),
            "columns": len(self._df.columns),
            "columns_list": self._df.columns.tolist(),
            "has_email_column": has_email,
            "null_email_count": self._df["email"].isnull().sum() if has_email else 0,
            "file_size_kb": round(self.file_path.stat().st_size / 1024, 2),
        }

    @abc.abstractmethod
    def extract(self) -> pd.DataFrame:
        """
        Orquesta el proceso de extracción.

        Este método debe ser implementado por cada subclase para definir el flujo
        de extracción específico de la fuente.
        """
        raise NotImplementedError

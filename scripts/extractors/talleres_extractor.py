"""
Extractor para la fuente de datos 'Talleres'.
"""
import pandas as pd

from config import settings
from scripts.extractors.base_extractor import BaseExtractor


class TalleresExtractor(BaseExtractor):
    """
    Extractor para los datos de inscripción a talleres.
    """

    def __init__(self):
        """Inicializa el extractor para la fuente 'talleres'."""
        super().__init__(
            source_name="talleres",
            file_path=settings.RAW_FILES["talleres"]
        )

    def extract(self) -> pd.DataFrame:
        """
        Orquesta el proceso de extracción para los datos de talleres.

        Flujo:
        1. Valida la existencia del archivo.
        2. Lee el CSV.
        3. Aplica el mapeo de columnas.
        4. Realiza conversiones de tipo básicas.
        5. Añade una columna calculada 'taller_count_entry'.
        6. Añade metadatos de trazabilidad.
        7. Loggea un resumen del proceso.

        Returns:
            Un DataFrame con los datos extraídos y estandarizados.
        """
        self.logger.info("Iniciando extracción para la fuente 'talleres'.")

        if not self.validate_file():
            return pd.DataFrame()

        df = self._read_csv_with_fallback()
        if df.empty:
            return pd.DataFrame()
        
        self._raw_df = df.copy()

        df = self._apply_column_mapping(df)

        # Conversión de tipos
        df["fecha_inscripcion"] = pd.to_datetime(df["fecha_inscripcion"], errors="coerce")

        # Añadir columna calculada
        df["taller_count_entry"] = 1
        self.logger.debug("Columna calculada 'taller_count_entry' añadida.")

        df = self._add_source_metadata(df)

        self._df = df

        # Logging de resumen
        self.logger.info(f"Extracción completada. Total filas: {len(self._df)}.")
        if "taller_titulo" in self._df.columns:
            self.logger.info(f"Talleres únicos encontrados: {self._df['taller_titulo'].nunique()}.")
        if "formulario_status" in self._df.columns:
            self.logger.info(f"Distribución de status de formularios:\n{self._df['formulario_status'].value_counts().to_string()}")

        return self._df.copy()

    def get_talleres_summary(self) -> dict:
        """
        Retorna un diccionario con el conteo de inscripciones por título de taller.

        Requiere que el método `extract()` haya sido llamado previamente.

        Returns:
            Un diccionario con el resumen de talleres.
        """
        if self._df.empty:
            self.logger.warning("El método 'extract()' debe ser llamado antes de 'get_talleres_summary()'.")
            return {}
        
        if "taller_titulo" in self._df.columns:
            return self._df["taller_titulo"].value_counts().to_dict()
        
        self.logger.warning("La columna 'taller_titulo' no se encontró en el DataFrame.")
        return {}

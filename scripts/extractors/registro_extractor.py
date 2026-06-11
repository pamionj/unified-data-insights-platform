"""
Extractor para la fuente de datos 'Registro RCV'.
"""
import pandas as pd

from config import settings
from scripts.extractors.base_extractor import BaseExtractor


class RegistroExtractor(BaseExtractor):
    """
    Extractor para los datos de registro de la comunidad (RCV).
    """

    def __init__(self):
        """Inicializa el extractor para la fuente 'registro'."""
        super().__init__(
            source_name="registro",
            file_path=settings.RAW_FILES["registro"]
        )

    def extract(self) -> pd.DataFrame:
        """
        Orquesta el proceso de extracción para los datos de registro.

        Flujo:
        1. Valida la existencia del archivo.
        2. Lee el CSV con manejo de encoding y delimitadores.
        3. Aplica el mapeo de columnas estándar.
        4. Realiza conversiones de tipo básicas y no destructivas.
        5. Añade metadatos de trazabilidad.
        6. Loggea un resumen del proceso.

        Returns:
            Un DataFrame con los datos extraídos y estandarizados, o un
            DataFrame vacío si ocurre un error crítico.
        """
        self.logger.info("Iniciando extracción para la fuente 'registro'.")

        if not self.validate_file():
            return pd.DataFrame()

        df = self._read_csv_with_fallback()
        if df.empty:
            self.logger.error("La lectura del archivo resultó en un DataFrame vacío.")
            return pd.DataFrame()
        
        self._raw_df = df.copy()

        df = self._apply_column_mapping(df)

        # Conversión de tipos básica y no destructiva
        self.logger.debug("Aplicando conversiones de tipo...")
        df["fecha_creacion"] = pd.to_datetime(df["fecha_creacion"], errors="coerce")
        df["fecha_nacimiento"] = pd.to_datetime(df["fecha_nacimiento"], errors="coerce")
        df["cuantas_personas_viven"] = pd.to_numeric(df["cuantas_personas_viven"], errors="coerce")
        self.logger.debug("Conversiones de tipo finalizadas.")

        df = self._add_source_metadata(df)

        self._df = df
        
        # Logging de resumen
        shape_info = self.get_shape_info()
        self.logger.info(f"Extracción completada. Total filas: {shape_info['rows']}.")
        self.logger.info(f"Columnas presentes: {shape_info['columns']}.")
        if shape_info['has_email_column']:
            self.logger.info(f"Filas con email nulo: {shape_info['null_email_count']}.")

        return self._df.copy()

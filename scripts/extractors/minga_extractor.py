"""
Extractor para la fuente de datos 'Chatbot Minga'.
"""
import pandas as pd

from config import settings
from scripts.extractors.base_extractor import BaseExtractor


class MingaExtractor(BaseExtractor):
    """
    Extractor para los datos de conversaciones del chatbot Minga.
    """

    def __init__(self):
        """Inicializa el extractor para la fuente 'minga'."""
        super().__init__(
            source_name="minga",
            file_path=settings.RAW_FILES["minga"]
        )

    def extract(self) -> pd.DataFrame:
        """
        Orquesta el proceso de extracción para los datos de Minga.

        Flujo:
        1. Valida la existencia del archivo.
        2. Lee el CSV.
        3. Aplica el mapeo de columnas.
        4. Realiza conversiones de tipo básicas.
        5. Añade metadatos de trazabilidad.
        6. Loggea un resumen del proceso.

        Returns:
            Un DataFrame con los datos extraídos y estandarizados.
        """
        self.logger.info("Iniciando extracción para la fuente 'minga'.")

        if not self.validate_file():
            return pd.DataFrame()

        df = self._read_csv_with_fallback()
        if df.empty:
            return pd.DataFrame()
        
        self._raw_df = df.copy()

        df = self._apply_column_mapping(df)

        # Conversión de tipos
        df["fecha_conversacion"] = pd.to_datetime(df["fecha_conversacion"], errors="coerce")
        df["num_mensajes"] = pd.to_numeric(df["num_mensajes"], errors="coerce")
        df["edad_minga"] = pd.to_numeric(df["edad_minga"], errors="coerce")

        df = self._add_source_metadata(df)

        self._df = df

        # Logging de resumen
        total_rows = len(self._df)
        self.logger.info(f"Extracción completada. Total conversaciones: {total_rows}.")
        if "subsidio_recomendado" in self._df.columns:
            self.logger.info(f"Distribución de subsidios recomendados:\n{self._df['subsidio_recomendado'].value_counts().to_string()}")
        if "email" in self._df.columns:
            email_count = self._df["email"].notna().sum()
            email_percentage = (email_count / total_rows * 100) if total_rows > 0 else 0
            self.logger.info(f"Emails presentes: {email_count}/{total_rows} ({email_percentage:.2f}%).")

        return self._df.copy()

    def get_subsidio_distribution(self) -> dict:
        """
        Retorna un diccionario con el conteo de subsidios recomendados.

        Requiere que el método `extract()` haya sido llamado previamente.

        Returns:
            Un diccionario con la distribución de subsidios.
        """
        if self._df.empty:
            self.logger.warning("El método 'extract()' debe ser llamado antes de 'get_subsidio_distribution()'.")
            return {}
        
        if "subsidio_recomendado" in self._df.columns:
            return self._df["subsidio_recomendado"].value_counts().to_dict()
        
        self.logger.warning("La columna 'subsidio_recomendado' no se encontró en el DataFrame.")
        return {}

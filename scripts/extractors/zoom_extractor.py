"""
Extractor para la fuente de datos de asistencia de Zoom.

Este extractor contiene lógica especializada para manejar las complejidades
de los reportes de Zoom, incluyendo el parsing de nombres y la asignación
de una confianza de matching inicial.
"""
import re
import numpy as np
import pandas as pd
from unidecode import unidecode

from config import settings
from scripts.extractors.base_extractor import BaseExtractor


class ZoomExtractor(BaseExtractor):
    """
    Extractor para los datos de asistencia a reuniones de Zoom.
    """

    def __init__(self):
        """Inicializa el extractor para la fuente 'zoom'."""
        super().__init__(
            source_name="zoom",
            file_path=settings.RAW_FILES["zoom"]
        )

    def _split_nombre_completo(self, nombre_completo: str) -> tuple[str | None, str | None]:
        """
        Divide un nombre completo en (nombre, apellido) usando una heurística simple.

        Limitación: Considera la primera palabra como nombre y el resto como apellido.
        Esto puede ser impreciso para nombres compuestos.

        Args:
            nombre_completo: La cadena de texto con el nombre completo.

        Returns:
            Una tupla conteniendo el nombre y el apellido.
        """
        if not nombre_completo or not isinstance(nombre_completo, str):
            return (None, None)

        parts = nombre_completo.strip().split()
        if not parts:
            return (None, None)

        if len(parts) == 1:
            self.logger.debug(f"Nombre con una sola parte encontrado: '{parts[0]}'. Apellido será None.")
            return (parts[0], None)

        nombre = parts[0]
        apellido = " ".join(parts[1:])
        return (nombre, apellido)

    def _build_nombre_key(self, nombre: str | None, apellido: str | None) -> str | None:
        """
        Genera una clave normalizada a partir de un nombre y apellido.

        La clave se usa para matching secundario cuando el email no está disponible.

        Args:
            nombre: El nombre.
            apellido: El apellido.

        Returns:
            La clave normalizada en formato snake_case, o None si no se puede construir.
        """
        if not nombre:
            return None

        full_name = f"{nombre} {apellido}" if apellido else nombre
        
        # Eliminar tildes y caracteres especiales
        s = unidecode(full_name)
        # Convertir a minúsculas
        s = s.lower().strip()
        # Eliminar cualquier caracter que no sea letra, número o espacio
        s = re.sub(r"[^a-z0-9\s]", "", s)
        # Colapsar espacios múltiples y unir con guion bajo
        key = "_".join(s.split())
        
        return key if key else None

    def _assign_initial_confidence(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Asigna un nivel de confianza de matching inicial a cada registro.

        Args:
            df: El DataFrame al que se le añadirá la columna 'match_confidence'.

        Returns:
            El DataFrame con la nueva columna.
        """
        conditions = [
            df["email"].str.contains("@", na=False),
            df["nombre_key"].notna(),
        ]
        choices = ["HIGH", "LOW"]
        
        df["match_confidence"] = np.select(conditions, choices, default="UNMATCHED")
        
        self.logger.info("Asignación de confianza inicial completada.")
        self.logger.info(f"Distribución de confianza:\n{df['match_confidence'].value_counts().to_string()}")
        
        return df

    def extract(self) -> pd.DataFrame:
        """
        Orquesta el proceso de extracción para los datos de Zoom.

        Flujo:
        1. Valida y lee el archivo CSV.
        2. Aplica el mapeo de columnas.
        3. Divide la columna 'nombre_zoom' en 'nombre' y 'apellido'.
        4. Construye la clave 'nombre_key' para matching.
        5. Realiza conversiones de tipo básicas.
        6. Asigna una confianza de matching inicial.
        7. Añade metadatos de trazabilidad.
        8. Loggea un resumen y retorna el DataFrame.

        Returns:
            Un DataFrame con los datos de Zoom extraídos y enriquecidos.
        """
        self.logger.info("Iniciando extracción para la fuente 'zoom'.")

        if not self.validate_file():
            return pd.DataFrame()

        df = self._read_csv_with_fallback()
        if df.empty:
            return pd.DataFrame()
        
        self._raw_df = df.copy()

        df = self._apply_column_mapping(df)

        # 4. Aplicar split de nombre
        nombres_apellidos = df["nombre_zoom"].apply(self._split_nombre_completo)
        df[["nombre", "apellido"]] = pd.DataFrame(nombres_apellidos.tolist(), index=df.index)
        self.logger.debug("Columna 'nombre_zoom' dividida en 'nombre' y 'apellido'.")

        # 5. Construir nombre_key
        df["nombre_key"] = df.apply(lambda row: self._build_nombre_key(row["nombre"], row["apellido"]), axis=1)
        self.logger.debug("Columna 'nombre_key' construida.")

        # 6. Conversión de tipos
        df["duracion_minutos"] = pd.to_numeric(df["duracion_minutos"], errors="coerce")
        # El parseo de tiempo es opcional y no crítico, lo dejamos como string por ahora.
        # df["hora_entrada"] = pd.to_datetime(df["hora_entrada"], format="%H:%M:%S", errors="coerce").dt.time
        # df["hora_salida"] = pd.to_datetime(df["hora_salida"], format="%H:%M:%S", errors="coerce").dt.time

        # 7. Asignar confianza
        df = self._assign_initial_confidence(df)

        # 8. Añadir metadatos
        df = self._add_source_metadata(df)

        self._df = df

        # 9. Logging de resumen
        self.logger.info(f"Extracción completada. Total filas: {len(self._df)}.")
        self.logger.info(f"Filas con apellido None (solo nombre): {self._df['apellido'].isnull().sum()}.")
        self.logger.info(f"Filas sin email: {self._df['email'].isnull().sum() + (self._df['email'] == '').sum()}.")
        if "duracion_minutos" in self._df.columns:
            avg_duration = self._df["duracion_minutos"].mean()
            self.logger.info(f"Duración promedio de asistencia: {avg_duration:.2f} minutos.")

        return self._df.copy()

    def get_unmatched_records(self) -> pd.DataFrame:
        """
        Retorna los registros que no pudieron ser asociados ni por email ni por nombre.
        """
        if self._df.empty:
            self.logger.warning("El método 'extract()' debe ser llamado antes de 'get_unmatched_records()'.")
            return pd.DataFrame()
        return self._df[self._df["match_confidence"] == "UNMATCHED"].copy()

    def get_confidence_summary(self) -> dict:
        """
        Retorna un diccionario con el conteo de niveles de confianza de matching.
        """
        if self._df.empty:
            self.logger.warning("El método 'extract()' debe ser llamado antes de 'get_confidence_summary()'.")
            return {}
        return self._df["match_confidence"].value_counts().to_dict()

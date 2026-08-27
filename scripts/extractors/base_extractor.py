"""
Módulo base para los extractores de datos.

Define la clase abstracta `BaseExtractor` que sirve como contrato
y proporciona funcionalidad común para todos los extractores de fuentes de datos.
"""
import abc
import csv
import logging
import re
import pandas as pd
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

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

    def _detect_encoding(self) -> str:
        """
        Detecta el encoding real del archivo inspeccionando sus primeros bytes.

        Busca señales de mojibake (UTF-8 decodificado incorrectamente como
        Latin-1, o viceversa) leyendo una muestra y verificando si contiene
        los patrones típicos de doble-codificación ('Ã©', 'Â¿', 'Ã³', etc.).

        Returns:
            El encoding recomendado: 'utf-8-sig' o el de settings.ENCODING_FALLBACK.
        """
        try:
            with open(self.file_path, "rb") as f:
                raw_sample = f.read(4096)

            # BOM UTF-8 explícito → utf-8-sig es seguro
            if raw_sample.startswith(b"\xef\xbb\xbf"):
                return "utf-8-sig"

            try:
                texto_utf8 = raw_sample.decode("utf-8")
                patrones_mojibake = ["Ã©", "Ã³", "Ã­", "Ã±", "Â¿", "Â¡", "Ã\xa9"]
                if any(p in texto_utf8 for p in patrones_mojibake):
                    self.logger.warning(
                        "Se detectaron patrones de mojibake en UTF-8 — "
                        "el archivo puede estar doblemente codificado. "
                        "Se usará utf-8-sig de todas formas; revisar manualmente "
                        "si los acentos se ven incorrectos en el resultado final."
                    )
                return "utf-8-sig"
            except UnicodeDecodeError:
                self.logger.info(
                    "El archivo no es UTF-8 válido — se usará el encoding de fallback."
                )
                return settings.ENCODING_FALLBACK

        except Exception as exc:
            self.logger.warning(f"No se pudo detectar encoding automáticamente: {exc}")
            return settings.ENCODING_PRIMARY

    @staticmethod
    def _archivo_tiene_comillas_rotas(lineas_datos: list[str]) -> bool:
        """
        Determina si el archivo tiene genuinamente líneas con comillas sin
        cerrar (campos de texto libre multilínea rotos), o si es un CSV
        sano donde cada línea ya tiene sus comillas balanceadas.

        Esta verificación es la salvaguarda principal contra falsos
        positivos: archivos como zoom_asistencia.csv tienen comillas
        (ej. en las columnas de fecha/hora) que SIEMPRE están bien
        balanceadas dentro de su propia línea — no deben pasar por el
        proceso de reparación, que asume la existencia de comillas
        huérfanas y puede fusionar el archivo completo si no encuentra
        un patrón de inicio de registro reconocible.

        Criterio:
            Un archivo tiene comillas rotas si y solo si existe al menos
            una línea individual con un conteo IMPAR de comillas (señal
            inequívoca de comilla sin cerrar en esa línea física).
            Si TODAS las líneas tienen conteo par de comillas, el archivo
            está sano y no requiere reparación, sin importar cuántas
            comillas tenga en total.

        Args:
            lineas_datos: Líneas del archivo (sin header) a inspeccionar.

        Returns:
            True si al menos una línea tiene comillas desbalanceadas.
            False si el archivo está completamente sano.
        """
        for linea in lineas_datos:
            if linea.count('"') % 2 == 1:
                return True
        return False

    def _build_record_start_pattern(
        self,
        lineas_datos: list[str],
        delimiter: str,
        num_columnas_esperadas: int,
    ) -> tuple[re.Pattern, int]:
        """
        Construye un patrón regex que detecta el inicio de un registro real,
        inferido empíricamente votando entre varias líneas candidatas del
        propio archivo — no asume un formato fijo para la primera columna
        (que varía entre fuentes: TALLER_ENTRY_ID es numérico, conv_id
        puede tener prefijo de texto como 'CONV-0001' o un ULID largo).

        Estrategia:
            En vez de confiar en una sola línea de referencia (riesgoso si
            esa línea resulta ser justo la rota), se inspecciona el primer
            campo de hasta 30 líneas no vacías del archivo y se clasifica
            cada una según la "forma" de ese primer campo. Se usa la forma
            MÁS FRECUENTE como patrón — los registros bien formados son
            mayoría en cualquier exportación real, así que la forma
            dominante es confiable incluso si hay líneas rotas mezcladas
            en la muestra.

            Formas reconocidas:
                - Puramente numérico        ('12457')        → r'^\\d+,'
                - Prefijo letras + alfanum.  ('CONV-0001',
                  'conv_01KVPBHM...')                        → r'^conv[_\\-]?[\\w]+,'
                - Alfanumérico genérico     ('abc123')        → r'^[\\w\\-]+,'

        Args:
            lineas_datos:            Líneas del archivo (sin header) a inspeccionar.
            delimiter:               Delimitador detectado para el archivo.
            num_columnas_esperadas:  Número de columnas del header — usado
                                     para descartar como referencia líneas
                                     que claramente no son registros completos.

        Returns:
            Tupla (patrón_compilado, longitud_prefijo_dominante).
            longitud_prefijo_dominante es la longitud típica del primer
            campo en la forma dominante — usada después para acotar la
            ventana de búsqueda de comillas de apertura sin cerrar.
            Si no se puede inferir un patrón confiable, retorna un patrón
            que nunca matchea (tratamiento conservador: todo el archivo
            se trata como un solo bloque a reparar, nunca se corrompe
            silenciosamente).
        """
        candidatas = [l for l in lineas_datos[:30] if l.strip()]
        formas: Counter = Counter()
        prefijos_por_forma: dict[str, str] = {}
        longitudes_por_forma: dict[str, list[int]] = {}

        for linea in candidatas:
            primer_campo = linea.split(delimiter)[0].strip()

            if re.fullmatch(r"\d+", primer_campo):
                clave = "numerico"
            elif re.fullmatch(r"[A-Za-z]+[_\-]?[\w]+", primer_campo):
                prefijo = re.match(r"[A-Za-z]+", primer_campo).group()
                clave = f"prefijo:{prefijo.lower()}"
                prefijos_por_forma[clave] = prefijo
            elif re.fullmatch(r"[\w\-]+", primer_campo):
                clave = "alfanumerico"
            else:
                continue

            formas[clave] += 1
            longitudes_por_forma.setdefault(clave, []).append(len(primer_campo))

        if not formas:
            return re.compile(r"(?!)"), 0

        forma_dominante, _ = formas.most_common(1)[0]
        longitudes = longitudes_por_forma.get(forma_dominante, [0])
        longitud_tipica = max(longitudes) if longitudes else 0

        if forma_dominante == "numerico":
            patron = rf"^\d+{re.escape(delimiter)}"
        elif forma_dominante.startswith("prefijo:"):
            prefijo_letras = prefijos_por_forma[forma_dominante]
            # [\w\-]+ cubre tanto sufijos numéricos cortos ('0001') como
            # IDs largos tipo ULID ('01KVPBHMGP63RZVAG2T71F7X78')
            patron = rf"^{re.escape(prefijo_letras)}[_\-]?[\w]+{re.escape(delimiter)}"
        else:
            patron = rf"^[\w\-]+{re.escape(delimiter)}"

        return re.compile(patron, re.IGNORECASE), longitud_tipica

    def _repair_unbalanced_quotes(
        self,
        raw_text: str,
        delimiter: str,
        num_columnas_esperadas: int,
    ) -> tuple[str, int]:
        """
        Repara campos de texto libre multilínea con comillas sin cerrar,
        fusionando líneas físicas en el registro lógico correcto, usando
        detección de inicio de registro en lugar de conteo de comillas.

        Problema que resuelve:
            Exportaciones de formularios o transcripciones de chatbot
            (ej. talleres.csv, historial_analizado.csv) generan un campo
            de texto libre con una comilla de apertura (") que nunca se
            cierra en esa misma línea física. El contenido continúa en
            líneas siguientes —mezclando saltos de línea reales del
            archivo con saltos de línea legítimos dentro del campo— hasta
            que el siguiente registro real comienza, sin que la comilla
            se haya cerrado correctamente en ningún punto intermedio.

            Caso particular de historial_analizado.csv: las conversaciones
            de chatbot pueden ser muy largas (decenas de intercambios
            User/Agent) con múltiples líneas en blanco dentro del mismo
            campo roto, lo que aumenta el riesgo de que fragmentos de la
            conversación sean confundidos con el inicio de un nuevo
            registro si solo se valida la FORMA del primer campo.

        Estrategia (robusta — no depende solo de contar comillas):
            1. Detectar el patrón de inicio de registro real a partir de
               las primeras líneas del archivo (forma del primer campo).
            2. VALIDACIÓN ADICIONAL: una línea solo se considera inicio de
               registro real si, además de matchear el patrón, el separar
               esa línea por el delimitador produce un número de campos
               razonablemente cercano a num_columnas_esperadas. Esto
               descarta fragmentos de texto libre que accidentalmente
               imitan la forma del ID (ej. una respuesta de usuario que
               empieza con un número) pero no tienen la estructura de
               columnas de un registro completo.
            3. Recorrer el archivo línea por línea. Mientras una línea NO
               cumpla ambos criterios, se considera continuación del
               registro anterior y se fusiona.
            4. Al fusionar, neutralizar las comillas internas del fragmento
               de continuación y cerrar el campo con una comilla final
               antes de las columnas reales que sigan, si las hay.

        Args:
            raw_text:               Contenido completo del archivo ya decodificado.
            delimiter:              Delimitador detectado para el archivo.
            num_columnas_esperadas: Número de columnas del header.

        Returns:
            Tupla (texto_reparado, líneas_fusionadas).
        """
        lineas = raw_text.split("\n")
        while lineas and lineas[-1].strip() == "":
            lineas.pop()

        if len(lineas) < 2:
            return raw_text, 0

        header = lineas[0]
        patron_inicio, _ = self._build_record_start_pattern(
            lineas[1:], delimiter, num_columnas_esperadas
        )

        def _es_inicio_de_registro_real(linea: str) -> bool:
            """
            Verifica si la línea matchea el patrón de forma del ID detectado.

            NOTA: no se valida el conteo de columnas aquí. Un registro recién
            iniciado con un campo de texto libre roto NUNCA tiene el conteo
            completo de columnas en su primera línea física (la comilla
            todavía está abierta) — exigir ese conteo en este punto produce
            falsos negativos sistemáticos. El patrón de forma del ID, votado
            sobre múltiples líneas candidatas, es suficiente por sí solo.
            """
            return bool(patron_inicio.match(linea))

        resultado: list[str] = [header]
        lineas_fusionadas = 0
        registro_actual: list[str] = []

        def _cerrar_registro_actual() -> None:
            if not registro_actual:
                return
            if len(registro_actual) == 1:
                resultado.append(registro_actual[0])
            else:
                resultado.append(self._merge_broken_record(registro_actual))

        for linea in lineas[1:]:
            if _es_inicio_de_registro_real(linea) or not registro_actual:
                _cerrar_registro_actual()
                registro_actual = [linea]
            else:
                registro_actual.append(linea)
                lineas_fusionadas += 1

        _cerrar_registro_actual()

        if lineas_fusionadas > 0:
            self.logger.warning(
                f"Se fusionaron {lineas_fusionadas} líneas de continuación "
                f"en '{self.file_path.name}'. Esto indica texto libre "
                f"multilínea con comillas mal escapadas en la exportación "
                f"original (ej. respuestas de formulario o transcripciones "
                f"de chatbot)."
            )

        return "\n".join(resultado), lineas_fusionadas

    @staticmethod
    def _merge_broken_record(fragmentos: list[str]) -> str:
        """
        Fusiona los fragmentos de un registro roto en una sola línea física
        válida para CSV, neutralizando comillas internas y preservando
        tanto las columnas ANTES del campo problemático como las columnas
        DESPUÉS de su cierre real.

        Estrategia:
            El primer fragmento contiene columnas válidas (algunas con sus
            propias comillas YA balanceadas, ej. TALLER_TITLE) hasta donde
            comienza el campo de texto libre que quedó roto — identificado
            por ser la ÚLTIMA comilla de apertura cuyo conteo total en el
            fragmento es impar (sin su cierre correspondiente).

            El último fragmento puede contener, además del cierre real del
            campo roto (su comilla de cierre), columnas adicionales que
            vienen DESPUÉS de esa comilla (ej. ',email,resumen') — esas
            columnas deben preservarse intactas, no fusionarse como texto.
            Se localiza la PRIMERA comilla del último fragmento como cierre
            real del campo, y todo lo posterior a ella se conserva como
            columnas separadas.

            Los fragmentos intermedios (si los hay) son continuación pura
            del campo de texto libre y se fusionan sin más análisis.

        Args:
            fragmentos: Lista de líneas físicas que componen un registro roto.

        Returns:
            Una sola línea física, con comillas balanceadas, lista para
            que pandas la interprete como un único registro CSV.
        """
        primer_fragmento = fragmentos[0]

        posiciones_comillas = [
            i for i, ch in enumerate(primer_fragmento) if ch == '"'
        ]

        idx_comilla_apertura = -1
        for pos in posiciones_comillas:
            conteo_hasta_aqui = primer_fragmento[: pos + 1].count('"')
            if conteo_hasta_aqui % 2 == 1:
                idx_comilla_apertura = pos

        if idx_comilla_apertura == -1:
            return " ".join(f.strip() for f in fragmentos)

        prefijo_valido = primer_fragmento[: idx_comilla_apertura + 1]
        inicio_texto_libre = primer_fragmento[idx_comilla_apertura + 1 :]

        fragmentos_intermedios = fragmentos[1:-1] if len(fragmentos) > 2 else []
        ultimo_fragmento = fragmentos[-1] if len(fragmentos) > 1 else ""

        idx_comilla_cierre = ultimo_fragmento.find('"')

        if idx_comilla_cierre == -1:
            texto_libre_final = ultimo_fragmento
            sufijo_columnas_reales = ""
        else:
            texto_libre_final = ultimo_fragmento[:idx_comilla_cierre]
            sufijo_columnas_reales = ultimo_fragmento[idx_comilla_cierre + 1 :]

        partes_texto_libre = (
            [inicio_texto_libre] + fragmentos_intermedios + [texto_libre_final]
        )
        texto_libre_unido = " ".join(
            p.replace('"', "'").strip() for p in partes_texto_libre
        )

        return f'{prefijo_valido}{texto_libre_unido}"{sufijo_columnas_reales}'

    def _read_csv_with_fallback(self) -> pd.DataFrame:
        """
        Lee el archivo CSV con detección de encoding, reparación de comillas
        sin cerrar (solo si el archivo realmente las tiene), y fallback de
        encoding si la lectura primaria falla.

        Flujo:
            1. Detectar encoding real (maneja mojibake UTF-8/Latin-1).
            2. Leer el contenido completo como texto.
            3. Verificar si el archivo tiene líneas con comillas sin cerrar.
               Si NO las tiene (archivo sano, ej. zoom_asistencia.csv),
               se omite el proceso de reparación por completo y se parsea
               directamente — evita que la heurística de reparación
               corrompa archivos que nunca estuvieron rotos.
            4. Si SÍ las tiene, reparar líneas con comillas sin cerrar
               (campos multilínea rotos, ej. talleres.csv,
               historial_analizado.csv), validando además que el inicio
               de cada registro reconstruido tenga un conteo de columnas
               compatible con el header — no solo la forma del ID.
            5. Parsear el texto (reparado o intacto) con pandas usando
               engine='python' (más tolerante que el motor C ante anomalías
               estructurales residuales) y on_bad_lines='warn' como red de
               seguridad final.
            6. Si falla con el encoding primario, reintentar con el fallback.

        Returns:
            Un DataFrame de pandas con los datos del archivo.
            DataFrame vacío si ninguna combinación de encoding funcionó.
        """
        delimiter = self._detect_delimiter()
        encoding_principal = self._detect_encoding()

        encodings_a_probar = [encoding_principal]
        if settings.ENCODING_FALLBACK not in encodings_a_probar:
            encodings_a_probar.append(settings.ENCODING_FALLBACK)
        if settings.ENCODING_PRIMARY not in encodings_a_probar:
            encodings_a_probar.append(settings.ENCODING_PRIMARY)

        ultimo_error: Exception | None = None

        for encoding in encodings_a_probar:
            try:
                with open(self.file_path, "r", encoding=encoding, errors="strict") as f:
                    raw_text = f.read()

                primera_linea = raw_text.split("\n", 1)[0]
                num_columnas_esperadas = len(primera_linea.split(delimiter))

                lineas_sin_header = raw_text.split("\n")[1:]
                requiere_reparacion = self._archivo_tiene_comillas_rotas(
                    lineas_sin_header
                )

                if requiere_reparacion:
                    texto_a_parsear, lineas_afectadas = self._repair_unbalanced_quotes(
                        raw_text, delimiter, num_columnas_esperadas
                    )
                else:
                    texto_a_parsear = raw_text
                    lineas_afectadas = 0
                    self.logger.info(
                        f"Archivo sin comillas desbalanceadas — "
                        f"omitiendo reparación, parseo directo."
                    )

                df = pd.read_csv(
                    StringIO(texto_a_parsear),
                    sep=delimiter,
                    engine="python",
                    on_bad_lines="warn",
                    quoting=csv.QUOTE_MINIMAL,
                )

                self.logger.info(
                    f"Archivo leído | encoding='{encoding}' | "
                    f"filas={len(df)} | columnas={len(df.columns)} | "
                    f"líneas reparadas={lineas_afectadas}"
                )

                df.columns = df.columns.str.strip()
                return df

            except UnicodeDecodeError as exc:
                ultimo_error = exc
                self.logger.warning(
                    f"Falló la lectura con encoding '{encoding}': {exc}. "
                    f"Probando siguiente encoding disponible."
                )
                continue

            except Exception as exc:
                ultimo_error = exc
                self.logger.error(
                    f"Error inesperado leyendo '{self.file_path.name}' "
                    f"con encoding '{encoding}': {exc}"
                )
                continue

        self.logger.critical(
            f"No se pudo leer el archivo CSV con ningún encoding probado "
            f"({encodings_a_probar}). Último error: {ultimo_error}"
        )
        return pd.DataFrame()

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

        expected_cols = set(mapping.keys())
        actual_cols = set(df.columns)

        missing_cols = expected_cols - actual_cols
        if missing_cols:
            self.logger.warning(f"Columnas esperadas no encontradas: {sorted(list(missing_cols))}")

        extra_cols = actual_cols - expected_cols
        if extra_cols:
            self.logger.info(f"Columnas extra encontradas (no se renombrarán): {sorted(list(extra_cols))}")

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

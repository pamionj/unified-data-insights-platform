"""
Configuración centralizada del proyecto ETL.

Este módulo define todas las constantes, rutas de archivos y parámetros
utilizados a lo largo del pipeline de datos.
"""
from pathlib import Path
from typing import Dict, List

# --- Rutas del Proyecto ---
# En desarrollo settings.py vive en <raiz>/config/. En el Release los modulos
# ofuscados viven en <raiz>/obfuscated/config/. En ambos casos la raiz real es
# la primera carpeta que contiene data/ (database/ y logs/ se crean en runtime,
# por eso no pueden usarse como criterio). Esta deteccion es robusta ante
# cambios en los nombres de directorio de ambos entornos.
def _find_project_root(start: Path) -> Path:
    current = start
    while current != current.parent:
        if (current / "data").is_dir():
            return current
        current = current.parent
    return start.parent


PROJECT_ROOT: Path = _find_project_root(Path(__file__).resolve().parent)

DATA_DIR: Path = PROJECT_ROOT / "data"
DATA_RAW_DIR: Path = DATA_DIR / "raw"
DATA_PROCESSED_DIR: Path = DATA_DIR / "processed"
DATABASE_DIR: Path = PROJECT_ROOT / "database"
LOGS_DIR: Path = PROJECT_ROOT / "logs"
SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"

# --- Archivos de Datos ---
RAW_FILES: Dict[str, Path] = {
    "registro": DATA_RAW_DIR / "registro_rcv.csv",
    "talleres": DATA_RAW_DIR / "talleres.csv",
    "minga": DATA_RAW_DIR / "historial_analizado.csv",
    "asistencia": DATA_RAW_DIR / "consolidado_asistencia.csv",
}

DB_PATH: Path = DATABASE_DIR / "deficit_cero.db"
MASTER_CSV_PATH: Path = DATA_PROCESSED_DIR / "usuarios_master.csv"

# --- Configuración de Logging ---
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# --- Configuración de ETL ---
ENCODING_PRIMARY: str = "utf-8-sig"
ENCODING_FALLBACK: str = "latin-1"
CSV_DELIMITERS: List[str] = [",", ";", "|", "\t"]

ETL_VERSION: str = "1.1.0"
PROJECT_NAME: str = "Déficit Cero — Community Data Pipeline"

# --- Nombres de Columnas Especiales ---
# Columnas que pueden requerir un manejo especial debido a espacios o caracteres.
RISKY_COLUMN_NAMES: List[str] = [
    "PASO 2 COMPLETO",
    "PROVEEDOR REGISTRO",
    "Nombre (nombre original)",
    "Duración (minutos)",
    "Respuesta al descargo de responsabilidad relativa a la grabación",
    "PREGUNTAS - RESPUESTAS",
    "Correo electrónico",
    "Hora de entrada",
    "Hora de salida",
    "En sala de espera",
]

# ── Creación de Directorios ─────────────────────────────────────────────────────
# NOTA: Los directorios se crean explícitamente mediante la función
# ensure_directories() en scripts/utils.py, llamada desde main().
# Se evita la ejecución en import para compatibilidad con Nuitka (compilación).

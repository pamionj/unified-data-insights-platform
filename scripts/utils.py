"""
Utilidades transversales para el pipeline de datos.

Este módulo proporciona funciones de ayuda para logging, profiling,
manejo de archivos y formateo de datos.
"""
import logging
import time
import re
import functools
from logging.handlers import RotatingFileHandler
from typing import Callable, Any

# Se importa de esta manera para evitar dependencias circulares
# y facilitar el acceso a las constantes de configuración.
from config import settings


def get_logger(name: str) -> logging.Logger:
    """
    Configura y retorna un logger con handlers para archivo y consola.

    El logger se configura para rotar archivos de log cuando alcanzan
    un tamaño máximo, manteniendo un historial de logs antiguos.

    Args:
        name: El nombre del logger, usualmente __name__ del módulo que lo llama.

    Returns:
        Una instancia de logging.Logger configurada.
    """
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    logger.setLevel(settings.LOG_LEVEL)
    formatter = logging.Formatter(settings.LOG_FORMAT, settings.LOG_DATE_FORMAT)

    # Handler para escribir en consola
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Handler para escribir en archivo con rotación
    log_file_name = f"etl_{time.strftime('%Y%m%d')}.log"
    log_file_path = settings.LOGS_DIR / log_file_name
    
    # 5MB por archivo, manteniendo 5 archivos de backup
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Evita que los logs se propaguen al logger raíz
    logger.propagate = False

    return logger


# Logger específico para este módulo de utilidades
_utils_logger = get_logger(__name__)


def timer(func: Callable) -> Callable:
    """
    Decorador que mide y loggea el tiempo de ejecución de una función.

    Args:
        func: La función a la que se le medirá el tiempo.

    Returns:
        La función envuelta (wrapper) que incluye la medición de tiempo.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Función interna del decorador."""
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        _utils_logger.info(
            f"Función '{func.__name__}' ejecutada en {execution_time:.4f}s"
        )
        return result
    return wrapper


@timer
def ensure_directories() -> None:
    """
    Verifica la existencia de los directorios clave del proyecto y los crea si no existen.

    Utiliza las rutas definidas en el módulo de settings.
    """
    _utils_logger.info("Verificando estructura de directorios...")
    dirs_to_check = [
        settings.DATA_DIR,
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATABASE_DIR,
        settings.LOGS_DIR,
        settings.SCRIPTS_DIR,
    ]
    for dir_path in dirs_to_check:
        if not dir_path.exists():
            _utils_logger.info(f"Creando directorio: {dir_path}")
            dir_path.mkdir(parents=True, exist_ok=True)
        else:
            _utils_logger.debug(f"Directorio ya existe: {dir_path}")
    _utils_logger.info("Estructura de directorios verificada.")


def format_number(n: int | float, decimals: int = 0) -> str:
    """
    Formatea un número con separador de miles de punto y decimales opcionales.

    Args:
        n: El número (entero o flotante) a formatear.
        decimals: El número de decimales a mostrar.

    Returns:
        El número formateado como una cadena de texto.
    
    Ejemplo:
        >>> format_number(1234567.89, decimals=1)
        '1.234.568,9' # El formato chileno usa coma para decimales
    """
    # El formato español usa punto para miles y coma para decimales.
    # Python locale no es siempre confiable, así que lo hacemos manual.
    try:
        if decimals > 0:
            return f"{n:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{n:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return str(n)


def snake_case(text: str) -> str:
    """
    Convierte una cadena de texto a formato snake_case.

    Maneja espacios, guiones, puntos, mayúsculas y otros caracteres no alfanuméricos.

    Args:
        text: La cadena de texto a convertir.

    Returns:
        La cadena convertida a snake_case.

    Ejemplo:
        >>> snake_case("Nombre (nombre original)")
        'nombre_nombre_original'
    """
    if not isinstance(text, str):
        return ""
    # Reemplaza caracteres no alfanuméricos por un espacio
    s = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    # Inserta un espacio antes de las mayúsculas (camelCase a snake_case)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    # Convierte a minúsculas, divide por espacios y une con guiones bajos
    return "_".join(s.lower().split())

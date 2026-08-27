"""
load.py — Capa de persistencia del pipeline ETL.

Responsabilidades:
    1. Crear y mantener la base de datos SQLite (database/deficit_cero.db)
    2. Cargar la tabla usuarios_master (DELETE + INSERT, idempotente)
    3. Cargar la tabla talleres_asistencias con el histórico de asistencia
    4. Guardar el CSV consolidado (data/processed/usuarios_master.csv)
    5. Registrar métricas de cada run en la tabla etl_runs

Tablas gestionadas:
    usuarios_master      — un registro por usuario (email o nombre_key)
    talleres_asistencias — un registro por asistencia única (taller × email × fecha)
    etl_runs             — auditoría de cada ejecución del pipeline

Fuente de asistencia:
    consolidado_asistencia.csv (reemplaza a zoom_asistencia.csv desde v1.1.0).
    Representa el histórico completo de asistencia a talleres desde 2023,
    incluyendo talleres presenciales, virtuales y otras modalidades.

Esta capa NO modifica ningún archivo en data/raw/.
Esta capa NO ejecuta lógica de transformación ni consolidación.

Proyecto: Déficit Cero — Community Data Pipeline
Versión: 1.1.0
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import DB_PATH, MASTER_CSV_PATH
from scripts.consolidate import ConsolidateResult
from scripts.utils import get_logger


# ── DDL — usuarios_master (v2) ────────────────────────────────────────────────
# Esquema con flags inscrito_taller / asistio_taller,
# conteos de asistencia, tasa_asistencia y match_confidence.

_DDL_USUARIOS_MASTER = """
CREATE TABLE IF NOT EXISTS usuarios_master (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identificación y confianza del cruce
    email                    TEXT,
    match_confidence         TEXT    DEFAULT 'HIGH'
                                     CHECK(match_confidence IN
                                           ('HIGH', 'LOW', 'UNMATCHED')),
    nombre_key               TEXT,
    member_id_rcv            TEXT,

    -- Datos personales
    nombre                   TEXT,
    apellido                 TEXT,
    genero                   TEXT,
    fecha_nacimiento         TEXT,
    whatsapp                 TEXT,
    nacionalidad             TEXT,

    -- Territorialidad
    region                   TEXT,
    comuna                   TEXT,

    -- Situación habitacional (fuente: registro)
    situacion_habitacional   TEXT,
    pertenece_comite         INTEGER,
    cuantas_personas_viven   INTEGER,
    estado_registro          TEXT,

    -- Perfil financiero (fuente: minga)
    subsidio_recomendado     TEXT,
    rsh                      TEXT,
    tiene_propiedad          INTEGER,
    tiene_subsidio           INTEGER,
    ingresos                 TEXT,
    ahorro                   TEXT,

    -- Flags de participación por fuente
    tiene_registro_web       INTEGER DEFAULT 0,
    inscrito_taller          INTEGER DEFAULT 0,
    asistio_taller           INTEGER DEFAULT 0,
    uso_minga                INTEGER DEFAULT 0,

    -- Conteos de actividad
    num_talleres_inscritos   INTEGER DEFAULT 0,
    num_talleres_asistidos   INTEGER DEFAULT 0,
    num_conversaciones_minga INTEGER DEFAULT 0,
    tasa_asistencia          REAL,

    -- Metadatos de consolidación
    fuentes                  TEXT,
    fecha_primer_registro    TEXT,
    fecha_etl                TEXT
);
"""

# ── DDL — talleres_asistencias ────────────────────────────────────────────────
# Tabla de detalle: un registro por asistencia única (taller × email × fecha).
# Reemplaza a zoom_asistencias (que guardaba metadatos de sesión Zoom como
# hora_entrada, hora_salida, duración — columnas que no existen en la nueva
# fuente consolidado_asistencia.csv).

_DDL_TALLERES_ASISTENCIAS = """
CREATE TABLE IF NOT EXISTS talleres_asistencias (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identificación del participante
    email            TEXT,
    nombre_asistente TEXT,
    nombre_key       TEXT,

    -- Datos del taller
    taller_entry_id  TEXT,
    taller_titulo    TEXT,
    fecha_taller     TEXT,

    -- Metadatos de cruce y auditoría
    match_confidence TEXT DEFAULT 'HIGH'
                          CHECK(match_confidence IN ('HIGH', 'LOW', 'UNMATCHED')),
    archivo_origen   TEXT,
    fecha_etl        TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# ── DDL — etl_runs ────────────────────────────────────────────────────────────
# NOTA: La columna se llama rows_asistencia_detalle (renombrada desde
# rows_zoom_detalle en v1.1.0). Para bases de datos existentes ejecutar:
#   ALTER TABLE etl_runs RENAME COLUMN rows_zoom_detalle TO rows_asistencia_detalle;

_DDL_ETL_RUNS = """
CREATE TABLE IF NOT EXISTS etl_runs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at                   TEXT    DEFAULT CURRENT_TIMESTAMP,
    total_usuarios           INTEGER,
    usuarios_registro        INTEGER,
    usuarios_inscritos       INTEGER,
    usuarios_asistidos       INTEGER,
    usuarios_minga           INTEGER,
    rows_asistencia_detalle  INTEGER,
    low_confidence           INTEGER,
    unmatched                INTEGER,
    duracion_segundos        REAL,
    warnings_count           INTEGER,
    estado                   TEXT CHECK(estado IN ('ok', 'error', 'warning'))
);
"""

# ── DDL — índices ─────────────────────────────────────────────────────────────

_DDL_INDEXES: list[str] = [
    # usuarios_master
    "CREATE INDEX IF NOT EXISTS idx_um_email        ON usuarios_master(email);",
    "CREATE INDEX IF NOT EXISTS idx_um_region       ON usuarios_master(region);",
    "CREATE INDEX IF NOT EXISTS idx_um_comuna       ON usuarios_master(comuna);",
    "CREATE INDEX IF NOT EXISTS idx_um_confidence   ON usuarios_master(match_confidence);",
    "CREATE INDEX IF NOT EXISTS idx_um_nombre_key   ON usuarios_master(nombre_key);",
    # talleres_asistencias
    "CREATE INDEX IF NOT EXISTS idx_ta_email        ON talleres_asistencias(email);",
    "CREATE INDEX IF NOT EXISTS idx_ta_nombre_key   ON talleres_asistencias(nombre_key);",
    "CREATE INDEX IF NOT EXISTS idx_ta_taller_id    ON talleres_asistencias(taller_entry_id);",
    "CREATE INDEX IF NOT EXISTS idx_ta_confidence   ON talleres_asistencias(match_confidence);",
]

# ── Columnas a escribir en cada tabla ─────────────────────────────────────────

_UM_COLUMNS: list[str] = [
    "email", "match_confidence", "nombre_key", "member_id_rcv",
    "nombre", "apellido", "genero", "fecha_nacimiento",
    "whatsapp", "nacionalidad", "region", "comuna",
    "situacion_habitacional", "pertenece_comite", "cuantas_personas_viven",
    "estado_registro", "subsidio_recomendado", "rsh",
    "tiene_propiedad", "tiene_subsidio", "ingresos", "ahorro",
    "tiene_registro_web", "inscrito_taller", "asistio_taller", "uso_minga",
    "num_talleres_inscritos", "num_talleres_asistidos",
    "num_conversaciones_minga", "tasa_asistencia",
    "fuentes", "fecha_primer_registro", "fecha_etl",
]

_TA_COLUMNS: list[str] = [
    "email", "nombre_asistente", "nombre_key",
    "taller_entry_id", "taller_titulo", "fecha_taller",
    "match_confidence", "archivo_origen",
]


# ── Clase de resultado ────────────────────────────────────────────────────────

@dataclass
class LoadResult:
    """
    Resultado completo de la capa de persistencia.

    Atributos:
        db_path:                  Ruta a la base de datos SQLite.
        csv_path:                 Ruta al CSV consolidado exportado.
        rows_written_master:      Filas insertadas en usuarios_master.
        rows_written_asistencia:  Filas insertadas en talleres_asistencias.
        rows_written_csv:         Filas escritas en el CSV.
        run_id:                   ID del registro en etl_runs (None si falló).
        duration_seconds:         Duración total de la operación en segundos.
        warnings:                 Advertencias generadas durante la carga.
        success:                  True si todas las operaciones completaron sin error.
    """

    db_path: Path
    csv_path: Path
    rows_written_master: int
    rows_written_asistencia: int
    rows_written_csv: int
    run_id: Optional[int]
    duration_seconds: float
    warnings: list[str]
    success: bool


# ── Funciones privadas ────────────────────────────────────────────────────────

def _ensure_database(db_path: Path, logger) -> sqlite3.Connection:
    """
    Crea la base de datos SQLite si no existe y garantiza que todas las
    tablas e índices estén presentes.

    Usa CREATE TABLE IF NOT EXISTS para ser idempotente: llamar múltiples
    veces no destruye datos existentes.

    NOTA DE MIGRACIÓN (v1.0.0 → v1.1.0):
        Si la base de datos fue creada con la versión anterior (zoom),
        ejecutar manualmente antes del primer run:
            DROP TABLE IF EXISTS zoom_asistencias;
            ALTER TABLE etl_runs RENAME COLUMN rows_zoom_detalle
                TO rows_asistencia_detalle;
        O bien eliminar el archivo .db para que se recree desde cero.

    Args:
        db_path: Ruta al archivo .db (se crea el directorio si no existe).
        logger:  Logger del módulo.

    Returns:
        Conexión SQLite configurada con WAL y foreign keys activos.

    Raises:
        sqlite3.Error: Si la conexión o el DDL fallan.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # WAL mejora la concurrencia en lecturas simultáneas del dashboard
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.execute(_DDL_USUARIOS_MASTER)
    conn.execute(_DDL_TALLERES_ASISTENCIAS)
    conn.execute(_DDL_ETL_RUNS)

    for idx_sql in _DDL_INDEXES:
        conn.execute(idx_sql)

    conn.commit()
    logger.info(f"Base de datos lista | ruta: {db_path}")
    return conn


def _prepare_for_sqlite(df: pd.DataFrame, logger) -> pd.DataFrame:
    """
    Convierte tipos pandas a tipos nativos compatibles con SQLite.

    Conversiones:
        bool / BooleanDtype  → int (0 / 1)
        datetime64           → string ISO 'YYYY-MM-DD HH:MM:SS'
        Int64 (nullable)     → int nativo o None
        float NaN / pd.NA    → None  (insertado como SQL NULL)

    Args:
        df:     DataFrame a convertir.
        logger: Logger del módulo.

    Returns:
        DataFrame con tipos Python nativos.
    """
    df = df.copy()

    for col in df.columns:
        dtype_str = str(df[col].dtype)

        if dtype_str == "bool":
            df[col] = df[col].astype(int)

        elif dtype_str == "boolean":
            df[col] = df[col].map(
                lambda v: int(v) if pd.notna(v) else None
            )

        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].apply(
                lambda v: v.strftime("%Y-%m-%d %H:%M:%S")
                if pd.notna(v) else None
            )

        elif dtype_str == "Int64":
            df[col] = df[col].apply(
                lambda v: int(v) if pd.notna(v) else None
            )

    # Reemplazar NaN / pd.NA restantes con None → NULL en SQLite
    df = df.where(pd.notna(df), other=None)

    logger.debug(f"Tipos preparados para SQLite | columnas: {len(df.columns)}")
    return df


def _load_usuarios_master(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    logger,
) -> int:
    """
    Carga el DataFrame en usuarios_master usando la estrategia
    DELETE + INSERT para garantizar idempotencia en cada run.

    Por qué DELETE + INSERT en lugar de UPSERT:
        Los registros UNMATCHED tienen email=NULL. SQLite permite múltiples
        NULLs en una columna UNIQUE, por lo que un UPSERT no detectaría
        conflictos entre runs y acumularía duplicados. El DELETE limpio
        previene esto sin lógica adicional.

    Args:
        conn:   Conexión SQLite activa.
        df:     DataFrame ya preparado por _prepare_for_sqlite().
        logger: Logger del módulo.

    Returns:
        Número de filas insertadas.
    """
    cols = [c for c in _UM_COLUMNS if c in df.columns]
    cols_faltantes = [c for c in _UM_COLUMNS if c not in df.columns]

    if cols_faltantes:
        logger.warning(
            f"Columnas de usuarios_master ausentes en DataFrame: "
            f"{cols_faltantes} — se insertarán como NULL"
        )

    placeholders = ", ".join(["?" for _ in cols])
    col_names    = ", ".join(cols)
    sql          = f"INSERT INTO usuarios_master ({col_names}) VALUES ({placeholders})"

    rows: list[tuple] = [
        tuple(row[c] if c in row.index else None for c in cols)
        for _, row in df.iterrows()
    ]

    with conn:
        conn.execute("DELETE FROM usuarios_master;")
        conn.executemany(sql, rows)

    n = int(conn.execute("SELECT COUNT(*) FROM usuarios_master;").fetchone()[0])
    logger.info(f"usuarios_master | filas insertadas: {n}")
    return n


def _load_talleres_asistencias(
    conn: sqlite3.Connection,
    df_asistencia: pd.DataFrame,
    logger,
) -> int:
    """
    Carga el DataFrame de asistencia en la tabla talleres_asistencias.

    Guarda el detalle histórico de asistencia: un registro por asistencia
    única (taller × email × fecha). Permite auditar quién asistió a qué
    taller y cuándo, a lo largo de toda la historia desde 2023.

    La columna 'archivo_origen' se toma de '_source_file' del DataFrame
    (metadato añadido por BaseExtractor), registrando de qué CSV proviene
    cada registro.

    Estrategia: DELETE + INSERT (mismo patrón que usuarios_master).

    Args:
        conn:           Conexión SQLite activa.
        df_asistencia:  DataFrame de asistencia transformado (salida de
                        AsistenciaTalleresExtractor + transform(), antes
                        de la agregación de consolidate()).
        logger:         Logger del módulo.

    Returns:
        Número de filas insertadas en talleres_asistencias.
    """
    if df_asistencia.empty:
        logger.warning(
            "talleres_asistencias: DataFrame de asistencia vacío — "
            "tabla no se cargará"
        )
        return 0

    df = df_asistencia.copy()

    # Mapear _source_file → archivo_origen (metadato de BaseExtractor)
    if "_source_file" in df.columns and "archivo_origen" not in df.columns:
        df["archivo_origen"] = df["_source_file"]

    # Preparar tipos para SQLite
    df = _prepare_for_sqlite(df, logger)

    cols = [c for c in _TA_COLUMNS if c in df.columns]
    cols_faltantes = [c for c in _TA_COLUMNS if c not in df.columns]

    if cols_faltantes:
        logger.info(
            f"Columnas opcionales de talleres_asistencias no presentes: "
            f"{cols_faltantes}"
        )

    placeholders = ", ".join(["?" for _ in cols])
    col_names    = ", ".join(cols)
    sql          = (
        f"INSERT INTO talleres_asistencias ({col_names}) VALUES ({placeholders})"
    )

    rows: list[tuple] = [
        tuple(row[c] if c in row.index else None for c in cols)
        for _, row in df.iterrows()
    ]

    with conn:
        conn.execute("DELETE FROM talleres_asistencias;")
        conn.executemany(sql, rows)

    n = int(
        conn.execute("SELECT COUNT(*) FROM talleres_asistencias;").fetchone()[0]
    )
    logger.info(f"talleres_asistencias | filas insertadas: {n}")
    return n


def _save_csv(
    df: pd.DataFrame,
    csv_path: Path,
    logger,
) -> int:
    """
    Guarda el DataFrame maestro como CSV en data/processed/.

    Usa encoding utf-8-sig (compatible con Excel en español) y separador
    coma. Crea el directorio si no existe.

    IMPORTANTE: Solo escribe en data/processed/. Nunca toca data/raw/.

    Args:
        df:       DataFrame a exportar.
        csv_path: Ruta destino (configurada en settings.py).
        logger:   Logger del módulo.

    Returns:
        Número de filas escritas.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    n_rows  = len(df)
    size_kb = csv_path.stat().st_size / 1024
    logger.info(
        f"CSV exportado | ruta: {csv_path.name} | "
        f"filas: {n_rows} | tamaño: {size_kb:.1f} KB"
    )
    return n_rows


def _record_etl_run(
    conn: sqlite3.Connection,
    result: ConsolidateResult,
    rows_asistencia: int,
    duration: float,
    estado: str,
    logger,
) -> Optional[int]:
    """
    Registra las métricas del run actual en la tabla etl_runs.

    Cada ejecución deja un registro auditable con totales, distribución
    por fuente, filas de detalle de asistencia, duración y estado.

    Args:
        conn:             Conexión SQLite activa.
        result:           ConsolidateResult con métricas de la consolidación.
        rows_asistencia:  Filas insertadas en talleres_asistencias.
        duration:         Duración de la carga en segundos.
        estado:           'ok' | 'warning' | 'error'
        logger:           Logger del módulo.

    Returns:
        ID del registro insertado, o None si falló.
    """
    sql = """
        INSERT INTO etl_runs (
            total_usuarios, usuarios_registro, usuarios_inscritos,
            usuarios_asistidos, usuarios_minga, rows_asistencia_detalle,
            low_confidence, unmatched,
            duracion_segundos, warnings_count, estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        result.total_usuarios,
        result.usuarios_registro,
        result.usuarios_inscritos_taller,
        result.usuarios_asistieron_taller,
        result.usuarios_minga,
        rows_asistencia,
        result.low_confidence_matches,
        result.unmatched_records,
        round(duration, 3),
        len(result.warnings),
        estado,
    )

    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        run_id = cursor.lastrowid
        logger.info(
            f"etl_runs registrado | id: {run_id} | estado: {estado}"
        )
        return run_id
    except sqlite3.Error as exc:
        logger.error(f"Error al registrar en etl_runs: {exc}")
        return None


# ── Función pública principal ─────────────────────────────────────────────────

def load(
    consolidate_result: ConsolidateResult,
    asistencia_df: Optional[pd.DataFrame] = None,
    db_path: Path = DB_PATH,
    csv_path: Path = MASTER_CSV_PATH,
) -> LoadResult:
    """
    Función principal de la capa de persistencia.

    Persiste el resultado de la consolidación en tres destinos:
        1. usuarios_master en SQLite (tabla maestra, DELETE + INSERT)
        2. talleres_asistencias en SQLite (detalle histórico de asistencia)
        3. CSV consolidado en data/processed/

    Y registra las métricas del run en etl_runs.

    La carga es idempotente: ejecutar load() dos veces con los mismos
    datos produce exactamente el mismo resultado sin duplicados.

    Args:
        consolidate_result: Resultado de consolidate() con el DataFrame maestro.
        asistencia_df:      DataFrame de asistencia transformado (salida de
                            AsistenciaTalleresExtractor + transform(), antes
                            de consolidate()). Si es None, talleres_asistencias
                            queda vacía.
        db_path:            Ruta a la base de datos SQLite (default: settings).
        csv_path:           Ruta al CSV de salida (default: settings).

    Returns:
        LoadResult con métricas de la operación.
        Nunca lanza excepciones al caller.
    """
    logger = get_logger("load")
    warnings: list[str] = list(consolidate_result.warnings)
    t_inicio = time.perf_counter()

    separador = "═" * 55
    logger.info(
        f"\n{separador}\n"
        f"  Load | registros: {consolidate_result.total_usuarios} | "
        f"asistencia_df: {'sí' if asistencia_df is not None else 'no'}\n"
        f"{separador}"
    )

    rows_master     = 0
    rows_asistencia = 0
    rows_csv        = 0
    run_id: Optional[int] = None
    conn: Optional[sqlite3.Connection] = None

    try:
        df_master = consolidate_result.df

        if df_master.empty:
            msg = "DataFrame maestro vacío — no hay datos que persistir"
            logger.warning(msg)
            warnings.append(msg)
            return LoadResult(
                db_path=db_path, csv_path=csv_path,
                rows_written_master=0, rows_written_asistencia=0,
                rows_written_csv=0, run_id=None,
                duration_seconds=0.0, warnings=warnings, success=False,
            )

        # 1 ── Crear / verificar base de datos
        conn = _ensure_database(db_path, logger)

        # 2 ── Preparar y cargar usuarios_master
        df_sql = _prepare_for_sqlite(df_master, logger)
        rows_master = _load_usuarios_master(conn, df_sql, logger)

        # 3 ── Cargar talleres_asistencias (si se proveyó el DataFrame)
        if asistencia_df is not None and not asistencia_df.empty:
            rows_asistencia = _load_talleres_asistencias(
                conn, asistencia_df, logger
            )
        else:
            logger.info(
                "talleres_asistencias: sin DataFrame de asistencia provisto "
                "— tabla vacía"
            )

        # 4 ── Exportar CSV
        rows_csv = _save_csv(df_master, csv_path, logger)

        # 5 ── Estado del run
        estado = "warning" if warnings else "ok"

        # 6 ── Registrar en etl_runs
        duracion = time.perf_counter() - t_inicio
        run_id = _record_etl_run(
            conn, consolidate_result, rows_asistencia, duracion, estado, logger
        )

        logger.info(
            f"Load completado | "
            f"master={rows_master} | "
            f"asistencia={rows_asistencia} | "
            f"csv={rows_csv} | "
            f"duración={duracion:.2f}s | estado={estado}"
        )

        return LoadResult(
            db_path=db_path,
            csv_path=csv_path,
            rows_written_master=rows_master,
            rows_written_asistencia=rows_asistencia,
            rows_written_csv=rows_csv,
            run_id=run_id,
            duration_seconds=round(duracion, 3),
            warnings=warnings,
            success=True,
        )

    except Exception as exc:
        duracion = time.perf_counter() - t_inicio
        logger.critical(
            f"Error inesperado en load() | error={exc}",
            exc_info=True,
        )
        if conn is not None:
            try:
                _record_etl_run(
                    conn, consolidate_result, rows_asistencia,
                    duracion, "error", logger,
                )
            except Exception:
                pass

        return LoadResult(
            db_path=db_path,
            csv_path=csv_path,
            rows_written_master=rows_master,
            rows_written_asistencia=rows_asistencia,
            rows_written_csv=rows_csv,
            run_id=run_id,
            duration_seconds=round(duracion, 3),
            warnings=warnings + [f"CRITICAL: {exc}"],
            success=False,
        )

    finally:
        if conn is not None:
            conn.close()
            logger.debug("Conexión SQLite cerrada")

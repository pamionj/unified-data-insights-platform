"""
main.py — Orquestador del pipeline ETL.

Punto de entrada único para ejecutar el pipeline completo o programado.

Modos de uso:
    python main.py                      # Ejecutar una vez y terminar
    python main.py --once               # Alias explícito del modo anterior
    python main.py --schedule 30        # Ejecutar cada 30 minutos (daemon)
    python main.py --schedule 60 --now  # Ejecutar ahora y luego cada 60 min

Flujo del pipeline:
    Extract (×4) → Transform (×4) → Consolidate → Load → Analytics

Fuentes de datos:
    registro    ← registro_rcv.csv         (RegistroExtractor)
    talleres    ← talleres.csv             (TalleresExtractor)
    minga       ← historial_analizado.csv  (MingaExtractor)
    asistencia  ← consolidado_asistencia.csv (AsistenciaTalleresExtractor)

    NOTA: La fuente "zoom" (zoom_asistencia.csv) fue reemplazada por
    "asistencia" (consolidado_asistencia.csv) en v1.1.0. El nuevo archivo
    representa el histórico completo de asistencia a talleres desde 2023,
    incluyendo talleres presenciales, virtuales y otras modalidades.

Project: Unified Data Insights Platform
Versión: 1.1.0
"""

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Optional

from config.settings import PROJECT_NAME, ETL_VERSION
from scripts.utils import get_logger, ensure_directories

# ── Imports globales para visibilidad de Nuitka ─────────────────────────────
# Nuitka resuelve dependencias estáticamente en tiempo de compilación.
# Los imports locales dentro de run_pipeline() impedían esa resolución.
# Ver: https://nuitka.net/doc/user-manual.html#use-of-hidden-imports
from scripts.extractors import (
    RegistroExtractor, TalleresExtractor, MingaExtractor,
)
from scripts.extractors.asistencia_talleres_extractor import (
    AsistenciaTalleresExtractor,
)
from scripts.transform   import transform
from scripts.consolidate import consolidate
from scripts.load        import load
from scripts.analytics   import compute_analytics
from scripts.scheduler   import run_scheduled


# ── Clase de resultado del pipeline ──────────────────────────────────────────

@dataclass
class PipelineResult:
    """
    Resultado completo de una ejecución del pipeline.

    Atributos:
        success:              True si todas las fases completaron sin error crítico.
        total_usuarios:       Total de usuarios en la tabla maestra.
        rows_master_db:       Filas escritas en usuarios_master (SQLite).
        rows_asistencia_db:   Filas escritas en talleres_asistencias (SQLite).
        rows_csv:             Filas escritas en el CSV consolidado.
        run_id:               ID del registro en etl_runs.
        duration_seconds:     Duración total del pipeline en segundos.
        warnings:             Lista de advertencias acumuladas de todas las fases.
        errors:               Lista de errores críticos (vacía si success=True).
        analytics_generated:  True si los KPIs se calcularon correctamente.
    """

    success: bool
    total_usuarios: int
    rows_master_db: int
    rows_asistencia_db: int
    rows_csv: int
    run_id: Optional[int]
    duration_seconds: float
    warnings: list[str]
    errors: list[str]
    analytics_generated: bool


# ── Pipeline principal ────────────────────────────────────────────────────────

def run_pipeline() -> PipelineResult:
    """
    Ejecuta el pipeline ETL completo de forma secuencial.

    Fases:
        1. Extract   — lee los 4 CSV desde data/raw/
        2. Transform — normaliza y limpia cada DataFrame
        3. Consolidate — une las 4 fuentes en usuarios_master
        4. Load      — persiste en SQLite y CSV
        5. Analytics — calcula KPIs (validación post-carga)

    Si una fase falla completamente (DataFrame vacío o excepción),
    el pipeline continúa con las fuentes disponibles en lugar de abortar.
    Los errores se acumulan en PipelineResult.errors.

    Returns:
        PipelineResult con métricas y estado de cada fase.
    """
    logger = get_logger("main")
    warnings: list[str] = []
    errors:   list[str] = []
    t_inicio = time.perf_counter()

    separador = "=" * 60
    logger.info(
        f"\n{separador}\n"
        f"  {PROJECT_NAME}\n"
        f"  Version: {ETL_VERSION}\n"
        f"  Iniciando pipeline ETL\n"
        f"{separador}"
    )

    # ── FASE 1 + 2: Extract & Transform ──────────────────────────────────────
    logger.info("--- FASE 1+2: Extract & Transform ---")

    fuentes_config = [
        ("registro",   RegistroExtractor),
        ("talleres",   TalleresExtractor),
        ("minga",      MingaExtractor),
        ("asistencia", AsistenciaTalleresExtractor),
    ]

    dataframes: dict = {}
    asistencia_df_transformed = None

    for source_name, ExtractorClass in fuentes_config:
        try:
            raw_df = ExtractorClass().extract()

            if raw_df.empty:
                msg = f"Extractor '{source_name}' retorno DataFrame vacio"
                logger.warning(msg)
                warnings.append(msg)
                continue

            t_result = transform(raw_df, source_name)
            warnings.extend(t_result.warnings)

            if t_result.df.empty:
                msg = (
                    f"Transform '{source_name}' retorno DataFrame vacio "
                    f"(quality_score={t_result.quality_score:.2%})"
                )
                logger.warning(msg)
                warnings.append(msg)
                continue

            dataframes[source_name] = t_result.df
            logger.info(
                f"  OK {source_name:<12} | "
                f"entrada={t_result.rows_input:>6} | "
                f"salida={t_result.rows_output:>6} | "
                f"quality={t_result.quality_score:.2%}"
            )

            # Guardar DataFrame de asistencia antes de la agregación en consolidate.
            # load() necesita el detalle granular (una fila por asistencia única)
            # para cargar talleres_asistencias — consolidate() lo agrega por email
            # y pierde ese nivel de detalle.
            if source_name == "asistencia":
                asistencia_df_transformed = t_result.df.copy()

        except Exception as exc:
            msg = (
                f"Error inesperado en extraccion/transformacion "
                f"de '{source_name}': {exc}"
            )
            logger.error(msg, exc_info=True)
            errors.append(msg)

    if not dataframes:
        msg = "Ninguna fuente produjo datos validos — abortando pipeline"
        logger.critical(msg)
        errors.append(msg)
        return PipelineResult(
            success=False,
            total_usuarios=0,
            rows_master_db=0,
            rows_asistencia_db=0,
            rows_csv=0,
            run_id=None,
            duration_seconds=round(time.perf_counter() - t_inicio, 3),
            warnings=warnings,
            errors=errors,
            analytics_generated=False,
        )

    # ── FASE 3: Consolidate ───────────────────────────────────────────────────
    logger.info("--- FASE 3: Consolidate ---")

    cons_result = None
    try:
        cons_result = consolidate(dataframes)
        warnings.extend(cons_result.warnings)

        if cons_result.df.empty:
            msg = "Consolidate retorno DataFrame vacio"
            logger.critical(msg)
            errors.append(msg)
            return PipelineResult(
                success=False,
                total_usuarios=0,
                rows_master_db=0,
                rows_asistencia_db=0,
                rows_csv=0,
                run_id=None,
                duration_seconds=round(time.perf_counter() - t_inicio, 3),
                warnings=warnings,
                errors=errors,
                analytics_generated=False,
            )

        logger.info(
            f"  OK Consolidacion completada | "
            f"total={cons_result.total_usuarios} | "
            f"registro={cons_result.usuarios_registro} | "
            f"inscritos={cons_result.usuarios_inscritos_taller} | "
            f"asistidos={cons_result.usuarios_asistieron_taller} | "
            f"minga={cons_result.usuarios_minga} | "
            f"LOW={cons_result.low_confidence_matches} | "
            f"UNMATCHED={cons_result.unmatched_records}"
        )

    except Exception as exc:
        msg = f"Error critico en consolidacion: {exc}"
        logger.critical(msg, exc_info=True)
        errors.append(msg)
        return PipelineResult(
            success=False,
            total_usuarios=0,
            rows_master_db=0,
            rows_asistencia_db=0,
            rows_csv=0,
            run_id=None,
            duration_seconds=round(time.perf_counter() - t_inicio, 3),
            warnings=warnings,
            errors=errors,
            analytics_generated=False,
        )

    # ── FASE 4: Load ──────────────────────────────────────────────────────────
    logger.info("--- FASE 4: Load ---")

    load_result = None
    try:
        load_result = load(
            cons_result,
            asistencia_df=asistencia_df_transformed,
        )
        warnings.extend(load_result.warnings)

        if not load_result.success:
            msg = f"Load completo con errores: {load_result.warnings}"
            logger.error(msg)
            errors.append(msg)

        logger.info(
            f"  OK Persistencia completada | "
            f"master={load_result.rows_written_master} | "
            f"asistencia={load_result.rows_written_asistencia} | "
            f"csv={load_result.rows_written_csv} | "
            f"run_id={load_result.run_id} | "
            f"duracion={load_result.duration_seconds:.2f}s"
        )

    except Exception as exc:
        msg = f"Error critico en carga: {exc}"
        logger.critical(msg, exc_info=True)
        errors.append(msg)
        load_result = None

    # ── FASE 5: Analytics (validación post-carga) ─────────────────────────────
    logger.info("--- FASE 5: Analytics ---")
    analytics_ok = False

    try:
        analytics = compute_analytics()
        analytics_ok = analytics.total_usuarios > 0

        if analytics_ok:
            logger.info(
                f"  OK KPIs calculados | "
                f"total={analytics.total_usuarios} | "
                f"regiones={analytics.regiones_unicas} | "
                f"comunas={analytics.comunas_unicas} | "
                f"fuente={analytics.data_source}"
            )
        else:
            msg = "Analytics no encontro datos en la DB tras la carga"
            logger.warning(msg)
            warnings.append(msg)

    except Exception as exc:
        msg = f"Error en calculo de analytics: {exc}"
        logger.error(msg, exc_info=True)
        errors.append(msg)

    # ── Resumen final ─────────────────────────────────────────────────────────
    duracion = round(time.perf_counter() - t_inicio, 3)
    success  = len(errors) == 0 and (load_result is not None and load_result.success)

    estado_str = "COMPLETADO" if success else "CON ERRORES"
    logger.info(
        f"\n{separador}\n"
        f"  Pipeline {estado_str}\n"
        f"  Duracion total: {duracion:.2f}s\n"
        f"  Usuarios procesados: {cons_result.total_usuarios}\n"
        f"  Warnings: {len(warnings)} | Errors: {len(errors)}\n"
        f"{separador}"
    )

    return PipelineResult(
        success=success,
        total_usuarios=cons_result.total_usuarios,
        rows_master_db=load_result.rows_written_master      if load_result else 0,
        rows_asistencia_db=load_result.rows_written_asistencia if load_result else 0,
        rows_csv=load_result.rows_written_csv               if load_result else 0,
        run_id=load_result.run_id                           if load_result else None,
        duration_seconds=duracion,
        warnings=warnings,
        errors=errors,
        analytics_generated=analytics_ok,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_arg_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            f"{PROJECT_NAME} v{ETL_VERSION}\n"
            "Pipeline ETL para consolidacion de datos de usuarios."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python main.py                  # Ejecutar una vez\n"
            "  python main.py --once           # Alias de lo anterior\n"
            "  python main.py --schedule 30    # Cada 30 minutos\n"
            "  python main.py --schedule 60 --now  # Ahora + cada 60 min"
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Ejecutar el pipeline una vez y terminar (comportamiento por defecto)",
    )
    parser.add_argument(
        "--schedule",
        type=int,
        metavar="MINUTOS",
        default=None,
        help="Ejecutar el pipeline cada N minutos en modo daemon",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        default=False,
        help=(
            "Con --schedule: ejecutar inmediatamente antes de iniciar "
            "el ciclo programado"
        ),
    )
    return parser


def _print_result_summary(result: PipelineResult) -> None:
    """
    Imprime un resumen visual del resultado en stdout.

    Usa caracteres ASCII puros para garantizar compatibilidad en terminales
    Windows con codificacion cp1252 o similares (sin soporte Unicode completo).
    """
    estado = "OK" if result.success else "ERROR"
    linea  = "-" * 50
    print(f"\n{linea}")
    print(f"  {PROJECT_NAME}")
    print(f"  Estado: {estado}")
    print(f"{linea}")
    print(f"  Usuarios en master:    {result.total_usuarios}")
    print(f"  Filas DB (master):     {result.rows_master_db}")
    print(f"  Filas DB (asistencia): {result.rows_asistencia_db}")
    print(f"  Filas CSV:             {result.rows_csv}")
    print(f"  Run ID (etl_runs):     {result.run_id}")
    print(f"  Duracion:              {result.duration_seconds:.2f}s")
    print(f"  Analytics generados:   {'Si' if result.analytics_generated else 'No'}")
    if result.warnings:
        print(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings[:5]:
            print(f"    WARN: {w[:80]}")
        if len(result.warnings) > 5:
            print(f"    ... y {len(result.warnings) - 5} mas (ver logs/)")
    if result.errors:
        print(f"  Errores ({len(result.errors)}):")
        for e in result.errors:
            print(f"    ERR: {e[:80]}")
    print(f"{linea}\n")


def main() -> int:
    """
    Punto de entrada principal del CLI.

    Returns:
        0 si el pipeline completo con exito, 1 si hubo errores.
    """
    # Garantizar UTF-8 en stdout/stderr al ejecutarse como subproceso en Windows.
    # errors='replace' evita UnicodeEncodeError si algun caracter no es soportado
    # por la codificacion del terminal (ej. cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ensure_directories()
    logger = get_logger("main")
    parser = _build_arg_parser()
    args   = parser.parse_args()

    # Modo: ejecutar una vez
    if args.schedule is None or args.once:
        result = run_pipeline()
        _print_result_summary(result)
        return 0 if result.success else 1

    # Modo: ejecucion programada
    run_scheduled(interval_minutes=args.schedule, run_now=args.now)
    return 0


if __name__ == "__main__":
    sys.exit(main())

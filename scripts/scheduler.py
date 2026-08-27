"""
scheduler.py — Automatización periódica del pipeline ETL.

Envuelve run_pipeline() con la librería schedule para ejecución
en intervalos configurables sin necesidad de cron externo.

Uso desde main.py:
    python main.py --schedule 30        # cada 30 minutos
    python main.py --schedule 60 --now  # ahora + cada 60 minutos

Uso directo (poco común, preferir main.py):
    python scripts/scheduler.py --interval 30

Proyecto: Déficit Cero — Community Data Pipeline
Versión: 1.1.0
"""

import signal
import sys
import time

import schedule

from scripts.utils import get_logger


# ── Estado del daemon ─────────────────────────────────────────────────────────

_running: bool = True   # Flag para el loop principal (permite parada limpia)


def _handle_signal(signum: int, frame) -> None:
    """
    Manejador de señales SIGINT (Ctrl+C) y SIGTERM.

    Activa la parada limpia del daemon en el próximo ciclo del loop.
    """
    global _running
    logger = get_logger("scheduler")
    logger.info(
        f"Señal {signum} recibida — deteniendo scheduler en el próximo ciclo"
    )
    _running = False


# ── Función de ejecución programada ──────────────────────────────────────────

def _scheduled_job() -> None:
    """
    Función que ejecuta el pipeline y loggea el resultado.
    Registrada como job en el scheduler de schedule.
    Nunca propaga excepciones para no romper el loop del daemon.
    """
    from main import run_pipeline   # import local para evitar circular

    logger = get_logger("scheduler")
    logger.info("Ejecutando pipeline programado...")

    try:
        result = run_pipeline()
        if result.success:
            logger.info(
                f"Pipeline programado completado | "
                f"usuarios={result.total_usuarios} | "
                f"duración={result.duration_seconds:.2f}s"
            )
        else:
            logger.error(
                f"Pipeline programado terminó con errores | "
                f"errors={result.errors}"
            )
    except Exception as exc:
        logger.critical(
            f"Excepción no capturada en pipeline programado: {exc}",
            exc_info=True,
        )


def run_scheduled(
    interval_minutes: int = 60,
    run_now: bool = False,
) -> None:
    """
    Inicia el daemon de ejecución periódica del pipeline ETL.

    Registra _scheduled_job() para ejecutarse cada interval_minutes
    minutos y entra en un loop bloqueante hasta recibir SIGINT o SIGTERM.

    Args:
        interval_minutes: Intervalo en minutos entre ejecuciones (default: 60).
        run_now:          Si True, ejecuta el pipeline inmediatamente antes
                          de iniciar el ciclo programado.
    """
    global _running
    _running = True

    logger = get_logger("scheduler")

    # Registrar manejadores de señales para parada limpia
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        f"Scheduler iniciado | "
        f"intervalo={interval_minutes} min | "
        f"run_now={run_now}"
    )
    print(
        f"\n  Scheduler activo — pipeline cada {interval_minutes} minuto(s)\n"
        f"  Presiona Ctrl+C para detener\n"
    )

    # Registrar el job en schedule
    schedule.every(interval_minutes).minutes.do(_scheduled_job)

    # Ejecución inmediata si se solicitó
    if run_now:
        logger.info("Ejecutando pipeline inicial (--now activado)")
        _scheduled_job()

    # Loop principal del daemon
    while _running:
        schedule.run_pending()
        time.sleep(1)

    # Limpieza al salir
    schedule.clear()
    logger.info("Scheduler detenido limpiamente")
    print("\n  Scheduler detenido.\n")

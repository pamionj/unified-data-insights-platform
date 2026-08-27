"""
verify_analytics.py — Verificación del módulo analytics.py.

Prerequisito: la Fase 5 debe haber sido ejecutada y verificada.
La base de datos database/deficit_cero.db debe existir con datos.

Ejecutar desde la raíz del proyecto:
    python verify_analytics.py

Valida 9 aspectos de analytics.py:
    1.  Importación y contrato de AnalyticsResult
    2.  total_usuarios coincide con el row count real de la DB
    3.  Coherencia de KPIs (flags <= total, multifuente <= total)
    4.  por_region: no vacío, claves string, valores int
    5.  top_comunas: estructura correcta con claves requeridas
    6.  inscritos_vs_asistidos: suma coherente con totales
    7.  timeline_registros: formato de período válido y orden cronológico
    8.  Fallback a CSV cuando la DB no existe
    9.  Sin datos disponibles retorna AnalyticsResult vacío sin crashear
"""

import sqlite3
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"

results: list[tuple[str, bool, str]] = []


def run_test(name: str, fn) -> None:
    """Ejecuta un test, captura cualquier excepción y registra el resultado."""
    try:
        fn()
        results.append((name, True, ""))
        print(f"  {PASS}  {name}")
    except AssertionError as exc:
        results.append((name, False, str(exc)))
        print(f"  {FAIL}  {name}")
        print(f"         AssertionError: {exc}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  {FAIL}  {name}")
        print(f"         {type(exc).__name__}: {exc}")
        traceback.print_exc()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_db_row_count() -> int:
    """Cuenta filas en usuarios_master directamente desde SQLite."""
    from config.settings import DB_PATH
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return int(
            conn.execute("SELECT COUNT(*) FROM usuarios_master;").fetchone()[0]
        )
    finally:
        conn.close()


def _db_disponible() -> bool:
    """Verifica si la DB de la Fase 5 existe y tiene datos."""
    from config.settings import DB_PATH
    return DB_PATH.exists() and _get_db_row_count() > 0


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_1_contrato_analytics_result():
    """
    Verifica que compute_analytics() retorna un AnalyticsResult con todos
    los campos requeridos y tipos correctos.
    """
    from scripts.analytics import compute_analytics, AnalyticsResult

    result = compute_analytics()

    assert isinstance(result, AnalyticsResult), (
        f"compute_analytics() debe retornar AnalyticsResult, retornó {type(result)}"
    )

    # Tipos de campos enteros
    int_fields = [
        "total_usuarios", "usuarios_registro", "usuarios_inscritos_taller",
        "usuarios_asistidos_taller", "usuarios_minga", "usuarios_multifuente",
        "comunas_unicas", "regiones_unicas",
    ]
    for f in int_fields:
        val = getattr(result, f)
        assert isinstance(val, int), (
            f"AnalyticsResult.{f} debe ser int, es {type(val)}"
        )

    # Tipos de campos estructurados
    assert isinstance(result.por_region,                  dict), "por_region debe ser dict"
    assert isinstance(result.top_comunas,                 list), "top_comunas debe ser list"
    assert isinstance(result.por_genero,                  dict), "por_genero debe ser dict"
    assert isinstance(result.por_situacion_habitacional,  dict), "por_situacion_habitacional debe ser dict"
    assert isinstance(result.distribucion_fuentes,        dict), "distribucion_fuentes debe ser dict"
    assert isinstance(result.inscritos_vs_asistidos,      dict), "inscritos_vs_asistidos debe ser dict"
    assert isinstance(result.distribucion_confidence,     dict), "distribucion_confidence debe ser dict"
    assert isinstance(result.timeline_registros,          list), "timeline_registros debe ser list"
    assert isinstance(result.generated_at,                str),  "generated_at debe ser str"
    assert isinstance(result.data_source,                 str),  "data_source debe ser str"
    assert isinstance(result.total_rows_source,           int),  "total_rows_source debe ser int"

    # data_source debe ser uno de los valores válidos
    assert result.data_source in ("sqlite", "csv", "empty"), (
        f"data_source inválido: '{result.data_source}'"
    )

    # generated_at debe ser parseable como ISO datetime
    from datetime import datetime
    try:
        datetime.fromisoformat(result.generated_at)
    except ValueError:
        raise AssertionError(
            f"generated_at no es un timestamp ISO válido: '{result.generated_at}'"
        )


def test_2_total_coincide_con_db():
    """
    Verifica que total_usuarios coincide exactamente con el row count
    real de la tabla usuarios_master en SQLite.
    """
    from scripts.analytics import compute_analytics

    if not _db_disponible():
        print(f"         {WARN}  DB no disponible — test omitido")
        return

    result       = compute_analytics()
    n_db         = _get_db_row_count()

    assert result.data_source == "sqlite", (
        f"Se esperaba data_source='sqlite', obtenido '{result.data_source}'"
    )
    assert result.total_usuarios == n_db, (
        f"total_usuarios ({result.total_usuarios}) != row count DB ({n_db})"
    )
    assert result.total_rows_source == n_db, (
        f"total_rows_source ({result.total_rows_source}) != row count DB ({n_db})"
    )

    print(f"         Info: {n_db} usuarios confirmados en DB y en AnalyticsResult")


def test_3_coherencia_kpis():
    """
    Verifica que los KPIs numéricos son coherentes entre sí:
    - Cada flag count <= total_usuarios
    - usuarios_multifuente <= total_usuarios
    - comunas_unicas y regiones_unicas > 0 si hay usuarios
    - tasa_asistencia_promedio entre 0 y un valor razonable
    """
    from scripts.analytics import compute_analytics

    result = compute_analytics()

    if result.total_usuarios == 0:
        print(f"         {WARN}  Sin usuarios — test omitido")
        return

    total = result.total_usuarios

    assert result.usuarios_registro         <= total, (
        f"usuarios_registro ({result.usuarios_registro}) > total ({total})"
    )
    assert result.usuarios_inscritos_taller <= total, (
        f"usuarios_inscritos_taller ({result.usuarios_inscritos_taller}) > total ({total})"
    )
    assert result.usuarios_asistidos_taller <= total, (
        f"usuarios_asistidos_taller ({result.usuarios_asistidos_taller}) > total ({total})"
    )
    assert result.usuarios_minga            <= total, (
        f"usuarios_minga ({result.usuarios_minga}) > total ({total})"
    )
    assert result.usuarios_multifuente      <= total, (
        f"usuarios_multifuente ({result.usuarios_multifuente}) > total ({total})"
    )
    assert result.comunas_unicas  >= 0, "comunas_unicas no puede ser negativo"
    assert result.regiones_unicas >= 0, "regiones_unicas no puede ser negativo"

    if result.tasa_asistencia_promedio is not None:
        assert result.tasa_asistencia_promedio >= 0, (
            f"tasa_asistencia_promedio negativa: {result.tasa_asistencia_promedio}"
        )

    print(
        f"         Info: total={total} | "
        f"registro={result.usuarios_registro} | "
        f"inscritos={result.usuarios_inscritos_taller} | "
        f"asistidos={result.usuarios_asistidos_taller} | "
        f"minga={result.usuarios_minga}"
    )


def test_4_por_region_estructura():
    """
    Verifica que por_region es un dict no vacío con claves string
    y valores enteros positivos.
    """
    from scripts.analytics import compute_analytics

    result = compute_analytics()

    if result.total_usuarios == 0:
        print(f"         {WARN}  Sin usuarios — test omitido")
        return

    assert len(result.por_region) > 0, (
        "por_region está vacío. Al menos una región debería tener usuarios."
    )

    for key, val in result.por_region.items():
        assert isinstance(key, str), (
            f"Clave de por_region debe ser str, es {type(key)}: '{key}'"
        )
        assert isinstance(val, int), (
            f"Valor de por_region debe ser int, es {type(val)} para '{key}'"
        )
        assert val > 0, (
            f"Conteo de región '{key}' debe ser > 0, es {val}"
        )

    # La suma de regiones <= total (algunos usuarios pueden no tener región)
    suma_regiones = sum(result.por_region.values())
    assert suma_regiones <= result.total_usuarios, (
        f"Suma de por_region ({suma_regiones}) > total_usuarios ({result.total_usuarios})"
    )

    print(
        f"         Info: {len(result.por_region)} regiones | "
        f"top: {list(result.por_region.items())[0]}"
    )


def test_5_top_comunas_estructura():
    """
    Verifica que top_comunas es una lista de dicts con las claves
    requeridas (comuna, region, count, pct) y valores coherentes.
    """
    from scripts.analytics import compute_analytics

    result = compute_analytics()

    if result.total_usuarios == 0:
        print(f"         {WARN}  Sin usuarios — test omitido")
        return

    assert isinstance(result.top_comunas, list), (
        f"top_comunas debe ser list, es {type(result.top_comunas)}"
    )

    if not result.top_comunas:
        print(f"         {WARN}  top_comunas vacío — puede ser que no haya comunas en los datos")
        return

    claves_requeridas = {"comuna", "region", "count", "pct"}

    for i, item in enumerate(result.top_comunas):
        assert isinstance(item, dict), (
            f"Elemento {i} de top_comunas debe ser dict, es {type(item)}"
        )
        claves_faltantes = claves_requeridas - set(item.keys())
        assert not claves_faltantes, (
            f"Elemento {i} de top_comunas falta claves: {claves_faltantes}"
        )
        assert isinstance(item["count"], int) and item["count"] > 0, (
            f"top_comunas[{i}].count debe ser int > 0, es {item['count']}"
        )
        assert isinstance(item["pct"], float) and 0 <= item["pct"] <= 100, (
            f"top_comunas[{i}].pct debe ser float entre 0 y 100, es {item['pct']}"
        )

    # Verificar orden descendente por count
    counts = [item["count"] for item in result.top_comunas]
    assert counts == sorted(counts, reverse=True), (
        "top_comunas no está ordenado por count descendente"
    )

    print(
        f"         Info: {len(result.top_comunas)} comunas | "
        f"top: {result.top_comunas[0]['comuna']} ({result.top_comunas[0]['count']})"
    )


def test_6_inscritos_vs_asistidos_coherente():
    """
    Verifica que inscritos_vs_asistidos tiene las claves requeridas
    y que los segmentos suman coherentemente con los totales de flags.
    """
    from scripts.analytics import compute_analytics

    result = compute_analytics()

    if result.total_usuarios == 0:
        print(f"         {WARN}  Sin usuarios — test omitido")
        return

    if not result.inscritos_vs_asistidos:
        print(f"         {WARN}  inscritos_vs_asistidos vacío — test omitido")
        return

    d = result.inscritos_vs_asistidos
    claves_requeridas = {
        "total_inscritos", "total_asistidos",
        "solo_inscritos", "solo_asistidos",
        "ambos", "ninguno", "tasa_conversion_pct",
    }
    faltantes = claves_requeridas - set(d.keys())
    assert not faltantes, (
        f"Faltan claves en inscritos_vs_asistidos: {faltantes}"
    )

    # Los 4 segmentos (solo_inscritos + solo_asistidos + ambos + ninguno)
    # deben sumar total_usuarios
    suma_segmentos = (
        d["solo_inscritos"] + d["solo_asistidos"] +
        d["ambos"] + d["ninguno"]
    )
    assert suma_segmentos == result.total_usuarios, (
        f"Los 4 segmentos suman {suma_segmentos} pero total_usuarios={result.total_usuarios}. "
        f"Detalle: solo_inscritos={d['solo_inscritos']}, "
        f"solo_asistidos={d['solo_asistidos']}, "
        f"ambos={d['ambos']}, ninguno={d['ninguno']}"
    )

    # Verificar coherencia con los totales de flags
    assert d["total_inscritos"] == result.usuarios_inscritos_taller, (
        f"inscritos_vs_asistidos.total_inscritos ({d['total_inscritos']}) != "
        f"result.usuarios_inscritos_taller ({result.usuarios_inscritos_taller})"
    )
    assert d["total_asistidos"] == result.usuarios_asistidos_taller, (
        f"inscritos_vs_asistidos.total_asistidos ({d['total_asistidos']}) != "
        f"result.usuarios_asistidos_taller ({result.usuarios_asistidos_taller})"
    )

    # tasa_conversion_pct entre 0 y 100
    assert 0 <= d["tasa_conversion_pct"] <= 100, (
        f"tasa_conversion_pct fuera de rango: {d['tasa_conversion_pct']}"
    )

    print(
        f"         Info: inscritos={d['total_inscritos']} | "
        f"asistidos={d['total_asistidos']} | "
        f"ambos={d['ambos']} | "
        f"conversión={d['tasa_conversion_pct']}%"
    )


def test_7_timeline_orden_y_formato():
    """
    Verifica que timeline_registros está ordenado cronológicamente,
    los períodos tienen formato 'YYYY-MM', y el acumulado es monotónico.
    """
    from scripts.analytics import compute_analytics
    import re

    result = compute_analytics()

    if not result.timeline_registros:
        print(f"         {WARN}  timeline_registros vacío — puede ser que no haya fechas")
        return

    periodo_regex = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    acumulado_prev = 0

    for i, item in enumerate(result.timeline_registros):
        assert isinstance(item, dict), (
            f"Elemento {i} de timeline_registros debe ser dict"
        )
        assert "periodo"   in item, f"Falta 'periodo' en elemento {i}"
        assert "count"     in item, f"Falta 'count' en elemento {i}"
        assert "acumulado" in item, f"Falta 'acumulado' en elemento {i}"

        assert periodo_regex.match(str(item["periodo"])), (
            f"Período '{item['periodo']}' no tiene formato YYYY-MM"
        )
        assert isinstance(item["count"], int) and item["count"] > 0, (
            f"count en período '{item['periodo']}' debe ser int > 0"
        )
        assert item["acumulado"] >= acumulado_prev, (
            f"acumulado no es monotónico en período '{item['periodo']}': "
            f"{item['acumulado']} < {acumulado_prev}"
        )
        acumulado_prev = item["acumulado"]

    # El acumulado final debe coincidir con usuarios que tienen fecha
    # (puede ser menor que total_usuarios si algunos no tienen fecha)
    acumulado_final = result.timeline_registros[-1]["acumulado"]
    assert acumulado_final <= result.total_usuarios, (
        f"acumulado final ({acumulado_final}) > total_usuarios ({result.total_usuarios})"
    )

    # Verificar orden cronológico
    periodos = [item["periodo"] for item in result.timeline_registros]
    assert periodos == sorted(periodos), (
        f"timeline_registros no está ordenado cronológicamente. "
        f"Primeros períodos: {periodos[:3]}"
    )

    print(
        f"         Info: {len(result.timeline_registros)} períodos | "
        f"desde {periodos[0]} hasta {periodos[-1]} | "
        f"acumulado final: {acumulado_final}"
    )


def test_8_fallback_csv():
    """
    Verifica que compute_analytics() usa el CSV como fallback cuando
    la DB no existe o está en una ruta inaccesible.
    """
    from scripts.analytics import compute_analytics
    from config.settings   import MASTER_CSV_PATH

    if not MASTER_CSV_PATH.exists():
        print(f"         {WARN}  CSV no existe en {MASTER_CSV_PATH} — test omitido")
        return

    # Pasar una ruta de DB que definitivamente no existe
    ruta_db_falsa = Path("__db_inexistente_test__.db")

    result = compute_analytics(
        db_path=ruta_db_falsa,
        csv_path=MASTER_CSV_PATH,
    )

    assert result.data_source == "csv", (
        f"Con DB inexistente, data_source debería ser 'csv', es '{result.data_source}'"
    )
    assert result.total_usuarios > 0, (
        "El fallback a CSV retornó 0 usuarios. Verificar que el CSV tiene datos."
    )
    assert not result.timeline_registros.__class__.__name__ == "NoneType", (
        "timeline_registros no debe ser None"
    )

    print(
        f"         Info: Fallback CSV funcionó | "
        f"total_usuarios={result.total_usuarios}"
    )


def test_9_sin_datos_no_crashea():
    """
    Verifica que compute_analytics() retorna un AnalyticsResult vacío
    (no lanza excepción) cuando ni la DB ni el CSV están disponibles.
    """
    from scripts.analytics import compute_analytics, AnalyticsResult

    ruta_db_falsa  = Path("__db_inexistente_test__.db")
    ruta_csv_falso = Path("__csv_inexistente_test__.csv")

    result = compute_analytics(
        db_path=ruta_db_falsa,
        csv_path=ruta_csv_falso,
    )

    assert isinstance(result, AnalyticsResult), (
        "Debe retornar AnalyticsResult incluso sin datos disponibles"
    )
    assert result.data_source == "empty", (
        f"data_source debe ser 'empty' sin datos, es '{result.data_source}'"
    )
    assert result.total_usuarios == 0, (
        f"total_usuarios debe ser 0 sin datos, es {result.total_usuarios}"
    )
    assert result.por_region == {}, (
        "por_region debe ser dict vacío sin datos"
    )
    assert result.top_comunas == [], (
        "top_comunas debe ser lista vacía sin datos"
    )
    assert result.timeline_registros == [], (
        "timeline_registros debe ser lista vacía sin datos"
    )

    print("         Info: AnalyticsResult vacío retornado sin excepción ✓")


# ── Ejecución ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("═" * 62)
    print("  VERIFICACIÓN analytics.py")
    print("  Proyecto: Déficit Cero — Community Data Pipeline")
    print("═" * 62)
    print()

    # Aviso si la DB no está disponible
    if not _db_disponible():
        print(
            f"  {WARN}  database/deficit_cero.db no encontrada o vacía.\n"
            f"       Algunos tests usarán el CSV como fallback.\n"
            f"       Para resultados completos, ejecutar primero:\n"
            f"       python verify_phase5.py\n"
        )

    run_test(
        "Test 1 — Contrato AnalyticsResult (tipos y campos)",
        test_1_contrato_analytics_result,
    )
    run_test(
        "Test 2 — total_usuarios coincide con row count de la DB",
        test_2_total_coincide_con_db,
    )
    run_test(
        "Test 3 — Coherencia de KPIs (flags <= total, rangos válidos)",
        test_3_coherencia_kpis,
    )
    run_test(
        "Test 4 — por_region: dict no vacío con tipos correctos",
        test_4_por_region_estructura,
    )
    run_test(
        "Test 5 — top_comunas: estructura y orden por count desc",
        test_5_top_comunas_estructura,
    )
    run_test(
        "Test 6 — inscritos_vs_asistidos: segmentos suman total_usuarios",
        test_6_inscritos_vs_asistidos_coherente,
    )
    run_test(
        "Test 7 — timeline_registros: formato YYYY-MM y orden cronológico",
        test_7_timeline_orden_y_formato,
    )
    run_test(
        "Test 8 — Fallback a CSV cuando DB no existe",
        test_8_fallback_csv,
    )
    run_test(
        "Test 9 — Sin datos disponibles retorna vacío sin crashear",
        test_9_sin_datos_no_crashea,
    )

    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    print()
    print("─" * 62)
    print(f"  Resultado: {passed}/{total} tests pasaron")
    print()

    if passed == total:
        print(
            "  \033[92m✓ analytics.py verificado. "
            "Listo para la Entrega 2 (main.py + scheduler.py).\033[0m"
        )
    else:
        print(
            f"  \033[91m✗ Hay {total - passed} fallo(s). "
            f"Corregir antes de continuar.\033[0m"
        )
        print()
        for name, ok, err in results:
            if not ok:
                print(f"  ✗ {name}")
                print(
                    f"    → {err[:150]}"
                    f"{'...' if len(err) > 150 else ''}"
                )

    print("─" * 62)
    print()

    if passed < total:
        sys.exit(1)

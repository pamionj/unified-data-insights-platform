"""
verify_asistencia_extractor.py — Verificación aislada de AsistenciaTalleresExtractor.

Prueba el extractor contra datos sintéticos que reproducen exactamente
los patrones confirmados en el diseño:
    - Tres formatos de fecha (ISO, DD/MM/YYYY, DD-MM-YYYY)
    - MEMBER_SCREEN_NAME vacío (columna opcional)
    - Mojibake UTF-8/Latin-1 en nombres
    - Duplicados reales vs. asistencias legítimas a distintas fechas
    - Email con espacios y mayúsculas (normalización estándar)
    - Valor de fecha no reconocido (debe loggear sin crashear)

No conecta con main.py ni modifica ningún archivo del pipeline existente.

Ejecutar desde la raíz del proyecto:
    python verify_asistencia_extractor.py
"""

import sys
import tempfile
import traceback
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from scripts.extractors.asistencia_talleres_extractor import (
    AsistenciaTalleresExtractor,
    normalize_fecha_taller,
)
from scripts.utils import get_logger

PASS = "\033[92m+ PASS\033[0m"
FAIL = "\033[91m- FAIL\033[0m"
SEP  = "-" * 58
results: list[tuple[str, bool, str]] = []


def run_test(name: str, fn) -> None:
    try:
        fn()
        results.append((name, True, ""))
        print(f"  {PASS}  {name}")
    except AssertionError as exc:
        results.append((name, False, str(exc)))
        print(f"  {FAIL}  {name}")
        print(f"         {exc}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  {FAIL}  {name}")
        print(f"         {type(exc).__name__}: {exc}")
        traceback.print_exc()


def _make_csv(content: str, encoding: str = "utf-8-sig") -> Path:
    """Escribe un CSV temporal y retorna su Path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False,
        encoding=encoding,
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


# ── Tests de normalize_fecha_taller ──────────────────────────────────────────

def test_1_fecha_iso():
    """Formato ISO: YYYY-MM-DD y YYYY/MM/DD."""
    logger = get_logger("test_fecha")
    series = pd.Series(["2026-05-28", "2026/05/28", "2025-12-01"])
    result = normalize_fecha_taller(series, logger)
    assert result.notna().all(), f"NaT inesperado: {result.tolist()}"
    assert result.iloc[0] == pd.Timestamp("2026-05-28")
    assert result.iloc[1] == pd.Timestamp("2026-05-28")
    assert result.iloc[2] == pd.Timestamp("2025-12-01")


def test_2_fecha_chile_barra():
    """Formato chileno con barra: DD/MM/YYYY y D/M/YYYY (sin cero)."""
    logger = get_logger("test_fecha")
    series = pd.Series(["28/05/2026", "28/5/2026", "1/1/2024"])
    result = normalize_fecha_taller(series, logger)
    assert result.notna().all(), f"NaT inesperado: {result.tolist()}"
    assert result.iloc[0] == pd.Timestamp("2026-05-28")
    assert result.iloc[1] == pd.Timestamp("2026-05-28")
    assert result.iloc[2] == pd.Timestamp("2024-01-01")


def test_3_fecha_chile_guion():
    """Formato chileno con guión: DD-MM-YYYY y D-M-YYYY (sin cero)."""
    logger = get_logger("test_fecha")
    series = pd.Series(["28-05-2026", "28-5-2026", "1-1-2024"])
    result = normalize_fecha_taller(series, logger)
    assert result.notna().all(), f"NaT inesperado: {result.tolist()}"
    assert result.iloc[0] == pd.Timestamp("2026-05-28")
    assert result.iloc[1] == pd.Timestamp("2026-05-28")
    assert result.iloc[2] == pd.Timestamp("2024-01-01")


def test_4_fecha_formato_desconocido_no_crashea():
    """Valor no reconocido → NaT sin excepción, warning en el log."""
    logger = get_logger("test_fecha")
    series = pd.Series(["28/5/26", "hoy", "", "2026-05-28"])
    result = normalize_fecha_taller(series, logger)
    assert pd.isna(result.iloc[0]), "28/5/26 debería ser NaT (año de 2 dígitos)"
    assert pd.isna(result.iloc[1]), "'hoy' debería ser NaT"
    assert pd.isna(result.iloc[2]), "cadena vacía debería ser NaT"
    assert result.iloc[3] == pd.Timestamp("2026-05-28"), "fecha válida no debe verse afectada"


# ── Tests del extractor completo ──────────────────────────────────────────────

def test_5_extractor_caso_base():
    """CSV bien formado con los 5 campos: extrae todas las filas."""
    csv = (
        "TALLER_ENTRY_ID,TALLER_TITLE,FECHA_TALLER,MEMBER_EMAIL,MEMBER_SCREEN_NAME\n"
        "12569,DS.01 - Mayo,28/5/2026,ana@test.cl,Ana Soto\n"
        "12569,DS.01 - Mayo,28/5/2026,bruno@test.cl,Bruno Diaz\n"
        "12570,DS.49 - Junio,15/6/2026,carla@test.cl,Carla Ramos\n"
    )
    path = _make_csv(csv)
    try:
        # Inyectar mappings mínimos sin tocar config/mappings.py
        import config.mappings as m
        m.COLUMN_MAPPING["asistencia"] = {
            "TALLER_ENTRY_ID":    "taller_entry_id",
            "TALLER_TITLE":       "taller_titulo",
            "FECHA_TALLER":       "fecha_taller",
            "MEMBER_EMAIL":       "email",
            "MEMBER_SCREEN_NAME": "nombre_asistente",
        }
        df = AsistenciaTalleresExtractor(file_path=path).extract()
        assert len(df) == 3, f"Esperadas 3 filas, obtenidas {len(df)}"
        assert "email" in df.columns
        assert "fecha_taller" in df.columns
        assert df["fecha_taller"].notna().all(), "Fechas deben estar parseadas"
    finally:
        path.unlink(missing_ok=True)


def test_6_deduplicacion_duplicado_real():
    """Dos filas idénticas (mismo taller, email y fecha) → queda 1."""
    csv = (
        "TALLER_ENTRY_ID,TALLER_TITLE,FECHA_TALLER,MEMBER_EMAIL,MEMBER_SCREEN_NAME\n"
        "12569,DS.01,28/5/2026,ana@test.cl,Ana\n"
        "12569,DS.01,28/5/2026,ana@test.cl,Ana\n"   # duplicado real
        "12569,DS.01,28/5/2026,bruno@test.cl,Bruno\n"
    )
    path = _make_csv(csv)
    try:
        df = AsistenciaTalleresExtractor(file_path=path).extract()
        assert len(df) == 2, (
            f"Duplicado real debe eliminarse: esperadas 2 filas, obtenidas {len(df)}"
        )
    finally:
        path.unlink(missing_ok=True)


def test_7_deduplicacion_distintas_fechas_mismo_taller():
    """Misma persona, mismo taller, DISTINTAS fechas → se conservan ambas."""
    csv = (
        "TALLER_ENTRY_ID,TALLER_TITLE,FECHA_TALLER,MEMBER_EMAIL,MEMBER_SCREEN_NAME\n"
        "12569,DS.01,28/5/2026,ana@test.cl,Ana\n"
        "12569,DS.01,04/6/2026,ana@test.cl,Ana\n"   # misma persona, otra sesión
        "12569,DS.01,28/5/2026,bruno@test.cl,Bruno\n"
    )
    path = _make_csv(csv)
    try:
        df = AsistenciaTalleresExtractor(file_path=path).extract()
        assert len(df) == 3, (
            f"Asistencias legítimas a distintas fechas deben conservarse: "
            f"esperadas 3 filas, obtenidas {len(df)}"
        )
    finally:
        path.unlink(missing_ok=True)


def test_8_email_normalizado_para_dedup():
    """Email con mayúsculas y espacios → normalizado antes de deduplicar."""
    csv = (
        "TALLER_ENTRY_ID,TALLER_TITLE,FECHA_TALLER,MEMBER_EMAIL,MEMBER_SCREEN_NAME\n"
        "12569,DS.01,28/5/2026,ANA@TEST.CL ,Ana\n"
        "12569,DS.01,28/5/2026, ana@test.cl,Ana\n"   # mismo email, distinta forma
    )
    path = _make_csv(csv)
    try:
        df = AsistenciaTalleresExtractor(file_path=path).extract()
        assert len(df) == 1, (
            f"Emails con mayúsculas/espacios distintos deben deduplicarse: "
            f"esperada 1 fila, obtenidas {len(df)}"
        )
    finally:
        path.unlink(missing_ok=True)


def test_9_member_screen_name_vacio():
    """MEMBER_SCREEN_NAME vacío o con solo espacios → None, no crashea."""
    csv = (
        "TALLER_ENTRY_ID,TALLER_TITLE,FECHA_TALLER,MEMBER_EMAIL,MEMBER_SCREEN_NAME\n"
        "12569,DS.01,28/5/2026,ana@test.cl,\n"       # vacío
        "12569,DS.01,28/5/2026,bruno@test.cl,   \n"  # solo espacios
        "12569,DS.01,28/5/2026,carla@test.cl,Carla\n"
    )
    path = _make_csv(csv)
    try:
        df = AsistenciaTalleresExtractor(file_path=path).extract()
        assert len(df) == 3, f"Esperadas 3 filas, obtenidas {len(df)}"
        assert pd.isna(df.loc[df["email"].str.contains("ana"), "nombre_asistente"].iloc[0])
        assert pd.isna(df.loc[df["email"].str.contains("bruno"), "nombre_asistente"].iloc[0])
        assert df.loc[df["email"].str.contains("carla"), "nombre_asistente"].iloc[0] == "Carla"
    finally:
        path.unlink(missing_ok=True)


def test_10_archivo_inexistente_retorna_dataframe_vacio():
    """Archivo no encontrado → DataFrame vacío sin excepción."""
    df = AsistenciaTalleresExtractor(
        file_path=Path("__archivo_inexistente__.csv")
    ).extract()
    assert isinstance(df, pd.DataFrame), "Debe retornar DataFrame"
    assert df.empty, "DataFrame debe estar vacío si el archivo no existe"


# ── Ejecución ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print(SEP)
    print("  VERIFICACIÓN — AsistenciaTalleresExtractor")
    print("  Fase 1: extractor aislado, sin conexión al pipeline")
    print(SEP)
    print()

    run_test("Test 1  — Fecha ISO (YYYY-MM-DD y YYYY/MM/DD)",                  test_1_fecha_iso)
    run_test("Test 2  — Fecha Chile barra (DD/MM/YYYY, sin cero a la izq.)",   test_2_fecha_chile_barra)
    run_test("Test 3  — Fecha Chile guión (DD-MM-YYYY, sin cero a la izq.)",   test_3_fecha_chile_guion)
    run_test("Test 4  — Formato desconocido → NaT sin crashear",               test_4_fecha_formato_desconocido_no_crashea)
    run_test("Test 5  — Extractor caso base (5 columnas, 3 filas)",            test_5_extractor_caso_base)
    run_test("Test 6  — Deduplicación: duplicado real → queda 1 fila",         test_6_deduplicacion_duplicado_real)
    run_test("Test 7  — Deduplicación: distintas fechas → se conservan ambas", test_7_deduplicacion_distintas_fechas_mismo_taller)
    run_test("Test 8  — Email con mayúsculas/espacios → normalizado para dedup",test_8_email_normalizado_para_dedup)
    run_test("Test 9  — MEMBER_SCREEN_NAME vacío → None, no crashea",          test_9_member_screen_name_vacio)
    run_test("Test 10 — Archivo inexistente → DataFrame vacío sin excepción",  test_10_archivo_inexistente_retorna_dataframe_vacio)

    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    print()
    print(SEP)
    print(f"  Resultado: {passed}/{total} tests pasaron")
    print()
    if passed == total:
        print("  + Fase 1 verificada.")
        print("  Siguiente paso: agregar 'asistencia' en config/mappings.py")
        print("  y conectar el extractor al pipeline (Fase 2).")
    else:
        print("  - Corregir antes de conectar al pipeline.")
        for name, ok, err in results:
            if not ok:
                print(f"    - {name}")
                print(f"      {err[:120]}")
    print(SEP)
    print()
    if passed < total:
        sys.exit(1)
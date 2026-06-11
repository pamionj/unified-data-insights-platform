"""
verify_phase2.py
Verificación independiente de Tests 6 y 7 — Fase 2 ETL Déficit Cero.
Ejecutar desde la raíz del proyecto:  python verify_phase2.py
"""

import sys
import traceback
from pathlib import Path

import pandas as pd

# ── Asegurar que el proyecto está en el path ──────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def run_test(name: str, fn) -> None:
    """Ejecuta un test, captura cualquier excepción y registra resultado."""
    try:
        fn()
        results.append((name, True, ""))
        print(f"{PASS}  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"{FAIL}  {name}")
        print(f"       Error: {exc}")
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 — Tolerancia a archivo inexistente
# Verifica que BaseExtractor NO lanza excepción cuando el archivo no existe.
# Si este test falla, el pipeline entero se caerá en producción cuando
# falte un CSV.
# ─────────────────────────────────────────────────────────────────────────────
def test_6_tolerancia_archivo_inexistente():
    from scripts.extractors.base_extractor import BaseExtractor

    class DummyExtractor(BaseExtractor):
        def __init__(self):
            # Pasamos una ruta que definitivamente no existe
            super().__init__("registro", Path("__archivo_que_no_existe_xyz__.csv"))

        def extract(self) -> pd.DataFrame:
            if not self.validate_file():
                return pd.DataFrame()
            return pd.DataFrame()  # nunca debería llegar aquí

    extractor = DummyExtractor()

    # La llamada a validate_file() NO debe lanzar FileNotFoundError
    resultado = extractor.extract()

    assert isinstance(resultado, pd.DataFrame), (
        f"extract() debe retornar pd.DataFrame, retornó {type(resultado)}"
    )
    assert resultado.empty, (
        "extract() debe retornar DataFrame VACÍO cuando el archivo no existe, "
        f"pero retornó {len(resultado)} filas"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7A — Las columnas riesgosas de Zoom están renombradas
# Verifica que "Nombre (nombre original)" y "Duración (minutos)"
# NO aparecen en el DataFrame final (deben estar como "nombre_zoom"
# y "duracion_minutos").
# ─────────────────────────────────────────────────────────────────────────────
def test_7a_columnas_risky_renombradas():
    from scripts.extractors.zoom_extractor import ZoomExtractor

    df = ZoomExtractor().extract()

    assert not df.empty, (
        "ZoomExtractor retornó DataFrame vacío. "
        "Verificar que data/raw/zoom_asistencia.csv existe."
    )

    columnas_originales_prohibidas = [
        "Nombre (nombre original)",
        "Duración (minutos)",
        "Correo electrónico",
        "Hora de entrada",
        "Hora de salida",
        "En sala de espera",
    ]
    for col in columnas_originales_prohibidas:
        assert col not in df.columns, (
            f"La columna original '{col}' sigue presente en el DataFrame. "
            f"El renombramiento falló. Columnas actuales: {df.columns.tolist()}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7B — Las columnas renombradas SÍ existen con el nombre correcto
# ─────────────────────────────────────────────────────────────────────────────
def test_7b_columnas_renombradas_presentes():
    from scripts.extractors.zoom_extractor import ZoomExtractor

    df = ZoomExtractor().extract()

    columnas_esperadas = [
        "nombre_zoom",       # ← Nombre (nombre original)
        "email",             # ← Correo electrónico
        "hora_entrada",
        "hora_salida",
        "duracion_minutos",  # ← Duración (minutos)
        "en_sala_espera",
        "nombre",            # ← generado por _split_nombre_completo
        "apellido",          # ← generado por _split_nombre_completo
        "nombre_key",        # ← generado por _build_nombre_key
        "match_confidence",  # ← asignado por _assign_initial_confidence
        "_source_name",
        "_source_file",
        "_extracted_at",
    ]
    columnas_faltantes = [c for c in columnas_esperadas if c not in df.columns]

    assert not columnas_faltantes, (
        f"Columnas esperadas ausentes en ZoomExtractor: {columnas_faltantes}\n"
        f"Columnas presentes: {df.columns.tolist()}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7C — match_confidence solo tiene valores válidos
# ─────────────────────────────────────────────────────────────────────────────
def test_7c_match_confidence_valores_validos():
    from scripts.extractors.zoom_extractor import ZoomExtractor

    df = ZoomExtractor().extract()
    valores_validos = {"HIGH", "LOW", "UNMATCHED"}
    valores_presentes = set(df["match_confidence"].dropna().unique())

    valores_invalidos = valores_presentes - valores_validos
    assert not valores_invalidos, (
        f"match_confidence contiene valores no permitidos: {valores_invalidos}. "
        f"Solo se permiten: {valores_validos}"
    )

    # Debe haber al menos un HIGH (hay filas con email en el CSV fake)
    assert "HIGH" in valores_presentes, (
        "No hay ningún registro con match_confidence='HIGH'. "
        "Verificar que _assign_initial_confidence detecta emails válidos."
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7D — Filas sin email tienen nombre_key o UNMATCHED
# ─────────────────────────────────────────────────────────────────────────────
def test_7d_filas_sin_email_tienen_key_o_unmatched():
    from scripts.extractors.zoom_extractor import ZoomExtractor

    df = ZoomExtractor().extract()

    # Filtrar filas donde email es nulo o vacío
    sin_email = df[df["email"].isna() | (df["email"].astype(str).str.strip() == "")]

    if sin_email.empty:
        # El CSV fake debería tener 5 filas sin email; si no las hay, avisar
        print("       AVISO: No se encontraron filas sin email. "
              "Verificar que zoom_asistencia.csv tiene las 5 filas sin correo.")
        return

    # Cada fila sin email debe ser LOW (tiene nombre_key) o UNMATCHED
    for idx, row in sin_email.iterrows():
        assert row["match_confidence"] in ("LOW", "UNMATCHED"), (
            f"Fila {idx} sin email tiene match_confidence='{row['match_confidence']}'. "
            f"Debería ser 'LOW' o 'UNMATCHED'. nombre_key='{row.get('nombre_key')}'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  VERIFICACIÓN FASE 2 — Tests 6 y 7")
    print("  Proyecto: Déficit Cero Community Data Pipeline")
    print("═" * 60 + "\n")

    run_test("Test 6  — Tolerancia a archivo inexistente",
             test_6_tolerancia_archivo_inexistente)

    run_test("Test 7A — Columnas riesgosas renombradas (no deben existir)",
             test_7a_columnas_risky_renombradas)

    run_test("Test 7B — Columnas renombradas presentes con nombre correcto",
             test_7b_columnas_renombradas_presentes)

    run_test("Test 7C — match_confidence solo valores HIGH/LOW/UNMATCHED",
             test_7c_match_confidence_valores_validos)

    run_test("Test 7D — Filas sin email tienen confidence LOW o UNMATCHED",
             test_7d_filas_sin_email_tienen_key_o_unmatched)

    # ── Resumen final ─────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    print("\n" + "─" * 60)
    print(f"  Resultado: {passed}/{total} tests pasaron")

    if passed == total:
        print("  \033[92mFase 2 verificada correctamente. Lista para Fase 3.\033[0m")
    else:
        print("  \033[91mHay fallos. Corregir antes de continuar a Fase 3.\033[0m")
        failed = [(n, e) for n, ok, e in results if not ok]
        for name, err in failed:
            print(f"\n  ✗ {name}")
            print(f"    {err}")
        sys.exit(1)

    print("─" * 60 + "\n")

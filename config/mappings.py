"""
Mapeos y normalizaciones de datos para el pipeline ETL.

Este módulo centraliza los diccionarios utilizados para renombrar columnas,
normalizar valores categóricos y definir campos prioritarios.
"""
from typing import Dict, List

# Mapeo de nombres de columnas desde el origen a un formato normalizado (snake_case).
COLUMN_MAPPING: Dict[str, Dict[str, str]] = {
    "registro": {
        "MEMBER_ID": "member_id",
        "ROL": "rol",
        "NOMBRE": "nombre",
        "APELLIDO": "apellido",
        "EMAIL": "email",
        "FECHA_NACIMIENTO": "fecha_nacimiento",
        "WHATSAPP": "whatsapp",
        "REGION": "region",
        "COMUNA": "comuna",
        "REGISTRO_COMPLETO": "registro_completo",
        "ACEPTA_TERMINOS": "acepta_terminos",
        "FECHA_CREACION": "fecha_creacion",
        "GENERO": "genero",
        "CUANTAS_PERSONAS_VIVES": "cuantas_personas_viven",
        "PERTENECES_COMITE_VIVIENDA": "pertenece_comite",
        "SITUACION_HABITACIONAL": "situacion_habitacional",
        "ESTADO": "estado_registro",
        "CAMPOS_COMPLETOS": "campos_completos",
        "FECHA": "fecha_paso2",
        "PASO 2 COMPLETO": "paso2_completo",
        "PROVEEDOR REGISTRO": "proveedor_registro",
    },
    "talleres": {
        "TALLER_ENTRY_ID": "taller_entry_id",
        "TALLER_TITLE": "taller_titulo",
        "TALLER_URL": "taller_url",
        "MEMBER_ID": "member_id",
        "MEMBER_SCREEN_NAME": "nombre_pantalla",
        "MEMBER_EMAIL": "email",
        "MEMBER_URL": "member_url",
        "FORMULARIO_ENTRY_ID": "formulario_entry_id",
        "FORMULARIO_URL": "formulario_url",
        "FORMULARIO_STATUS": "formulario_status",
        "FORMULARIO_ENTRY_DATE": "fecha_inscripcion",
        "PREGUNTAS - RESPUESTAS": "preguntas_respuestas",
    },
    "minga": {
        "conv_id": "conv_id",
        "date": "fecha_conversacion",
        "transcript": "transcript",
        "num_msgs": "num_mensajes",
        "email_usuario": "email",
        "preguntas_usuario": "preguntas_usuario",
        "resumen": "resumen",
        "subsidio_recomendado": "subsidio_recomendado",
        "rsh": "rsh",
        "con_quien_postula": "con_quien_postula",
        "edad": "edad_minga",
        "tiene_propiedad": "tiene_propiedad",
        "tiene_subsidio_habitacional": "tiene_subsidio",
        "nacionalidad": "nacionalidad",
        "ingresos": "ingresos",
        "ahorro": "ahorro",
    },
    "zoom": {
        "Nombre (nombre original)": "nombre_zoom",
        "Correo electrónico": "email",
        "Hora de entrada": "hora_entrada",
        "Hora de salida": "hora_salida",
        "Duración (minutos)": "duracion_minutos",
        "Invitado": "es_invitado",
        "Respuesta al descargo de responsabilidad relativa a la grabación": "acepta_grabacion",
        "En sala de espera": "en_sala_espera",
    },
}

# Campos prioritarios para la consolidación de datos.
# Cuando hay conflictos, los datos de las fuentes que contienen estos campos
# pueden tener mayor precedencia.
PRIORITY_FIELDS: List[str] = [
    "nombre",
    "apellido",
    "region",
    "comuna",
    "genero",
    "fecha_nacimiento",
]

# Define la columna de fecha principal para cada fuente de datos.
SOURCE_DATE_COLUMNS: Dict[str, str] = {
    "registro": "fecha_creacion",
    "talleres": "fecha_inscripcion",
    "minga": "fecha_conversacion",
    "zoom": "hora_entrada",
}

# Mapeo para la normalización del campo de género.
GENDER_NORMALIZATION: Dict[str, str] = {
    "m": "masculino",
    "masculino": "masculino",
    "male": "masculino",
    "hombre": "masculino",
    "h": "masculino",
    "f": "femenino",
    "femenino": "femenino",
    "female": "femenino",
    "mujer": "femenino",
    "otro": "otro",
    "other": "otro",
    "no binario": "otro",
    "no_especificado": "no_especificado",
    "": "no_especificado",
}

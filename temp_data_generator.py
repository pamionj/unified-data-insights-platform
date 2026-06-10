
import pandas as pd
import numpy as np
from faker import Faker
import random
import json
from datetime import datetime, timedelta

# Inicializar Faker para datos chilenos
fake = Faker("es_CL")

# --- Constantes y configuración ---
NUM_REGISTRO = 80
NUM_TALLERES = 60
NUM_MINGA = 50
NUM_ZOOM = 45
OUTPUT_DIR = "data/raw"

# --- Datos Chilenos para realismo ---
REGIONES_Y_COMUNAS = {
    "Metropolitana de Santiago": ["Santiago", "Puente Alto", "Maipú", "La Florida", "Las Condes", "Providencia"],
    "Valparaíso": ["Valparaíso", "Viña del Mar", "Quilpué", "Villa Alemana", "Concón"],
    "Biobío": ["Concepción", "Talcahuano", "Coronel", "Chiguayante", "San Pedro de la Paz"],
    "O'Higgins": ["Rancagua", "Machalí", "Rengo", "San Fernando"],
    "Maule": ["Talca", "Curicó", "Linares", "Constitución"]
}
REGIONES_PONDERACION = {
    "Metropolitana de Santiago": 0.5,
    "Valparaíso": 0.2,
    "Biobío": 0.15,
    "O'Higgins": 0.10,
    "Maule": 0.05
}
SITUACION_HABITACIONAL = ["Arriendo", "Allegado/a", "Vivienda propia con deuda", "Vivienda propia sin deuda", "Vivienda cedida", "Sin vivienda"]
PROVEEDOR_REGISTRO = ["web", "app_movil", "formulario_fisico"]
TALLER_TITLES = [
    "Taller de Postulación DS19 - Mayo 2026",
    "Taller Ahorro y Subsidio Habitacional",
    "Jornada Comités de Vivienda - Región Metropolitana",
    "Webinar: Cómo Postular al Subsidio Habitacional"
]
SUBSIDIOS = ["DS19", "DS49", "DS1", "Ninguno", "Pendiente evaluación"]
RSH = ["40%", "60%", "80%", "No registra"]
NACIONALIDADES = ["Chilena", "Venezolana", "Colombiana", "Peruana"]
INGRESOS = ["$400.000 - $600.000", "$600.001 - $900.000", "$900.001 - $1.200.000", "Más de $1.200.000"]

# --- 1. Generación de 'registro_rcv.csv' ---
print("Generando registro_rcv.csv...")
data_registro = []
emails_registro = set()

for i in range(NUM_REGISTRO):
    nombre = fake.first_name()
    apellido = fake.last_name()
    email = f"{nombre.lower()}.{apellido.lower()}@{random.choice(['gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com'])}"
    
    region = random.choices(list(REGIONES_PONDERACION.keys()), weights=list(REGIONES_PONDERACION.values()), k=1)[0]
    comuna = random.choice(REGIONES_Y_COMUNAS[region])
    
    fecha_creacion = fake.date_time_between(start_date=datetime(2023,1,1), end_date=datetime(2026,5,1))

    data_registro.append({
        "MEMBER_ID": f"RCV-{i+1:04d}",
        "ROL": "usuario" if random.random() < 0.95 else "admin",
        "NOMBRE": nombre,
        "APELLIDO": apellido,
        "EMAIL": email,
        "FECHA_NACIMIENTO": fake.date_of_birth(minimum_age=26, maximum_age=66).strftime('%Y-%m-%d'),
        "WHATSAPP": f"+569{fake.random_number(digits=8, fix_len=True)}",
        "REGION": region,
        "COMUNA": comuna,
        "REGISTRO_COMPLETO": "Sí" if random.random() < 0.8 else "No",
        "ACEPTA_TERMINOS": "Sí" if random.random() < 0.95 else "No",
        "FECHA_CREACION": fecha_creacion.strftime('%Y-%m-%d %H:%M:%S'),
        "GENERO": random.choices(["Masculino", "Femenino", "Otro"], weights=[0.45, 0.50, 0.05], k=1)[0],
        "CUANTAS_PERSONAS_VIVES": random.randint(1, 8),
        "PERTENECES_COMITE_VIVIENDA": "Sí" if random.random() < 0.35 else "No",
        "SITUACION_HABITACIONAL": random.choice(SITUACION_HABITACIONAL),
        "ESTADO": "activo" if random.random() < 0.9 else "inactivo",
        "CAMPOS_COMPLETOS": "Sí" if random.random() < 0.8 else "No",
        "FECHA": fecha_creacion.strftime('%Y-%m-%d') if random.random() > 0.6 else "",
        "PASO 2 COMPLETO": "Sí" if random.random() < 0.5 else "No",
        "PROVEEDOR REGISTRO": random.choice(PROVEEDOR_REGISTRO)
    })
    emails_registro.add(email)

df_registro = pd.DataFrame(data_registro)

# Problemas de calidad para registro_rcv
# 5 filas con EMAIL vacío o inválido
for idx in df_registro.sample(n=3).index:
    df_registro.loc[idx, "EMAIL"] = ""
for idx in df_registro.sample(n=2).index:
    df_registro.loc[idx, "EMAIL"] = "emailinvalido"
# 3 filas con NOMBRE en mayúsculas
for idx in df_registro.sample(n=3).index:
    df_registro.loc[idx, "NOMBRE"] = df_registro.loc[idx, "NOMBRE"].upper()
# 4 emails duplicados
duplicated_emails = df_registro.sample(n=4)["EMAIL"].tolist()
for i, idx in enumerate(df_registro.sample(n=4).index):
    df_registro.loc[idx, "EMAIL"] = duplicated_emails[i]
# 2 filas con espacios extra en EMAIL
for idx in df_registro.sample(n=2).index:
    df_registro.loc[idx, "EMAIL"] = f" {df_registro.loc[idx, 'EMAIL']} "
# Variantes de REGION
for idx in df_registro[df_registro["REGION"] == "Metropolitana de Santiago"].sample(frac=0.2).index:
    df_registro.loc[idx, "REGION"] = "RM"
for idx in df_registro[df_registro["REGION"] == "Metropolitana de Santiago"].sample(frac=0.2).index:
    df_registro.loc[idx, "REGION"] = "metropolitana"

df_registro.to_csv(f"{OUTPUT_DIR}/registro_rcv.csv", index=False, encoding='utf-8-sig')
print("registro_rcv.csv generado.")

# --- 2. Generación de 'talleres.csv' ---
print("Generando talleres.csv...")
emails_validos_registro = [e for e in emails_registro if '@' in e]
emails_para_talleres = random.sample(emails_validos_registro, k=min(40, len(emails_validos_registro)))
data_talleres = []
emails_talleres = set(emails_para_talleres)

for i in range(NUM_TALLERES):
    if i < len(emails_para_talleres):
        email = emails_para_talleres[i]
        member_id_base = df_registro[df_registro["EMAIL"] == email]["MEMBER_ID"].iloc[0] if not df_registro[df_registro["EMAIL"] == email].empty else f"RCV-9{i:03d}"
        member_id = f"MEM-{member_id_base.split('-')[1]}"
        nombre_pantalla = df_registro[df_registro["EMAIL"] == email]["NOMBRE"].iloc[0] if not df_registro[df_registro["EMAIL"] == email].empty else fake.first_name()
    else:
        nombre = fake.first_name()
        apellido = fake.last_name()
        email = f"{nombre.lower()}.{apellido.lower()}.new@{random.choice(['gmail.com', 'hotmail.com'])}"
        member_id = f"MEM-N{i:03d}"
        nombre_pantalla = f"{nombre} {apellido.split()[0]}"
        emails_talleres.add(email)

    data_talleres.append({
        "TALLER_ENTRY_ID": f"ENTRY-{i+1:04d}",
        "TALLER_TITLE": random.choice(TALLER_TITLES),
        "TALLER_URL": f"http://deficitcero.cl/talleres/{random.randint(1,4)}",
        "MEMBER_ID": member_id,
        "MEMBER_SCREEN_NAME": nombre_pantalla,
        "MEMBER_EMAIL": email,
        "MEMBER_URL": f"http://comunidad.deficitcero.cl/u/{random.randint(1000,9999)}",
        "FORMULARIO_ENTRY_ID": f"FORM-{i+1:04d}",
        "FORMULARIO_URL": f"http://forms.deficitcero.cl/f/{random.randint(100,999)}",
        "FORMULARIO_STATUS": random.choices(["completado", "pendiente", "cancelado"], weights=[0.8, 0.15, 0.05], k=1)[0],
        "FORMULARIO_ENTRY_DATE": fake.date_time_between(start_date=datetime(2024,1,1), end_date=datetime(2026,5,20)).strftime('%Y-%m-%d'),
        "PREGUNTAS - RESPUESTAS": json.dumps({"pregunta_1": "respuesta", "asistira_presencial": random.choice(["Sí", "No"])})
    })

df_talleres = pd.DataFrame(data_talleres)

# Problemas de calidad para talleres
for idx in df_talleres.sample(n=3).index:
    df_talleres.loc[idx, "MEMBER_EMAIL"] = ""
for idx in df_talleres.sample(n=2).index:
    email = df_talleres.loc[idx, "MEMBER_EMAIL"]
    if email:
        df_talleres.loc[idx, "MEMBER_EMAIL"] = email.capitalize()

df_talleres.to_csv(f"{OUTPUT_DIR}/talleres.csv", index=False, encoding='utf-8-sig')
print("talleres.csv generado.")

# --- 3. Generación de 'historial_analizado.csv' ---
print("Generando historial_analizado.csv...")
emails_para_minga_reg = random.sample(list(emails_registro), k=min(25, len(emails_registro)))
emails_para_minga_tal = random.sample(list(emails_talleres - set(emails_para_minga_reg)), k=min(15, len(emails_talleres - set(emails_para_minga_reg))))
emails_minga = set(emails_para_minga_reg + emails_para_minga_tal)
data_minga = []

for i in range(NUM_MINGA):
    if i < len(emails_minga):
        email = list(emails_minga)[i]
    else:
        email = f"new.user.{i}@chatbot.com"

    data_minga.append({
        "conv_id": f"CONV-{i+1:04d}",
        "date": fake.date_between(start_date=datetime(2024,6,1), end_date=datetime(2026,5,31)).strftime('%Y-%m-%d'),
        "transcript": fake.text(max_nb_chars=random.randint(50, 100)),
        "num_msgs": random.randint(3, 25),
        "email_usuario": email,
        "preguntas_usuario": json.dumps(fake.words(nb=random.randint(1,4))),
        "resumen": fake.sentence(),
        "subsidio_recomendado": random.choice(SUBSIDIOS),
        "rsh": random.choice(RSH),
        "con_quien_postula": random.choice(["Solo", "Cónyuge", "Familia", "Otros"]),
        "edad": random.randint(18, 70),
        "tiene_propiedad": random.choice(["Sí", "No"]),
        "tiene_subsidio_habitacional": random.choice(["Sí", "No"]),
        "nacionalidad": random.choices(NACIONALIDADES, weights=[0.85, 0.08, 0.04, 0.03], k=1)[0],
        "ingresos": random.choice(INGRESOS),
        "ahorro": random.choice(["$500.000", "$1.000.000", "$2.000.000", "Sin ahorro formal"])
    })

df_minga = pd.DataFrame(data_minga)

# Problemas de calidad para minga
for idx in df_minga.sample(n=4).index:
    df_minga.loc[idx, "email_usuario"] = random.choice(["", None])
for idx in df_minga.sample(n=2).index:
    df_minga.loc[idx, "edad"] = f"{df_minga.loc[idx, 'edad']} años"

df_minga.to_csv(f"{OUTPUT_DIR}/historial_analizado.csv", index=False, encoding='utf-8-sig')
print("historial_analizado.csv generado.")

# --- 4. Generación de 'zoom_asistencia.csv' ---
print("Generando zoom_asistencia.csv...")
emails_para_zoom_tal = random.sample(list(emails_talleres), k=min(30, len(emails_talleres)))
emails_zoom = set(emails_para_zoom_tal)
data_zoom = []

for i in range(NUM_ZOOM):
    if i < 5: # 5 sin email
        email = ""
        nombre = fake.first_name()
    elif i < 35: # 30 de talleres
        email = list(emails_zoom)[i-5]
        nombre = fake.name()
    else: # 10 nuevos
        email = f"guest.{i}@zoom.com"
        nombre = fake.name()

    hora_entrada_dt = datetime(2026, 5, 25, 9, 0, 0) + timedelta(minutes=random.randint(0, 75), seconds=random.randint(0,59))
    hora_salida_dt = datetime(2026, 5, 25, 10, 30, 0) + timedelta(minutes=random.randint(0, 30), seconds=random.randint(0,59))
    duracion = max(0, (hora_salida_dt - hora_entrada_dt).seconds // 60)

    data_zoom.append({
        "Nombre (nombre original)": nombre,
        "Correo electrónico": email,
        "Hora de entrada": hora_entrada_dt.strftime('%H:%M:%S'),
        "Hora de salida": hora_salida_dt.strftime('%H:%M:%S'),
        "Duración (minutos)": duracion,
        "Invitado": "Sí" if email == "" else "No",
        "Respuesta al descargo de responsabilidad relativa a la grabación": "Acepto" if random.random() > 0.1 else "",
        "En sala de espera": random.choice(["Sí", "No"])
    })

df_zoom = pd.DataFrame(data_zoom)

# Problemas de calidad para zoom
for idx in df_zoom.sample(n=2).index:
    df_zoom.loc[idx, "Nombre (nombre original)"] = df_zoom.loc[idx, "Nombre (nombre original)"].split()[0]
for idx in df_zoom.sample(n=1).index:
    email = df_zoom.loc[idx, "Correo electrónico"]
    if email:
        df_zoom.loc[idx, "Correo electrónico"] = email.upper()

df_zoom.to_csv(f"{OUTPUT_DIR}/zoom_asistencia.csv", index=False, encoding='utf-8-sig')
print("zoom_asistencia.csv generado.")

print("\n¡Generación de todos los datasets completada!")

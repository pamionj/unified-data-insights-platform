from scripts.extractors.talleres_extractor import TalleresExtractor
df = TalleresExtractor().extract()

print("Filas totales extraídas:       ", len(df))
print("FORMULARIO_ENTRY_ID únicos:    ", df['formulario_entry_id'].nunique())
print("MEMBER_EMAIL únicos:           ", df['email'].nunique())
print("MEMBER_ID únicos:              ", df['member_id'].nunique())
print("TALLER_ENTRY_ID únicos:        ", df['taller_entry_id'].nunique())
print("Filas con email nulo:          ", df['email'].isna().sum())
print("Filas con formulario_id nulo:  ", df['formulario_entry_id'].isna().sum())
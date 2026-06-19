# Laudus → Google Sheets Sync (legacy)

> **DEPRECATED como path de rutina (Story 9.11).** Beancount es el source of truth; el sync a Sheets se discontinúa. Este módulo (`pipeline/sync.py`) se **retiene como fallback de disaster-recovery** para re-importar histórico de Laudus si fuera necesario. Doc re-homeada desde el `README.txt` borrado en 9.11.

## Descripción
Sincroniza datos contables (Balance y Libro Mayor) desde la API de Laudus ERP hacia Google Sheets. Obtiene la última fecha sincronizada, consulta los datos correspondientes e inserta filas previniendo duplicados en la Spreadsheet compartida.

## Estructura
- `pipeline/sync.py`: Script principal de ejecución. Lógica central de sincronización. Se invoca con `python -m pipeline.sync`.
- `pipeline/utils/dates.py`: Cálculo de rangos de fechas (inicio y fin del próximo mes a consultar).
- `pipeline/config/laudus_config.py`: Credenciales y generación de URLs/parámetros (endpoints) para Laudus.
- `pipeline/config/gspread_config.py`: Credenciales de Google Service Account y acceso a la hoja de Google Sheets.
- `pipeline/utils/gspread_utils.py`: Sincronización optimizada ('upsert' en memoria) para prevenir registros duplicados en Sheets.
- `pipeline/services/laudus_service.py`: Servicio base para autenticación, tokens y peticiones HTTP GET genéricas hacia la API.
- `pipeline/services/balance_sheet_service.py` & `pipeline/services/ledger_service.py`: Wrappers para consumir dominios específicos.

## Requisitos
1. Python 3.9+
2. Instalar dependencias: `pip install -r pipeline/requirements.txt`
3. Configurar un archivo `.env` en la raíz del proyecto con:
   - `LAUDUS_USERNAME`
   - `LAUDUS_PASSWORD`
   - `LAUDUS_COMPANYVATID`
   - `GOOGLE_APPLICATION_CREDENTIALS`: Ruta del JSON de la Service Account (ej: `pipeline/config/serviceAccountKey.json`).
   - `GOOGLE_SHEET_ID`: El ID de la spreadsheet (se extrae de la URL del Google Sheet).

## Ejecución
```
python -m pipeline.sync
```
Si el script intenta consultar registros para fechas futuras de manera anticipada, se detiene previniendo comportamientos indeseados y muestra un "error de fecha".

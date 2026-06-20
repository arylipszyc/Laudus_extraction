# Laudus API Sync Project

## Descripción
Este proyecto sincroniza datos contables (Balance y Libro Mayor) desde la API de Laudus ERP hacia Google Sheets. Utiliza un script en Python que obteniene la última fecha sincronizada, consulta los datos correspondientes e inserta filas previniendo duplicados en tu SpreadSheet compartida.

## Estructura del Proyecto
- `sync.py`: Script principal de ejecución. Mantiene la lógica central de sincronización.
- `utils/dates.py`: Módulo utilitario para el cálculo de rangos de fechas (inicio y fin del próximo mes a consultar).
- `config/laudus_config.py`: Configuración de credenciales y generación de las URLs y parámetros (endpoints) para Laudus.
- `config/gspread_config.py`: Configuración de credenciales de Google Service Account y acceso a la hoja de Google Sheets.
- `utils/gspread_utils.py`: Lógica de sincronización optimizada ('upsert' en memoria) para prevenir registros duplicados en Sheets.
- `services/laudus_service.py`: Servicio base para manejar la autenticación, tokens y peticiones HTTP GET genéricas hacia la API.
- `services/balance_sheet_service.py` & `services/ledger_service.py`: Wrappers diseñados para consumir dominios específicos.

## Requisitos
1. Python 3.9+
2. Instalar los paquetes correspondientes (p.ej.: `requests`, `python-dotenv`, `gspread`, etc).
3. Asegurarse de tener configurado un archivo `.env` en la raíz del proyecto con el siguiente contenido:
   - LAUDUS_USERNAME
   - LAUDUS_PASSWORD
   - LAUDUS_COMPANYVATID
   - GOOGLE_APPLICATION_CREDENTIALS: Ruta del archivo JSON de tu Service Account (ej: `GOOGLE_APPLICATION_CREDENTIALS=config/serviceAccountKey.json`).
   - GOOGLE_SHEET_ID: El ID de tu hoja de cálculo (se extrae de la URL de tu Google Sheet).

## Ejecución
Ejecute el pipeline principal mediante:
python sync.py

Si el script intenta consultar registros para fechas en el futuro de manera anticipada, se detendrá previniendo comportamientos indeseados y mostrará un "error de fecha".

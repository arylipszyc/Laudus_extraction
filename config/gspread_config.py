import logging
import os

import gspread
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_gspread_client():
    """Inicializa y retorna un cliente de gspread usando el service account."""
    try:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path:
            cred_path = cred_path.strip("'\"")
        if not cred_path or not os.path.exists(cred_path):
            logger.error(
                "No se encontró el archivo de credenciales de Google Service Account en: %s",
                cred_path,
            )
            return None
        return gspread.service_account(filename=cred_path)
    except Exception as e:
        logger.error("Error al inicializar gspread: %s", e)
        return None


def get_spreadsheet():
    """Retorna el documento de Google Sheets listo para leer o escribir."""
    gc = get_gspread_client()
    if not gc:
        return None

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        logger.error("La variable GOOGLE_SHEET_ID no está definida en .env")
        return None
    sheet_id = sheet_id.strip("'\"")

    try:
        return gc.open_by_key(sheet_id)
    except Exception as e:
        logger.error(
            "Error al abrir el documento '%s': %s. "
            "Verifica que la planilla esté compartida con el Service Account.",
            sheet_id, repr(e),
        )
        return None

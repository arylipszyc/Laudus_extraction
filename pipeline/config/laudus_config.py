import os
import dotenv

dotenv.load_dotenv()

# ──────────────────────────────────────────────
# URLs base de la API
# ──────────────────────────────────────────────
LOGIN_URL          = "https://api.laudus.cl/security/login"
BALANCE_SHEET_URL  = "https://api.laudus.cl/accounting/balanceSheet/totals"
LEDGER_URL         = "https://api.laudus.cl/accounting/ledger"

# ──────────────────────────────────────────────
# Autenticación
# ──────────────────────────────────────────────
default_headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
payload = {
    "userName":     os.environ.get("LAUDUS_USERNAME"),
    "password":     os.environ.get("LAUDUS_PASSWORD"),
    "companyVATId": os.environ.get("LAUDUS_COMPANYVATID"),
}


def get_endpoints(date_from, date_to):
    """Devuelve URLs y parámetros de los endpoints principales para el rango dado."""
    return {
        "GET_LEDGER": {
            "url":    LEDGER_URL,
            "params": {"dateFrom": str(date_from), "dateTo": str(date_to)},
        },
        "GET_BALANCE_SHEET": {
            "url":    BALANCE_SHEET_URL,
            "params": {"dateTo": str(date_to)},
        },
    }

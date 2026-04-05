import os
import gspread
import traceback
from dotenv import load_dotenv

load_dotenv()
try:
    gc = gspread.service_account(filename=os.getenv('GOOGLE_APPLICATION_CREDENTIALS').strip('\'"'))
    print("Service account loaded")
    gc.open_by_key(os.getenv('GOOGLE_SHEET_ID').strip('\'"'))
    print("SUCCESS")
except Exception as e:
    traceback.print_exc()

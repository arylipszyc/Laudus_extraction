import logging

logger = logging.getLogger(__name__)


def _cell_value(val):
    """Preserva int/float para que Google Sheets los interprete como números."""
    if val is None or val == "":
        return ""
    if isinstance(val, (int, float)):
        return val
    return str(val)


def upsert_to_sheet(spreadsheet, sheet_name, data_list, primary_key_func, headers):
    """
    Esta función actualiza o inserta registros en una pestaña de Google Sheets
    evitando duplicados mediante una clave primaria en memoria.
    
    :param spreadsheet: Objeto Spreadsheet de gspread.
    :param sheet_name: String, nombre de la pestaña.
    :param data_list: Lista de diccionarios, los nuevos registros a insertar.
    :param primary_key_func: Función que toma un diccionario (fila) y devuelve un string único.
    :param headers: Lista de strings, determinan las columnas a escribir en formato de cabecera.
    """
    # 1. Asegurarse que la pestaña exista
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except Exception:  # gspread.exceptions.WorksheetNotFound
        # Calcular cuantas columnas necesitamos
        ws = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols=str(len(headers) + 5))
        ws.append_row(headers)
        
    # 2. Descargar todos los registros existentes
    existing_data = ws.get_all_records()
    
    # 3. Transformarlos en un diccionario utilizando la clave primaria
    data_dict = {}
    for row in existing_data:
        if not any(row.values()): 
            continue # Saltar filas completamente vacías
        try:
            pk = primary_key_func(row)
            data_dict[pk] = row
        except KeyError:
            pass # Si falta algún campo clave, se ignora
            
    # 4. Mezclar el diccionario en memoria con los nuevos registros traídos
    for item in data_list:
        pk = primary_key_func(item)
        data_dict[pk] = item
        
    # 5. Formatear los datos como listas de listas para subirlos de una sola vez
    rows_to_write = [headers]
    for pk, row in data_dict.items():
        # Preservar tipos numéricos para que Google Sheets no los trate como texto
        rows_to_write.append([_cell_value(row.get(h, "")) for h in headers])
        
    # 6. Sobreescribir toda la pestaña (este 'Clear' seguido del 'Update' es la técnica nativa de volcado en lote)
    logger.info("Subiendo %d filas únicas a la pestaña '%s'...", len(rows_to_write) - 1, sheet_name)
    ws.clear()
    
    # USER_ENTERED permite que Google Sheets interprete números como números y fechas como fechas
    ws.update(values=rows_to_write, range_name="A1", value_input_option="USER_ENTERED")


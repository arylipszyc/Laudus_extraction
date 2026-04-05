import logging

logger = logging.getLogger(__name__)


def _cell_value(val):
    """Preserva int/float para que Google Sheets los interprete como números."""
    if val is None or val == "":
        return ""
    if isinstance(val, (int, float)):
        return val
    return str(val)


def safe_write(ws, rows_to_write, backup_rows, sheet_name):
    """
    Ejecuta clear() + update() protegiendo contra pérdida de datos.
    Si el update falla después del clear, restaura automáticamente el backup.
    """
    ws.clear()
    try:
        ws.update(values=rows_to_write, range_name="A1", value_input_option="USER_ENTERED")
    except Exception as e:
        logger.error(
            "Fallo al escribir en '%s' después de clear(). Restaurando %d filas previas...",
            sheet_name, len(backup_rows),
        )
        if backup_rows:
            ws.update(values=backup_rows, range_name="A1", value_input_option="USER_ENTERED")
        raise


def upsert_to_sheet(spreadsheet, sheet_name, data_list, primary_key_func, headers):
    """
    Actualiza o inserta registros en una pestaña de Google Sheets evitando duplicados
    mediante una clave primaria en memoria.

    Retorna la lista de dicts merged (útil para reusar en memoria sin releer el sheet).

    :param spreadsheet: Objeto Spreadsheet de gspread.
    :param sheet_name: String, nombre de la pestaña.
    :param data_list: Lista de diccionarios, los nuevos registros a insertar.
    :param primary_key_func: Función que toma un dict (fila) y devuelve un string único.
    :param headers: Lista de strings que determinan las columnas a escribir.
    """
    # 1. Asegurarse que la pestaña exista
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except Exception:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols=str(len(headers) + 5))
        ws.append_row(headers)

    # 2. Descargar todos los registros existentes
    existing_data = ws.get_all_records()

    # 3. Construir diccionario en memoria con clave primaria
    data_dict = {}
    for row in existing_data:
        if not any(row.values()):
            continue
        try:
            pk = primary_key_func(row)
            data_dict[pk] = row
        except KeyError:
            pass

    # 4. Mezclar con los nuevos registros (nuevos sobreescriben por clave)
    for item in data_list:
        pk = primary_key_func(item)
        data_dict[pk] = item

    # 5. Formatear como lista de listas
    rows_to_write = [headers]
    for row in data_dict.values():
        rows_to_write.append([_cell_value(row.get(h, "")) for h in headers])

    # 6. Backup construido desde existing_data ya cargado (sin llamada extra a la API)
    backup_rows = [headers] + [
        [_cell_value(row.get(h, "")) for h in headers] for row in existing_data
    ]

    logger.info("Subiendo %d filas únicas a la pestaña '%s'...", len(rows_to_write) - 1, sheet_name)
    safe_write(ws, rows_to_write, backup_rows, sheet_name)

    # Retornar los registros merged como lista de dicts para reusar en memoria
    return list(data_dict.values())


def replace_sheet(spreadsheet, sheet_name, data_list, headers):
    """
    Reemplaza el contenido completo de una pestaña sin deduplicación.
    Más eficiente que upsert_to_sheet para hojas _final donde siempre se reescribe todo.
    Protege contra pérdida de datos: restaura si el update falla tras el clear.

    :param spreadsheet: Objeto Spreadsheet de gspread.
    :param sheet_name: String, nombre de la pestaña.
    :param data_list: Lista de dicts con los datos a escribir.
    :param headers: Lista de strings que determinan las columnas.
    """
    try:
        ws = spreadsheet.worksheet(sheet_name)
        backup_rows = ws.get_all_values()  # backup del estado actual
    except Exception:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols=str(len(headers) + 5))
        backup_rows = []

    rows_to_write = [headers]
    for row in data_list:
        rows_to_write.append([_cell_value(row.get(h, "")) for h in headers])

    logger.info("Reemplazando %d filas en la pestaña '%s'...", len(rows_to_write) - 1, sheet_name)
    safe_write(ws, rows_to_write, backup_rows, sheet_name)

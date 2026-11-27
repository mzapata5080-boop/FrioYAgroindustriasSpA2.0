"""Generación de hojas Excel con protección frente a fórmulas en texto."""
import json
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def _cell_value(value):
    if isinstance(value, (date, datetime, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    if value is None:
        return ''
    text = str(value)
    if text.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
        return "'" + text
    return text


def build_excel(title, columns, rows):
    workbook = Workbook()
    workbook.properties.title = title
    sheet = workbook.active
    sheet.title = 'Reporte'
    sheet.append([_cell_value(label) for _, label in columns])
    for row in rows:
        sheet.append([_cell_value(row.get(key)) for key, _ in columns])

    header_fill = PatternFill('solid', fgColor='1F2937')
    for cell in sheet[1]:
        cell.font = Font(color='FFFFFF', bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(vertical='top', wrap_text=True)
    for column_index, (key, label) in enumerate(columns, start=1):
        values = [str(label)] + [
            str(row.get(key) if row.get(key) is not None else '')
            for row in rows[:500]
        ]
        width = min(max(max((len(value) for value in values), default=0) + 2, 12), 42)
        sheet.column_dimensions[get_column_letter(column_index)].width = width
    sheet.freeze_panes = 'A2'
    if columns and rows:
        sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()

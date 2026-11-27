"""Generación de reportes PDF reutilizando filas y columnas filtradas."""
from io import BytesIO
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _paragraph_text(value):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))
    return escape(text)


def build_pdf(title, columns, rows):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A3),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle(
        'ReportCell',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=6 if len(columns) > 12 else 8,
        leading=8 if len(columns) > 12 else 10,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    header_style = ParagraphStyle(
        'ReportHeader',
        parent=cell_style,
        fontName='Helvetica-Bold',
        textColor=colors.white,
    )
    table_data = [[Paragraph(_paragraph_text(label), header_style) for _, label in columns]]
    for row in rows:
        table_data.append([
            Paragraph(_paragraph_text(row.get(key) if row.get(key) is not None else ''), cell_style)
            for key, _ in columns
        ])

    content = [Paragraph(_paragraph_text(title), styles['Title']), Spacer(1, 5 * mm)]
    if not rows:
        content.append(Paragraph('Sin registros para los filtros seleccionados.', styles['BodyText']))
    else:
        available_width = document.width
        column_width = available_width / max(len(columns), 1)
        table = Table(
            table_data,
            colWidths=[column_width] * len(columns),
            repeatRows=1,
            hAlign='LEFT',
        )
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        content.append(table)
    document.build(content)
    return buffer.getvalue()

"""Endpoints de solo lectura para panel, alertas y exportaciones."""
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, F, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from finanzas.models import Cliente, DocumentoVenta, Proveedor
from frio_agroindustria.api_common import (
    allowed,
    error,
    permission_denied,
    serialize,
)
from frio_agroindustria.api_resources import RESOURCES
from inventario.api import serialize as serialize_movement
from inventario.models import MovimientoBodega, Repuesto
from obras.api import (
    SUPERVISOR_ROLES,
    obras_queryset_for,
    serialize_obra,
    serialize_solicitud,
)
from obras.models import Obra, SolicitudMaterial

from .excel import build_excel
from .filters import (
    InvalidReportFilter,
    filter_kardex_items,
    filter_queryset,
    filter_search,
)
from .pdf import build_pdf


REPORT_COLUMNS = {
    'clientes': (
        'rut', 'razon_social', 'telefono', 'correo', 'direccion',
        'representante', 'cargo_contacto', 'creado_el',
    ),
    'proveedores': (
        'rut', 'razon_social', 'giro', 'telefono', 'email', 'direccion',
        'encargado_pagos', 'correo_pagos', 'banco', 'tipo_cuenta',
        'numero_cuenta', 'creado_el',
    ),
    'facturas': (
        'id', 'proveedor', 'fecha', 'numero_documento', 'tipo_documento',
        'monto', 'observaciones', 'creado_el', 'descuento_general',
        'descuento_pronto_pago', 'tasa_iva', 'proveedor_nombre',
        'detalle_count', 'detalles_bloqueados',
    ),
    'articulos': (
        'codigo_parte', 'descripcion', 'categoria_nombre', 'ubicacion_bodega',
        'unidad_medida_display', 'stock_actual', 'stock_reservado',
        'stock_minimo', 'activo',
    ),
    'kardex': (
        'id', 'fecha_registro', 'clase_movimiento', 'articulo', 'cantidad',
        'unidad_medida', 'variacion_stock_bodega', 'costo_total_fifo',
        'obra_codigo', 'cliente_nombre', 'receptor', 'responsable', 'destino',
        'motivo_operacion', 'referencia_movimiento', 'referencia_operacion',
        'referencia_lote', 'observaciones',
    ),
    'obras': (
        'codigo_ot', 'nombre', 'cliente_nombre', 'tipo_servicio', 'estado',
        'presupuesto_estimado', 'supervisor_nombre', 'fecha_inicio',
    ),
    'solicitudes': (
        'id', 'obra_codigo', 'articulo_nombre', 'cantidad_solicitada',
        'cantidad_reservada', 'cantidad_entregada', 'unidad_medida',
        'solicitado_por_nombre', 'estado',
    ),
}

REPORT_TITLES = {
    'clientes': 'Reporte de clientes',
    'proveedores': 'Reporte de proveedores',
    'facturas': 'Reporte de facturas de compra',
    'articulos': 'Reporte de inventario',
    'kardex': 'Reporte de Kardex',
    'obras': 'Reporte de obras',
    'solicitudes': 'Reporte de solicitudes de materiales',
}

MOVEMENT_LABELS = {
    'INGRESO': 'Ingreso',
    'SALIDA': 'Egreso',
    'AJUSTE': 'Ajuste',
    'DEVOLUCION': 'Devolución',
    'MERMA_BODEGA': 'Merma en bodega',
    'MERMA_OBRA': 'Merma en obra',
    'DEV_BODEGA': 'Devolución a bodega',
    'DEV_PROVEEDOR': 'Devolución a proveedor',
    'USO_INTERNO': 'Uso interno',
    'CAMBIO': 'Ajuste por cambio de artículo',
    'ANULAR': 'Ajuste compensatorio (anulación)',
}


def _format_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    rendered = f'{amount:,.2f}'
    integer, fraction = rendered.split('.')
    fraction = fraction.rstrip('0')
    rendered = integer.replace(',', '.')
    if fraction:
        rendered += ',' + fraction
    return f'${rendered} CLP'


def _display_value(resource, key, item):
    value = item.get(key)
    if value is None:
        return '—'
    if key == 'activo':
        return 'Activo' if value else 'Inactivo'
    if isinstance(value, bool):
        return 'Sí' if value else 'No'
    if resource == 'kardex' and key == 'clase_movimiento':
        return MOVEMENT_LABELS.get(value, value or '—')
    if resource == 'kardex' and key == 'variacion_stock_bodega':
        try:
            number = Decimal(str(value))
            rendered = format(number.normalize(), 'f')
            return f'+{rendered}' if number > 0 else rendered
        except (InvalidOperation, ValueError):
            return '—'
    if key == 'fecha_registro':
        occurred = value if hasattr(value, 'strftime') else parse_datetime(str(value))
        if occurred is None:
            return str(value)
        if timezone.is_aware(occurred):
            occurred = timezone.localtime(occurred)
        return occurred.strftime('%d-%m-%Y %H:%M')
    if key in {
        'monto', 'costo_total_fifo', 'presupuesto_estimado',
        'monto_materiales_estimado', 'monto_mano_obra_estimado',
        'total_estimado', 'total', 'saldo', 'precio_unitario', 'subtotal',
    }:
        return _format_amount(value)
    if resource == 'articulos' and key == 'stock_actual':
        stock = Decimal(str(value))
        minimum = Decimal(str(item.get('stock_minimo') or 0))
        return f'{value} (Bajo)' if stock <= minimum else str(value)
    return str(value)


def _display_rows(resource, columns, rows):
    return [
        {
            key: _display_value(resource, key, item)
            for key, _ in columns
        }
        for item in rows
    ]


def _report_allowed(user, resource):
    if resource == 'articulos':
        return user.is_authenticated
    if resource == 'kardex':
        return allowed(user, ('gerencia',))
    if resource == 'obras':
        return allowed(user, ('gerencia', 'bodega', 'finanzas', *SUPERVISOR_ROLES))
    if resource == 'solicitudes':
        return allowed(user, ('gerencia', 'bodega', *SUPERVISOR_ROLES))
    if resource in RESOURCES:
        return allowed(user, RESOURCES[resource][2])
    return False


def _report_items(request, resource):
    if resource == 'articulos':
        queryset = Repuesto.objects.select_related('categoria').order_by('pk')
        queryset = filter_queryset(resource, queryset, request.GET)
        return [serialize(item) for item in queryset]

    if resource == 'kardex':
        from inventario.operaciones_api import enriquecer_kardex

        queryset = (
            MovimientoBodega.objects.select_related(
                'repuesto', 'responsable', 'receptor', 'obra', 'cliente',
                'recepcioningreso__responsable', 'devolucion_fifo__consumo',
                'detalle_recepcion_compra__recepcion',
            )
            .prefetch_related('detalles_fifo__lote')
            .order_by('-fecha_registro', '-pk')
        )
        rows = [serialize_movement(item) for item in queryset]
        enriquecer_kardex(rows)
        return filter_kardex_items(rows, request.GET)

    if resource == 'obras':
        queryset = obras_queryset_for(request.user)
        queryset = filter_queryset(resource, queryset, request.GET)
        return [serialize_obra(item) for item in queryset]

    if resource == 'solicitudes':
        queryset = (
            SolicitudMaterial.objects.select_related(
                'obra__cliente', 'obra__supervisor', 'articulo',
                'solicitado_por', 'aprobado_por',
            )
            .filter(obra__in=obras_queryset_for(request.user))
            .order_by('-creado_el', '-pk')
        )
        queryset = filter_queryset(resource, queryset, request.GET)
        return [serialize_solicitud(item) for item in queryset]

    model = RESOURCES[resource][0]
    queryset = model.objects.order_by('pk')
    if resource == 'facturas':
        queryset = queryset.select_related('proveedor').prefetch_related(
            'detalles__articulo', 'detalles__recepciones', 'recepciones_compra',
        )
    queryset = filter_queryset(resource, queryset, request.GET)
    return [serialize(item) for item in queryset]


def _requested_columns(request, resource, rows):
    raw = request.GET.get('columns')
    if not raw:
        available = set(rows[0]) if rows else set(REPORT_COLUMNS[resource])
        keys = [key for key in REPORT_COLUMNS[resource] if key in available]
        return [(key, key.replace('_', ' ').capitalize()) for key in keys]
    try:
        requested = json.loads(raw)
    except (TypeError, ValueError):
        raise InvalidReportFilter('Las columnas del reporte no son válidas.')
    if not isinstance(requested, list) or len(requested) > 30:
        raise InvalidReportFilter('Las columnas del reporte no son válidas.')
    if not requested:
        if not rows:
            return []
        available = set(rows[0])
        keys = [key for key in REPORT_COLUMNS[resource] if key in available]
        return [(key, key.replace('_', ' ').capitalize()) for key in keys]
        return []
    allowed_columns = set(REPORT_COLUMNS[resource])
    columns = []
    for column in requested:
        if not isinstance(column, dict):
            raise InvalidReportFilter('Las columnas del reporte no son válidas.')
        key = column.get('key')
        label = column.get('label')
        if not isinstance(key, str) or key not in allowed_columns or not isinstance(label, str):
            raise InvalidReportFilter('Las columnas del reporte no son válidas.')
        columns.append((key, label.strip()[:100] or key))
    return columns


@require_GET
def export_report(request, resource, file_format):
    if not request.user.is_authenticated:
        return error('Inicia sesión.', 401)
    if resource not in REPORT_TITLES or not _report_allowed(request.user, resource):
        return permission_denied()
    if file_format not in ('pdf', 'xlsx', 'excel'):
        return error('Formato de reporte no disponible.', 404)
    try:
        items = _report_items(request, resource)
        items = filter_search(items, request.GET.get('q'))
        columns = _requested_columns(request, resource, items)
    except InvalidReportFilter as exc:
        return error(str(exc), 400)
    displayed_items = _display_rows(resource, columns, items)

    if file_format == 'pdf':
        content = build_pdf(REPORT_TITLES[resource], columns, displayed_items)
        content_type = 'application/pdf'
        extension = 'pdf'
    else:
        content = build_excel(REPORT_TITLES[resource], columns, displayed_items)
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        extension = 'xlsx'
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{resource}.{extension}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@require_GET
def dashboard(request):
    if not request.user.is_authenticated:
        return error('Inicia sesión.', 401)
    if not allowed(request.user, ('gerencia',)):
        return permission_denied()

    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_movements = MovimientoBodega.objects.filter(
        fecha_registro__date__gte=month_start,
        fecha_registro__date__lte=today,
    )
    start = today - timedelta(days=29)
    grouped = (
        MovimientoBodega.objects.filter(
            fecha_registro__date__gte=start,
            fecha_registro__date__lte=today,
        )
        .annotate(dia=TruncDate('fecha_registro'))
        .values('dia')
        .annotate(
            ingresos=Count('pk', filter=Q(tipo='INGRESO')),
            salidas=Count('pk', filter=Q(tipo='SALIDA')),
        )
        .order_by('dia')
    )
    daily = {
        row['dia'].isoformat(): {
            'ingresos': row['ingresos'],
            'salidas': row['salidas'],
        }
        for row in grouped
        if row['dia'] is not None
    }
    chart = []
    for day_offset in range(30):
        day = start + timedelta(days=day_offset)
        values = daily.get(day.isoformat(), {'ingresos': 0, 'salidas': 0})
        chart.append({'fecha': day.isoformat(), **values})

    from inventario.operaciones_api import enriquecer_kardex

    recent = list(
        MovimientoBodega.objects.select_related(
            'repuesto', 'responsable', 'receptor', 'obra', 'cliente',
            'recepcioningreso__responsable',
        ).order_by('-fecha_registro', '-pk')[:8]
    )
    activities = [serialize_movement(item) for item in recent]
    enriquecer_kardex(activities)
    activities = [
        {
            'id': row.get('id'),
            'fecha': row.get('fecha_registro'),
            'tipo': row.get('clase_movimiento') or row.get('tipo'),
            'articulo': row.get('articulo'),
            'cantidad': row.get('cantidad'),
            'unidad': row.get('unidad_medida'),
            'obra': row.get('obra_codigo') or '',
            'responsable': row.get('responsable') or 'Sin registro',
        }
        for row in activities[:8]
    ]

    return JsonResponse({
        'kpis': {
            'total_articulos': Repuesto.objects.count(),
            'stock_critico': Repuesto.objects.filter(
                activo=True, stock_actual__lte=F('stock_minimo')
            ).count(),
            'ingresos_mes': month_movements.filter(tipo='INGRESO').count(),
            'salidas_mes': month_movements.filter(tipo='SALIDA').count(),
            'obras_activas': Obra.objects.exclude(estado='CERRADA').count(),
            'solicitudes_pendientes': SolicitudMaterial.objects.filter(
                estado='PENDIENTE'
            ).count(),
            'clientes_registrados': Cliente.objects.count(),
            'proveedores_registrados': Proveedor.objects.count(),
        },
        'movimientos_30_dias': chart,
        'actividades_kardex': activities,
    })


@require_GET
def alerts(request):
    if not request.user.is_authenticated:
        return error('Inicia sesión.', 401)

    user = request.user
    today = timezone.localdate()
    next_week = today + timedelta(days=7)
    groups = []

    critical = Repuesto.objects.filter(
        activo=True, stock_actual__lte=F('stock_minimo')
    ).order_by('stock_actual', 'pk')
    critical_count = critical.count()
    if critical_count:
        groups.append({
            'tipo': 'stock',
            'mensaje': 'Artículo bajo stock mínimo',
            'count': critical_count,
            'items': [{
                'id': item.pk,
                'nombre': f'{item.codigo_parte} — {item.descripcion}',
            } for item in critical[:5]],
            'resource': 'articulos',
            'filters': {'stock_bajo': '1'},
        })

    if allowed(user, ('gerencia', 'bodega', *SUPERVISOR_ROLES)):
        pending = SolicitudMaterial.objects.filter(
            estado='PENDIENTE',
            obra__in=obras_queryset_for(user),
        ).select_related('obra', 'articulo').order_by('-creado_el')
        pending_count = pending.count()
        if pending_count:
            groups.append({
                'tipo': 'solicitud',
                'mensaje': 'Solicitud pendiente de aprobación',
                'count': pending_count,
                'items': [{
                    'id': item.pk,
                    'nombre': f'{item.obra.codigo_ot} — {item.articulo.descripcion}',
                } for item in pending[:5]],
                'resource': 'solicitudes',
                'filters': {'estado': 'PENDIENTE'},
            })

    if allowed(user, ('gerencia', 'bodega', 'finanzas', *SUPERVISOR_ROLES)):
        due_works = obras_queryset_for(user).filter(
            estado__in=('PLANIFICADA', 'EN_EJECUCION', 'PAUSADA'),
            fecha_termino_estimada__gte=today,
            fecha_termino_estimada__lte=next_week,
        ).order_by('fecha_termino_estimada', 'pk')
        due_count = due_works.count()
        if due_count:
            groups.append({
                'tipo': 'obra',
                'mensaje': 'Obra próxima a vencer',
                'count': due_count,
                'items': [{
                    'id': item.pk,
                    'nombre': f'{item.codigo_ot} — vence {item.fecha_termino_estimada}',
                } for item in due_works[:5]],
                'resource': 'obras',
                'filters': {'vence_proxima': '1'},
            })

    if allowed(user, ('gerencia', 'finanzas')):
        pending_documents = filter_queryset(
            'documentos-venta',
            DocumentoVenta.objects.select_related('cliente').order_by(
                'vencimiento', 'pk'
            ),
            {'saldo_pendiente': '1'},
        )
        documents_count = pending_documents.count()
        if documents_count:
            groups.append({
                'tipo': 'documento',
                'mensaje': 'Documento pendiente',
                'count': documents_count,
                'items': [{
                    'id': item.pk,
                    'nombre': f'{item.numero_documento} — {item.cliente.razon_social}',
                } for item in pending_documents[:5]],
                'resource': 'documentos-venta',
                'filters': {'saldo_pendiente': '1'},
            })

    return JsonResponse({
        'count': sum(group['count'] for group in groups),
        'groups': groups,
    })

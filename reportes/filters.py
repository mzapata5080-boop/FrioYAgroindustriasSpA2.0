"""Filtros compartidos entre las listas del sistema y sus reportes."""
import unicodedata
from datetime import datetime
from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from inventario.models import OperacionInventario
from obras.models import Obra, SolicitudMaterial


FILTER_FIELDS = {
    'clientes': [
        {'name': 'rut', 'label': 'RUT', 'type': 'text'},
        {'name': 'razon_social', 'label': 'Razón social', 'type': 'text'},
        {'name': 'correo', 'label': 'Correo', 'type': 'text'},
    ],
    'proveedores': [
        {'name': 'rut', 'label': 'RUT', 'type': 'text'},
        {'name': 'razon_social', 'label': 'Razón social', 'type': 'text'},
        {'name': 'banco', 'label': 'Banco', 'type': 'text'},
    ],
    'facturas': [
        {'name': 'fecha_inicio', 'label': 'Fecha inicio', 'type': 'date'},
        {'name': 'fecha_termino', 'label': 'Fecha término', 'type': 'date'},
        {'name': 'proveedor', 'label': 'Proveedor', 'type': 'text'},
    ],
    'documentos-venta': [
        {
            'name': 'saldo_pendiente',
            'label': 'Saldo pendiente',
            'type': 'select',
            'choices': [['', 'Todos'], ['1', 'Pendiente'], ['0', 'Saldado']],
        },
    ],
    'articulos': [
        {'name': 'categoria', 'label': 'Categoría', 'type': 'text'},
        {
            'name': 'stock_bajo',
            'label': 'Stock bajo',
            'type': 'select',
            'choices': [['', 'Todos'], ['1', 'Sí'], ['0', 'No']],
        },
        {
            'name': 'activo',
            'label': 'Activos',
            'type': 'select',
            'choices': [['', 'Todos'], ['1', 'Activos'], ['0', 'Inactivos']],
        },
    ],
    'kardex': [
        {
            'name': 'tipo',
            'label': 'Tipo de movimiento',
            'type': 'select',
            'choices': [['', 'Todos']] + [[value, label] for value, label in (
                [('INGRESO', 'Ingreso'), ('SALIDA', 'Salida'), ('DEVOLUCION', 'Devolución')]
                + list(OperacionInventario.TIPOS)
            )],
        },
        {'name': 'fecha_inicio', 'label': 'Fecha inicio', 'type': 'date'},
        {'name': 'fecha_termino', 'label': 'Fecha término', 'type': 'date'},
    ],
    'obras': [
        {
            'name': 'estado',
            'label': 'Estado',
            'type': 'select',
            'choices': [['', 'Todos']] + [[value, label] for value, label in Obra.ESTADOS],
        },
        {'name': 'supervisor', 'label': 'Supervisor', 'type': 'text'},
        {
            'name': 'vence_proxima',
            'label': 'Vence en 7 días',
            'type': 'select',
            'choices': [['', 'Todas'], ['1', 'Sí']],
        },
    ],
    'solicitudes': [
        {
            'name': 'estado',
            'label': 'Estado',
            'type': 'select',
            'choices': [['', 'Todos']] + [[value, label] for value, label in SolicitudMaterial.ESTADOS],
        },
        {'name': 'obra', 'label': 'Obra', 'type': 'text'},
    ],
}


class InvalidReportFilter(ValueError):
    """Un valor de filtro no tiene el formato esperado."""


def _date_parameter(params, name):
    raw = (params.get(name) or '').strip()
    if not raw:
        return None
    value = parse_date(raw)
    if value is None:
        raise InvalidReportFilter(f'La fecha de {name.replace("_", " ")} no es válida.')
    return value


def filter_queryset(resource, queryset, params):
    """Aplica filtros compatibles con los modelos y devuelve el queryset filtrado."""
    if resource in ('clientes', 'proveedores'):
        for field in ('rut', 'razon_social'):
            value = (params.get(field) or '').strip()
            if value:
                queryset = queryset.filter(**{f'{field}__icontains': value})
        extra_field = 'correo' if resource == 'clientes' else 'banco'
        value = (params.get(extra_field) or '').strip()
        if value:
            queryset = queryset.filter(**{f'{extra_field}__icontains': value})

    elif resource == 'facturas':
        start = _date_parameter(params, 'fecha_inicio')
        end = _date_parameter(params, 'fecha_termino')
        if start and end and start > end:
            raise InvalidReportFilter('La fecha inicio no puede ser posterior a la fecha término.')
        if start:
            queryset = queryset.filter(fecha__gte=start)
        if end:
            queryset = queryset.filter(fecha__lte=end)
        provider = (params.get('proveedor') or '').strip()
        if provider:
            queryset = queryset.filter(
                Q(proveedor__razon_social__icontains=provider)
                | Q(proveedor__rut__icontains=provider)
            )

    elif resource == 'documentos-venta':
        pending = (params.get('saldo_pendiente') or '').strip()
        if pending == '1':
            queryset = queryset.filter(saldo__gt=0, anulado=False)
        elif pending == '0':
            queryset = queryset.filter(saldo=0, anulado=False)

    elif resource == 'articulos':
        category = (params.get('categoria') or '').strip()
        if category:
            queryset = queryset.filter(categoria__nombre__icontains=category)
        low_stock = (params.get('stock_bajo') or '').strip()
        if low_stock in ('0', '1'):
            lookup = 'stock_actual__lte' if low_stock == '1' else 'stock_actual__gt'
            queryset = queryset.filter(**{lookup: F('stock_minimo')})
        active = (params.get('activo') or '').strip()
        if active in ('0', '1'):
            queryset = queryset.filter(activo=(active == '1'))

    elif resource in ('obras', 'solicitudes'):
        state = (params.get('estado') or '').strip()
        valid_states = {value for value, _ in (
            Obra.ESTADOS if resource == 'obras' else SolicitudMaterial.ESTADOS
        )}
        if state and state not in valid_states:
            raise InvalidReportFilter('El estado seleccionado no es válido.')
        if state:
            queryset = queryset.filter(estado=state)
        if resource == 'obras':
            supervisor = (params.get('supervisor') or '').strip()
            if supervisor:
                queryset = queryset.filter(
                    Q(supervisor__username__icontains=supervisor)
                    | Q(supervisor__first_name__icontains=supervisor)
                    | Q(supervisor__last_name__icontains=supervisor)
                )
            if (params.get('vence_proxima') or '').strip() == '1':
                today = timezone.localdate()
                queryset = queryset.filter(
                    estado__in=('PLANIFICADA', 'EN_EJECUCION', 'PAUSADA'),
                    fecha_termino_estimada__gte=today,
                    fecha_termino_estimada__lte=today + timedelta(days=7),
                )
        else:
            work = (params.get('obra') or '').strip()
            if work:
                queryset = queryset.filter(
                    Q(obra__codigo_ot__icontains=work)
                    | Q(obra__nombre__icontains=work)
                )
    return queryset


def filter_kardex_items(items, params):
    """Filtra filas ya enriquecidas para incluir también operaciones virtuales."""
    start = _date_parameter(params, 'fecha_inicio')
    end = _date_parameter(params, 'fecha_termino')
    if start and end and start > end:
        raise InvalidReportFilter('La fecha inicio no puede ser posterior a la fecha término.')
    movement_type = (params.get('tipo') or '').strip()
    allowed_types = {value for value, _ in FILTER_FIELDS['kardex'][0]['choices']}
    if movement_type and movement_type not in allowed_types:
        raise InvalidReportFilter('El tipo de movimiento seleccionado no es válido.')

    filtered = []
    for item in items:
        occurred = item.get('fecha_registro')
        if isinstance(occurred, datetime):
            if timezone.is_aware(occurred):
                occurred = timezone.localtime(occurred).date()
            else:
                occurred = occurred.date()
        elif isinstance(occurred, str):
            occurred = parse_date(occurred[:10])
        if start and (occurred is None or occurred < start):
            continue
        if end and (occurred is None or occurred > end):
            continue
        if movement_type and item.get('clase_movimiento') != movement_type:
            continue
        filtered.append(item)
    return filtered


def _js_string(value):
    if value is None:
        return ''
    if value is True:
        return 'true'
    if isinstance(value, dict):
        return '[object Object]'
    if isinstance(value, list):
        return ','.join(_js_string(part) for part in value)
    return str(value)


def _normalize(value):
    return ''.join(
        char for char in unicodedata.normalize('NFD', value)
        if unicodedata.category(char) != 'Mn'
    ).lower()


def filter_search(items, term):
    """Replica la búsqueda general de la tabla antes de exportar."""
    query = _normalize((term or '').strip())
    if not query:
        return items
    return [
        item for item in items
        if query in _normalize(' '.join(_js_string(value) for value in item.values()))
    ]

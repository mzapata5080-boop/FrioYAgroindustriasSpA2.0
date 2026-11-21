"""Operaciones comunes del catálogo con controles de rol en el servidor."""
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.forms.models import model_to_dict
from django.views.decorators.http import require_http_methods
from usuarios.forms import TrabajadorEditarForm
from frio_agroindustria.api_common import error, data, allowed, schema, serialize
from frio_agroindustria.common import registrar_cambio, snapshot_instance
from frio_agroindustria.api_resources import RESOURCES
from inventario.api import movements
from inventario.models import Repuesto, RecepcionIngreso
from finanzas.forms import FacturaCompraDetalleForm


def _resource_fields(resource, formclass, instance=None):
    form = formclass(instance=instance) if instance else formclass()
    fields = schema(form)
    if resource == 'facturas':
        fields.append({
            'name': 'detalles',
            'label': 'Artículos de la factura',
            'type': 'details',
            'required': True
        })
    return fields


def _resource_options(resource):
    if resource != 'facturas':
        return {}
    return {
        'articles': list(
            Repuesto.objects.order_by('pk').values(
                'id', 'codigo_parte', 'descripcion', 'unidad_medida'
            )
        )
    }


def _validate_invoice_details(raw_details, required=True):
    if not isinstance(raw_details, list):
        return None, {
            'detalles': ['Los detalles deben enviarse como una lista de artículos.']
        }
    if required and not raw_details:
        return None, {
            'detalles': ['Agregue al menos un artículo a la factura.']
        }
    if not raw_details:
        return [], {}

    details = []
    errors = {}
    for index, values in enumerate(raw_details):
        if not isinstance(values, dict):
            errors[f'detalles.{index}'] = [
                'Cada detalle debe incluir artículo, cantidad y precio unitario.'
            ]
            continue

        form = FacturaCompraDetalleForm(data=values)
        if not form.is_valid():
            for field, messages in form.errors.items():
                errors[f'detalles.{index}.{field}'] = [
                    str(message) for message in messages
                ]
            continue
        details.append(form.save(commit=False))

    if errors:
        return None, errors
    return details, {}


def _save_invoice_details(invoice, details, replace=False):
    if replace:
        invoice.detalles.all().delete()
    for detail in details:
        detail.factura = invoice
        detail.save()

@require_http_methods(['GET','POST'])
def collection(request,resource):
    if not request.user.is_authenticated: return error('Inicia sesión.',401)
    if resource in ('ingresos','salidas','kardex'):
        return movements(request,resource)
    if resource == 'solicitudes':
        roles = ('bodega', 'gerencia', 'supervisor de obra', 'supervisor')
        if not allowed(request.user, roles):
            return error('No tienes permisos.', 403)
        from inventario.api_forms import SolicitudMaterialForm
        from inventario.models import Repuesto
        if request.method == 'GET':
            return JsonResponse({
                'items': [],
                'fields': schema(SolicitudMaterialForm()),
                'can_write': True,
                'can_delete': False,
                'articles': list(Repuesto.objects.filter(activo=True).values('id', 'codigo_parte', 'descripcion', 'unidad_medida', 'stock_actual')),
                'notice': 'Pantalla de Solicitudes preparada según los campos acordados con Benjamín. La persistencia en Supabase se conectará el 21/11.'
            })
        form = SolicitudMaterialForm(data(request))
        if not form.is_valid():
            return JsonResponse({'errors': form.errors}, status=400)
        return error('Conexión pendiente: El guardado definitivo en base compartida de Obras y Solicitudes se completará el sábado 21/11 tras aplicar la migración 0003.', status=501)
    if resource not in RESOURCES: return error('Recurso no encontrado.',404)
    model,formclass,roles=RESOURCES[resource]
    read_stock=resource=='articulos' and request.method=='GET'
    if not read_stock and not allowed(request.user,roles): return error('No tienes permisos.',403)
    if request.method=='GET':
        qs = model.objects.order_by('pk')
        if resource == 'articulos':
            qs = qs.select_related('categoria')
        if resource == 'facturas':
            qs = qs.prefetch_related(
                'detalles__articulo',
                'detalles__recepciones',
                'recepciones_compra'
            )
        return JsonResponse({
            'items': [serialize(x) for x in qs],
            'fields': _resource_fields(resource, formclass),
            'can_write': allowed(request.user, roles),
            'can_delete': resource in ('clientes', 'trabajadores'),
            **_resource_options(resource)
        })

    payload = data(request)
    raw_details = payload.pop('detalles', None) if resource == 'facturas' else None
    form = formclass(payload)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)

    invoice_details = None
    if resource == 'facturas':
        invoice_details, detail_errors = _validate_invoice_details(raw_details)
        if detail_errors:
            return JsonResponse({'errors': detail_errors}, status=400)

    try:
        with transaction.atomic():
            obj=form.save()
            if resource == 'facturas':
                _save_invoice_details(obj, invoice_details)
            registrar_cambio(request.user, 'CREAR', obj)
    except IntegrityError: return error('El registro ya existe o tiene referencias inválidas.')
    return JsonResponse({'item':serialize(obj)},status=201)

@require_http_methods(['GET','POST'])
def detail(request,resource,pk):
    if not request.user.is_authenticated: return error('Inicia sesión.',401)
    if resource not in RESOURCES: return error('Recurso no encontrado.',404)
    model,formclass,roles=RESOURCES[resource]
    if not allowed(request.user,roles): return error('No tienes permisos.',403)
    obj=model.objects.filter(pk=pk).first()
    if obj is None: return error('Registro no encontrado.',404)
    if resource=='trabajadores': formclass=TrabajadorEditarForm
    if request.method=='GET':
        return JsonResponse({
            'item': serialize(obj),
            'fields': _resource_fields(resource, formclass, obj),
            **_resource_options(resource)
        })
    d=data(request)
    raw_details = d.pop('detalles', None) if resource == 'facturas' else None
    if d.pop('_delete',False):
        if resource not in ('clientes','trabajadores'): return error('No se permite eliminar este tipo de registro.',403)
        if resource=='trabajadores' and obj.pk==request.user.pk: return error('No puedes eliminar tu propia cuenta.')
        antes = snapshot_instance(obj)
        obj_pk = obj.pk
        try: obj.delete()
        except ProtectedError: return error('Hay registros asociados; no se puede eliminar.')
        obj.pk = obj_pk
        registrar_cambio(request.user, 'ELIMINAR', obj, antes=antes)
        return JsonResponse({'ok':True})
    try:
        with transaction.atomic():
            obj = model.objects.select_for_update().get(pk=pk)
            antes = snapshot_instance(obj)
            if (
                resource == 'facturas'
                and raw_details is not None
                and (
                    obj.recepciones_compra.exists()
                    or RecepcionIngreso.objects.filter(factura=obj).exists()
                )
            ):
                return JsonResponse({
                    'errors': {
                        'detalles': [
                            'No se pueden cambiar los artículos de una factura que ya tiene recepciones.'
                        ]
                    }
                }, status=400)
            merged = model_to_dict(obj)
            merged.update(d)
            form = formclass(merged, instance=obj)
            if not form.is_valid():
                return JsonResponse({'errors': form.errors}, status=400)

            invoice_details = None
            if resource == 'facturas' and raw_details is not None:
                invoice_details, detail_errors = _validate_invoice_details(
                    raw_details,
                    required=obj.detalles.exists()
                )
                if detail_errors:
                    return JsonResponse({'errors': detail_errors}, status=400)

            obj = form.save()
            if resource == 'facturas' and invoice_details is not None:
                _save_invoice_details(obj, invoice_details, replace=True)
            registrar_cambio(request.user, 'EDITAR', obj, antes=antes)
    except model.DoesNotExist:
        return error('Registro no encontrado.', 404)
    except IntegrityError:
        return error('No se pudo guardar el registro.')
    return JsonResponse({'item': serialize(obj)})
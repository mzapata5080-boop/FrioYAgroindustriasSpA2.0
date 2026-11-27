"""Operaciones comunes del catálogo con controles de rol en el servidor."""
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.forms.models import model_to_dict
from django.views.decorators.http import require_http_methods
from usuarios.forms import TrabajadorEditarForm
from frio_agroindustria.api_common import (
    error, data, allowed, schema, serialize, permission_denied,
)
from frio_agroindustria.common import registrar_cambio, snapshot_instance
from frio_agroindustria.api_resources import RESOURCES
from inventario.api import movements
from inventario.models import Repuesto, RecepcionIngreso
from finanzas.forms import FacturaCompraDetalleForm
from finanzas.models import FacturaCompraDetalle, FacturaCompra, Presupuesto, PresupuestoDetalle
from finanzas.comercial import actualizar_totales
from reportes.filters import FILTER_FIELDS, InvalidReportFilter, filter_queryset


def _resource_fields(resource, formclass, instance=None):
    form = formclass(instance=instance) if instance else formclass()
    fields = schema(form)
    if resource == 'facturas':
        fields.append({
            'name': 'detalles',
            'label': 'Artículos de la factura',
            'type': 'details',
            'required': True,
        })
    return fields


def _resource_options(resource):
    if resource == 'detalles-presupuesto':
        from finanzas.models import PrecioArticulo
        precios = {}
        for precio in PrecioArticulo.objects.order_by('-fecha', '-pk'):
            precios.setdefault(str(precio.articulo_id), str(precio.precio_lista))
        return {'list_prices': precios}
    if resource != 'facturas':
        return {}
    return {
        'articles': list(
            Repuesto.objects.order_by('pk').values(
                'id', 'codigo_parte', 'descripcion', 'unidad_medida'
            )
        )
    }


def _validate_invoice_details(raw_details, required=True, existing_details=()):
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
    existing_by_id = {str(detail.pk): detail for detail in existing_details}
    used_existing_ids = set()
    for index, values in enumerate(raw_details):
        if not isinstance(values, dict):
            errors[f'detalles.{index}'] = [
                'Cada detalle debe incluir artículo, cantidad y precio unitario.'
            ]
            continue

        existing = existing_by_id.get(str(values.get('id')))
        if existing and existing.pk in used_existing_ids:
            existing = None
        form = FacturaCompraDetalleForm(data=values, instance=existing)
        if not form.is_valid():
            for field, messages in form.errors.items():
                errors[f'detalles.{index}.{field}'] = [
                    str(message) for message in messages
                ]
            continue
        if existing:
            used_existing_ids.add(existing.pk)
        details.append(FacturaCompraDetalle(
            articulo=form.cleaned_data['articulo'],
            cantidad=form.cleaned_data['cantidad'],
            precio_unitario=form.cleaned_data['precio_unitario'],
            **{f'descuento_{n}': form.cleaned_data[f'descuento_{n}'] for n in (1,2,3)},
            precio_lista=form.cleaned_data.get('precio_lista'),
        ))

    if errors:
        return None, errors
    return details, {}


def _save_invoice_details(invoice, details, replace=False):
    if replace:
        invoice.detalles.all().delete()
    for detail in details:
        detail.factura = invoice
        detail.save()


def _resource_permissions(resource, user):
    if resource == 'presupuestos-venta':
        return {
            'can_approve': user.is_superuser
            or user.has_perm('finanzas.aprobar_presupuesto')
        }
    if resource == 'documentos-venta':
        return {
            'can_register_payments': user.is_superuser
            or user.has_perm('finanzas.registrar_pago_documento'),
            'can_void_documents': user.is_superuser
            or user.has_perm('finanzas.anular_documento_venta'),
        }
    return {}


@require_http_methods(['GET', 'POST'])
def collection(request, resource):
    if not request.user.is_authenticated:
        return error('Inicia sesión.', 401)
    if resource in ('ingresos', 'salidas', 'kardex'):
        return movements(request, resource)
    if resource not in RESOURCES:
        return error('Recurso no encontrado.', 404)
    model, formclass, roles = RESOURCES[resource]
    read_stock = resource == 'articulos' and request.method == 'GET'
    if not read_stock and not allowed(request.user, roles):
        return permission_denied()
    if request.method == 'GET':
        qs = model.objects.order_by('pk')
        if resource == 'articulos':
            qs = qs.select_related('categoria')
        if resource == 'facturas':
            qs = qs.prefetch_related(
                'detalles__articulo',
                'detalles__recepciones',
                'recepciones_compra',
            )
        try:
            qs = filter_queryset(resource, qs, request.GET)
        except InvalidReportFilter as exc:
            return error(str(exc), 400)
        return JsonResponse({
            'items': [serialize(x) for x in qs],
            'fields': _resource_fields(resource, formclass),
            'filter_fields': FILTER_FIELDS.get(resource, []),
            'can_write': allowed(request.user, roles),
            'can_delete': resource in ('clientes', 'trabajadores'),
            **_resource_permissions(resource, request.user),
            **_resource_options(resource),
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
            if resource == 'detalles-presupuesto':
                padre = Presupuesto.objects.select_for_update().get(pk=form.cleaned_data['presupuesto'].pk)
                if padre.estado != 'BORRADOR':
                    return error('El presupuesto ya fue resuelto.')
                form.instance.presupuesto = padre
            if resource == 'notas-credito':
                obj = form.save(commit=False)
                obj.registrado_por = request.user
                obj.save()
                form.save_m2m()
            else:
                obj = form.save()
            if resource == 'facturas':
                _save_invoice_details(obj, invoice_details)
            if resource in ('facturas', 'presupuestos-venta'):
                actualizar_totales(obj)
            elif resource == 'detalles-presupuesto':
                actualizar_totales(padre)
            registrar_cambio(request.user, 'CREAR', obj)
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {
            'error': exc.messages
        }
        return JsonResponse({'errors': errors}, status=400)
    except IntegrityError:
        return error('El registro ya existe o tiene referencias inválidas.')
    return JsonResponse({'item': serialize(obj)}, status=201)


@require_http_methods(['GET', 'POST'])
def detail(request, resource, pk):
    if not request.user.is_authenticated:
        return error('Inicia sesión.', 401)
    if resource not in RESOURCES:
        return error('Recurso no encontrado.', 404)
    model, formclass, roles = RESOURCES[resource]
    if not allowed(request.user, roles):
        return permission_denied()
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        return error('Registro no encontrado.', 404)
    if resource == 'trabajadores':
        formclass = TrabajadorEditarForm
    if request.method == 'GET':
        return JsonResponse({
            'item': serialize(obj),
            'fields': _resource_fields(resource, formclass, obj),
            **_resource_permissions(resource, request.user),
            **_resource_options(resource),
        })
    d = data(request)
    raw_details = d.pop('detalles', None) if resource == 'facturas' else None
    if d.pop('_delete', False):
        if resource not in ('clientes', 'trabajadores'):
            return permission_denied()
        if resource == 'trabajadores' and obj.pk == request.user.pk:
            return error('No puedes eliminar tu propia cuenta.')
        antes = snapshot_instance(obj)
        obj_pk = obj.pk
        try:
            obj.delete()
        except ProtectedError:
            return error('Hay registros asociados; no se puede eliminar.')
        obj.pk = obj_pk
        registrar_cambio(request.user, 'ELIMINAR', obj, antes=antes)
        return JsonResponse({'ok': True})
    if resource == 'notas-credito':
        return error('Las notas de crédito son inmutables.', 403)
    try:
        with transaction.atomic():
            obj = model.objects.select_for_update().get(pk=pk)
            antes = snapshot_instance(obj)
            if resource == 'facturas' and obj.confirmada:
                return error('La factura está confirmada; no se puede modificar.', 403)
            if resource == 'facturas' and (obj.recepciones_compra.exists() or RecepcionIngreso.objects.filter(factura=obj).exists()):
                financieros = {'monto', 'descuento_general', 'descuento_pronto_pago', 'tasa_iva', 'calcular_totales'}
                if any(k in d and str(d[k]) != str(getattr(obj, k, obj.calculo_activo)) for k in financieros):
                    return error('La factura tiene recepciones: conserva sus valores financieros.', 403)
            if resource == 'detalles-presupuesto':
                padre = Presupuesto.objects.select_for_update().get(pk=obj.presupuesto_id)
                if padre.estado != 'BORRADOR':
                    return error('El presupuesto ya fue resuelto.')
                if 'presupuesto' in d and str(d['presupuesto']) != str(padre.pk):
                    return error('No se permite mover un detalle a otro presupuesto.')
            if (
                resource == 'facturas'
                and raw_details is not None
                and (
                    obj.recepciones_compra.exists()
                    or RecepcionIngreso.objects.filter(factura=obj).exists()
                )
            ):
                return JsonResponse(
                    {
                        'errors': {
                            'detalles': [
                                'No se pueden cambiar los artículos de una factura que ya tiene recepciones.'
                            ]
                        }
                    },
                    status=400,
                )
            merged = model_to_dict(obj)
            merged.update(d)
            form = formclass(merged, instance=obj)
            if not form.is_valid():
                return JsonResponse({'errors': form.errors}, status=400)

            invoice_details = None
            if resource == 'facturas' and raw_details is not None:
                invoice_details, detail_errors = _validate_invoice_details(
                    raw_details,
                    required=obj.detalles.exists(),
                    existing_details=obj.detalles.all(),
                )
                if detail_errors:
                    return JsonResponse({'errors': detail_errors}, status=400)

            obj = form.save()
            if resource == 'facturas' and invoice_details is not None:
                _save_invoice_details(obj, invoice_details, replace=True)
            if resource in ('facturas', 'presupuestos-venta'):
                actualizar_totales(obj)
            elif resource == 'detalles-presupuesto':
                actualizar_totales(padre)
            registrar_cambio(request.user, 'EDITAR', obj, antes=antes)
    except ValidationError as exc:
        return JsonResponse({'errors': exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}}, status=400)
    except model.DoesNotExist:
        return error('Registro no encontrado.', 404)
    except IntegrityError:
        return error('No se pudo guardar el registro.')
    return JsonResponse({'item': serialize(obj)})
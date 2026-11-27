"""Recursos comerciales y sus permisos; validación en los formularios existentes."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from frio_agroindustria.api_common import (
    allowed, data, error, serialize, permission_denied,
)
from .models import (
    Cliente,
    Proveedor,
    FacturaCompra,
    Presupuesto,
    PresupuestoDetalle,
    DocumentoVenta,
    PagoDocumento,
    NotaCredito,
)
from .forms import (
    ClienteForm,
    ProveedorForm,
    FacturaCompraForm,
    PresupuestoForm,
    PresupuestoDetalleForm,
    DocumentoVentaForm,
    PagoDocumentoForm,
    NotaCreditoForm,
)
from .calculos import calcular_documento, margen_sobre_venta
from .comercial import confirmar_compra, registrar_precio
from .models import PrecioArticulo
from .forms import PrecioArticuloForm
from frio_agroindustria.api_common import schema

FINANCE_RESOURCES = {
    'clientes': (Cliente, ClienteForm, ('finanzas', 'gerencia')),
    'proveedores': (Proveedor, ProveedorForm, ('finanzas', 'gerencia')),
    'facturas': (FacturaCompra, FacturaCompraForm, ('finanzas', 'gerencia')),
    'presupuestos-venta': (
        Presupuesto, PresupuestoForm, ('finanzas', 'gerencia')
    ),
    'detalles-presupuesto': (
        PresupuestoDetalle, PresupuestoDetalleForm, ('finanzas', 'gerencia')
    ),
    'documentos-venta': (
        DocumentoVenta, DocumentoVentaForm, ('finanzas', 'gerencia')
    ),
    'notas-credito': (NotaCredito, NotaCreditoForm, ('finanzas', 'gerencia')),
}


@require_http_methods(['POST'])
def calculo_previo(request):
    if not allowed(request.user, ('finanzas', 'gerencia')):
        return permission_denied()
    payload = data(request)
    try:
        if 'precio_compra' in payload or 'precio_lista' in payload:
            return JsonResponse({'margen': margen_sobre_venta(payload.get('precio_compra'), payload.get('precio_lista'))})
        resultado = calcular_documento(payload.get('detalles'), payload.get('descuento_general', '0'),
            payload.get('descuento_pronto_pago', '0'), payload.get('tasa_iva', '19'))
    except ValidationError as exc:
        return _validation_response(exc)
    return JsonResponse({'totales': resultado})


@require_http_methods(['GET', 'POST'])
def precios(request):
    if not allowed(request.user, ('finanzas', 'gerencia', 'bodega')):
        return permission_denied()
    if request.method == 'GET':
        qs = PrecioArticulo.objects.select_related('articulo')
        if request.GET.get('articulo'):
            if not request.GET['articulo'].isdigit():
                return error('Artículo inválido.')
            qs = qs.filter(articulo_id=request.GET['articulo'])
        por_articulo = {}
        for registro in qs:
            grupo = por_articulo.setdefault(registro.articulo_id, [])
            if len(grupo) < 3:
                grupo.append({'id': registro.pk, 'articulo': registro.articulo_id,
                    'articulo_nombre': str(registro.articulo), 'precio_compra': registro.precio_compra,
                    'precio_lista': registro.precio_lista, 'margen': registro.margen, 'fecha': registro.fecha})
        return JsonResponse({'items': [p for grupo in por_articulo.values() for p in grupo],
            'fields': schema(PrecioArticuloForm()), 'can_write': allowed(request.user, ('finanzas', 'gerencia')),
            'can_delete': False})
    if not allowed(request.user, ('finanzas', 'gerencia')):
        return permission_denied()
    form = PrecioArticuloForm(data(request))
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    from frio_agroindustria.common import registrar_cambio
    try:
        with transaction.atomic():
            registro = registrar_precio(articulo_id=form.cleaned_data['articulo'].pk,
                precio_compra=form.cleaned_data['precio_compra'], precio_lista=form.cleaned_data['precio_lista'], usuario=request.user)
            registrar_cambio(request.user, 'CREAR_PRECIO', registro)
    except ValidationError as exc:
        return _validation_response(exc)
    return JsonResponse({'item': {'id': registro.pk, 'precio_compra': registro.precio_compra,
        'precio_lista': registro.precio_lista, 'margen': registro.margen, 'fecha': registro.fecha}}, status=201)


@require_http_methods(['POST'])
def compra_confirmar(request, pk):
    if not allowed(request.user, ('finanzas', 'gerencia')):
        return permission_denied()
    from frio_agroindustria.common import registrar_cambio
    try:
        with transaction.atomic():
            factura, repetida = confirmar_compra(factura_id=pk, usuario=request.user)
            if not repetida:
                registrar_cambio(request.user, 'CONFIRMAR', factura)
    except FacturaCompra.DoesNotExist:
        return error('Factura no encontrada.', 404)
    except ValidationError as exc:
        return _validation_response(exc)
    return JsonResponse({'item': serialize(factura), 'repeated': repetida})


def _permission(user, codename):
    return user.is_superuser or user.has_perm(f"finanzas.{codename}")


def _validation_response(exc):
    if hasattr(exc, "message_dict"):
        errors = {
            field: [str(message) for message in messages]
            for field, messages in exc.message_dict.items()
        }
    else:
        errors = {"error": [str(message) for message in exc.messages]}
    return JsonResponse({"errors": errors}, status=400)


@require_http_methods(["GET", "POST"])
def documento_pagos(request, pk):
    if not request.user.is_authenticated:
        return error("Inicia sesión.", 401)
    if not allowed(request.user, ("finanzas", "gerencia")):
        return permission_denied()
    documento = DocumentoVenta.objects.filter(pk=pk).first()
    if documento is None:
        return error("Documento no encontrado.", 404)

    if request.method == "GET":
        return JsonResponse({
            "items": [serialize(pago) for pago in documento.pagos.select_related(
                "registrado_por"
            )],
            "saldo": str(documento.saldo),
            "total": str(documento.total),
            "can_register": _permission(
                request.user, "registrar_pago_documento"
            ) and not documento.anulado,
        })

    if not _permission(request.user, "registrar_pago_documento"):
        return permission_denied()
    payload = data(request)
    payload["documento"] = documento.pk
    form = PagoDocumentoForm(payload)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    from frio_agroindustria.common import registrar_cambio

    try:
        with transaction.atomic():
            pago = form.save(commit=False)
            pago.registrado_por = request.user
            pago.save()
            registrar_cambio(request.user, "CREAR", pago)
    except ValidationError as exc:
        return _validation_response(exc)
    except IntegrityError:
        return error("No se pudo registrar el pago.")
    return JsonResponse({
        "item": serialize(pago),
        "saldo": str(pago.documento.saldo),
    }, status=201)


@require_http_methods(["POST"])
def presupuesto_decision(request, pk):
    if not request.user.is_authenticated:
        return error("Inicia sesión.", 401)
    if not _permission(request.user, "aprobar_presupuesto"):
        return permission_denied()
    payload = data(request)
    accion = payload.get("accion")
    presupuesto = Presupuesto.objects.filter(pk=pk).first()
    if presupuesto is None:
        return error("Presupuesto no encontrado.", 404)

    from frio_agroindustria.common import registrar_cambio, snapshot_instance

    try:
        with transaction.atomic():
            presupuesto = Presupuesto.objects.select_for_update().get(pk=pk)
            antes = snapshot_instance(presupuesto)
            if accion == "aprobar":
                from .comercial import actualizar_totales
                actualizar_totales(presupuesto)
                presupuesto.aprobar(request.user)
            elif accion == "rechazar":
                presupuesto.rechazar(request.user, payload.get("motivo", ""))
            else:
                return error("La acción debe ser aprobar o rechazar.")
            registrar_cambio(request.user, accion.upper(), presupuesto, antes=antes)
    except ValidationError as exc:
        return _validation_response(exc)
    return JsonResponse({"item": serialize(presupuesto)})


@require_http_methods(["POST"])
def documento_anular(request, pk):
    if not request.user.is_authenticated:
        return error("Inicia sesión.", 401)
    if not _permission(request.user, "anular_documento_venta"):
        return permission_denied()
    payload = data(request)
    documento = DocumentoVenta.objects.filter(pk=pk).first()
    if documento is None:
        return error("Documento no encontrado.", 404)

    from frio_agroindustria.common import registrar_cambio, snapshot_instance

    try:
        with transaction.atomic():
            documento = DocumentoVenta.objects.select_for_update().get(pk=pk)
            antes = snapshot_instance(documento)
            documento.anular_documento(request.user, payload.get("motivo", ""))
            registrar_cambio(request.user, "ANULAR", documento, antes=antes)
    except ValidationError as exc:
        return _validation_response(exc)
    return JsonResponse({"item": serialize(documento)})

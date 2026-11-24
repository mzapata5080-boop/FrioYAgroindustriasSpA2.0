"""Persistencia comercial: snapshots propios; jamás escribe lotes ni costos FIFO."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from inventario.models import Repuesto, RecepcionIngreso
from .calculos import calcular_documento
from .models import FacturaCompra, Presupuesto, PrecioArticulo


def lineas_documento(documento):
    return [{
        'cantidad': d.cantidad, 'precio_unitario': d.precio_unitario,
        **{f'descuento_{n}': getattr(d, f'descuento_{n}') for n in (1, 2, 3)},
    } for d in documento.detalles.order_by('pk')]


def actualizar_totales(documento):
    lineas = lineas_documento(documento)
    activo = documento.calculo_activo or any((documento.descuento_general, documento.descuento_pronto_pago))
    activo = activo or any(any(l[f'descuento_{n}'] for n in (1, 2, 3)) for l in lineas)
    if not activo:
        return  # Un documento legado conserva su monto y su comportamiento anteriores.
    if not lineas and isinstance(documento, Presupuesto):
        documento.calculo_activo = True
        documento.save(update_fields=['calculo_activo'])
        return
    resultado = calcular_documento(lineas, documento.descuento_general,
        documento.descuento_pronto_pago, documento.tasa_iva)
    documento.calculo_activo = True
    documento.calculo_comercial = resultado
    campos = ['calculo_activo', 'calculo_comercial']
    if isinstance(documento, FacturaCompra):
        documento.monto = Decimal(resultado['total'])
        campos.append('monto')
    documento.save(update_fields=campos)


@transaction.atomic
def registrar_precio(*, articulo_id, precio_compra, precio_lista, usuario):
    articulo = Repuesto.objects.select_for_update().get(pk=articulo_id)
    return PrecioArticulo.objects.create(articulo=articulo, precio_compra=precio_compra,
        precio_lista=precio_lista, registrado_por=usuario)


@transaction.atomic
def confirmar_compra(*, factura_id, usuario):
    factura = FacturaCompra.objects.select_for_update().get(pk=factura_id)
    if factura.confirmada:
        return factura, True
    if factura.recepciones_compra.exists() or RecepcionIngreso.objects.filter(factura=factura).exists():
        raise ValidationError('Esta factura ya tiene recepciones; conserva sus importes históricos.')
    if not factura.calculo_activo:
        raise ValidationError('Activa el cálculo comercial y revisa los totales antes de confirmar.')
    actualizar_totales(factura)
    # Orden compartido para que dos compras de varios artículos no bloqueen en orden inverso.
    detalles = list(factura.detalles.order_by('articulo_id', 'pk'))
    list(Repuesto.objects.select_for_update().filter(
        pk__in=[d.articulo_id for d in detalles]).order_by('pk'))
    for detalle in detalles:
        if detalle.precio_lista is not None:
            registrar_precio(articulo_id=detalle.articulo_id, precio_compra=detalle.precio_unitario,
                precio_lista=detalle.precio_lista, usuario=usuario)
    factura.confirmada = True
    factura.save(update_fields=['confirmada'])
    return factura, False

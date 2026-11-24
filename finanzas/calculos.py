"""Cálculo comercial puro. Ninguna función escribe inventario ni consume FIFO."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from django.core.exceptions import ValidationError

CENTAVO = Decimal('0.01')
MAX_IMPORTE = Decimal('9999999999.99')


def numero(valor, nombre, minimo=Decimal('0'), maximo=MAX_IMPORTE):
    if isinstance(valor, (bool, float)) or valor is None:
        raise ValidationError({nombre: 'Utiliza un decimal válido.'})
    try:
        resultado = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({nombre: 'Utiliza un decimal válido.'}) from exc
    if not resultado.is_finite() or not minimo <= resultado <= maximo:
        raise ValidationError({nombre: f'Valor fuera del intervalo {minimo} a {maximo}.'})
    if resultado != resultado.quantize(CENTAVO):
        raise ValidationError({nombre: 'Se admiten hasta dos decimales.'})
    return resultado


def porcentaje(valor, nombre):
    return numero(valor, nombre, maximo=Decimal('100'))


def dinero(valor):
    resultado = valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if not Decimal('0') <= resultado <= MAX_IMPORTE:
        raise ValidationError('El importe calculado excede el máximo permitido.')
    return resultado


def calcular_documento(lineas, descuento_general='0', descuento_pronto_pago='0', tasa_iva='19'):
    """D1→D2→D3 sobre el unitario, redondeo por línea; general→pronto pago→IVA.

    Generales y pronto pago se calculan sobre el saldo del subtotal. Se guardan
    diferencias de importes redondeados para que el desglose cuadre exactamente.
    """
    if not isinstance(lineas, list) or not lineas:
        raise ValidationError({'detalles': 'Agrega al menos una línea.'})
    if len(lineas) > 500:
        raise ValidationError({'detalles': 'Máximo 500 líneas por documento.'})
    dg = porcentaje(descuento_general, 'descuento_general')
    pp = porcentaje(descuento_pronto_pago, 'descuento_pronto_pago')
    iva = porcentaje(tasa_iva, 'tasa_iva')
    with localcontext() as contexto:
        contexto.prec = 50
        resultados = []
        for i, linea in enumerate(lineas):
            if not isinstance(linea, dict):
                raise ValidationError({'detalles': f'Línea {i+1} inválida.'})
            cantidad = numero(linea.get('cantidad'), 'cantidad', minimo=CENTAVO,
                maximo=Decimal('9999999999999.99'))
            precio = numero(linea.get('precio_unitario'), 'precio_unitario')
            ds = [porcentaje(linea.get(f'descuento_{n}', '0'), f'descuento_{n}') for n in (1, 2, 3)]
            unitario = precio
            for d in ds:
                unitario *= 1 - d / 100
            bruto = dinero(cantidad * precio)
            neto_linea = dinero(cantidad * unitario)
            resultados.append({
                'cantidad': str(cantidad), 'precio_unitario': str(precio),
                **{f'descuento_{n}': str(ds[n-1]) for n in (1, 2, 3)},
                'bruto': str(bruto), 'descuento_articulo': str(bruto-neto_linea),
                'unitario_neto_referencia': str(unitario), 'neto_linea': str(neto_linea),
            })
        bruto = dinero(sum((Decimal(x['bruto']) for x in resultados), Decimal('0')))
        subtotal = dinero(sum((Decimal(x['neto_linea']) for x in resultados), Decimal('0')))
        tras_general = dinero(subtotal * (1-dg/100))
        neto = dinero(tras_general * (1-pp/100))
        impuesto = dinero(neto * iva/100)
        total = dinero(neto+impuesto)
    return {
        'version': 1, 'redondeo': 'HALF_UP_2_DECIMALES_POR_LINEA',
        'lineas': resultados, 'bruto': str(bruto),
        'descuentos_articulos': str(bruto-subtotal), 'subtotal': str(subtotal),
        'descuento_general': str(dg), 'importe_descuento_general': str(subtotal-tras_general),
        'descuento_pronto_pago': str(pp), 'importe_pronto_pago': str(tras_general-neto),
        'neto': str(neto), 'tasa_iva': str(iva), 'impuestos': str(impuesto), 'total': str(total),
    }


def margen_sobre_venta(compra, lista):
    compra = numero(compra, 'precio_compra')
    lista = numero(lista, 'precio_lista', minimo=CENTAVO)
    with localcontext() as contexto:
        contexto.prec = 50
        margen = ((lista-compra)/lista*100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if not Decimal('-9999999.99') <= margen <= Decimal('100'):
        raise ValidationError('Margen fuera del rango admitido.')
    return margen

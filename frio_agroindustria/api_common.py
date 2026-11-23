"""Respuestas JSON, permisos, metadatos y serialización compartidos."""
import json
from decimal import Decimal
from django import forms
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.forms.models import model_to_dict
from usuarios.models import Trabajador
from finanzas.models import (
    FacturaCompra,
    Presupuesto,
    PresupuestoDetalle,
    DocumentoVenta,
    PagoDocumento,
    NotaCredito,
)
from inventario.models import MovimientoBodega, RecepcionIngreso, Repuesto

class CorsMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        origin = request.headers.get('Origin')
        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if origin in settings.FRONTEND_ORIGINS:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
            response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            from django.utils.cache import patch_vary_headers
            patch_vary_headers(response, ('Origin',))
        return response

def error(message, status=400): return JsonResponse({'error': message}, status=status)
def data(request):
    try:
        result = json.loads(request.body or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, UnicodeDecodeError): return {}
def profile(user):
    return {'id':user.pk,'username':user.username,'name':user.get_full_name(), 'rol':user.rol,'is_superuser':user.is_superuser}
def allowed(user, roles): return user.is_authenticated and (user.is_superuser or user.rol in roles)

def schema(form):
    result=[]
    for name,f in form.fields.items():
        if name=='password': continue
        kind='text'
        if isinstance(f.widget,forms.HiddenInput): kind='hidden'
        elif isinstance(f.widget,forms.PasswordInput): kind='password'
        elif isinstance(f.widget,forms.Textarea): kind='textarea'
        elif isinstance(f,forms.BooleanField): kind='checkbox'
        elif isinstance(f,forms.DateField): kind='date'
        elif isinstance(f,forms.DecimalField): kind='number'
        elif isinstance(f,forms.EmailField): kind='email'
        elif hasattr(f,'choices'): kind='select'
        item={'name':name,'label':str(f.label or name.replace('_',' ').capitalize()),'type':kind,'required':f.required}
        if f.initial is not None and kind not in ('hidden', 'password'):
            item['initial'] = f.initial
        if kind=='select':
            item['choices']=[[str(k),str(v)] for k,v in f.choices]
            item['multiple']=f.widget.allow_multiple_selected
        if isinstance(f, forms.DecimalField):
            item['step'] = str(f.widget.attrs.get(
                'step', Decimal(1).scaleb(-f.decimal_places)
            ))
            if f.min_value is not None: item['min'] = str(f.min_value)
            if f.max_value is not None: item['max'] = str(f.max_value)
        if getattr(f,'max_length',None): item['maxLength']=f.max_length
        result.append(item)
    return result

def serialize(obj):
    if isinstance(obj,Trabajador):
        return {**profile(obj),'first_name':obj.first_name,'last_name':obj.last_name,'email':obj.email,'rut':obj.rut,'telefono':obj.telefono,'is_active':obj.is_active,'rol':obj.groups.first().name if obj.groups.exists() else ''}
    d=model_to_dict(obj)
    if isinstance(obj, Repuesto):
        d['categoria_id'] = obj.categoria_id
        d['categoria_nombre'] = obj.categoria.nombre if obj.categoria else '—'
        d['unidad_medida_display'] = obj.get_unidad_medida_display()
    if isinstance(obj,FacturaCompra):
        d['proveedor_nombre'] = str(obj.proveedor)
        details = list(obj.detalles.all())
        d['detalle_count'] = len(details)
        d['detalles_bloqueados'] = (
            bool(obj.recepciones_compra.all())
            or RecepcionIngreso.objects.filter(factura=obj).exists()
            or any(detail.recepciones.all() for detail in details)
        )
        d['detalles'] = [{
            'id': detail.pk,
            'articulo': detail.articulo_id,
            'articulo_nombre': str(detail.articulo),
            'cantidad': str(detail.cantidad),
            'precio_unitario': str(detail.precio_unitario),
        } for detail in details]
        if not d['detalles']:
            d['detalles'] = [{
                'articulo_nombre': str(receipt.movimiento.repuesto),
                'cantidad': str(receipt.movimiento.cantidad),
                'precio_unitario': str(receipt.precio_unitario_neto),
            } for receipt in RecepcionIngreso.objects.filter(factura=obj).select_related(
                'movimiento__repuesto'
            ).order_by('movimiento__fecha_registro', 'movimiento_id')]
    if isinstance(obj, Presupuesto):
        d.update(
            cliente_nombre=str(obj.cliente),
            obra_codigo=obj.obra.codigo_ot if obj.obra_id else '',
            obra_nombre=obj.obra.nombre if obj.obra_id else '',
            total=str(obj.total),
            detalles=[{
                'id': detalle.pk,
                'articulo': detalle.articulo_id,
                'articulo_nombre': str(detalle.articulo),
                'cantidad': str(detalle.cantidad),
                'precio_unitario': str(detalle.precio_unitario),
                'subtotal': str(detalle.subtotal),
            } for detalle in obj.detalles.select_related('articulo')],
        )
    if isinstance(obj, PresupuestoDetalle):
        d.update(
            presupuesto_numero=obj.presupuesto.numero,
            articulo_nombre=str(obj.articulo),
            subtotal=str(obj.subtotal),
        )
    if isinstance(obj, DocumentoVenta):
        d.update(
            cliente_nombre=str(obj.cliente),
            obra_codigo=obj.obra.codigo_ot if obj.obra_id else '',
            obra_nombre=obj.obra.nombre if obj.obra_id else '',
            pagos_count=obj.pagos.count(),
            notas_credito_count=obj.notas_credito.count(),
        )
    if isinstance(obj, PagoDocumento):
        d.update(
            documento_numero=obj.documento.numero_documento,
            registrado_por_nombre=(
                obj.registrado_por.get_full_name().strip()
                or obj.registrado_por.username
            ),
        )
    if isinstance(obj, NotaCredito):
        d.update(documento_numero=obj.documento.numero_documento)
    if isinstance(obj,MovimientoBodega):
        d.update(fecha_registro=obj.fecha_registro,articulo=str(obj.repuesto))
        try: d['responsable']=str(obj.recepcioningreso.responsable)
        except RecepcionIngreso.DoesNotExist: d['responsable']='Sin registro'
        try:
            receipt = obj.recepcioningreso
            worker = receipt.responsable
            d.update(responsable_id=worker.pk, responsable=worker.get_full_name().strip() or worker.username,
                     unidad_medida=receipt.unidad_medida, factura_id=receipt.factura_id,
                     precio_unitario_neto=receipt.precio_unitario_neto, subtotal_neto=receipt.subtotal_neto)
        except RecepcionIngreso.DoesNotExist:
            d.update(responsable_id=None, unidad_medida=obj.repuesto.unidad_medida)
    return d


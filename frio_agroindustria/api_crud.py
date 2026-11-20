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
        return JsonResponse({'items':[serialize(x) for x in qs], 'fields':schema(formclass()),'can_write':allowed(request.user,roles),'can_delete':resource in ('clientes','trabajadores')})
    form=formclass(data(request))
    if resource=='facturas' and form.is_valid() and form.cleaned_data['monto']<=0:
        form.add_error('monto','El monto debe ser mayor que cero.')
    if not form.is_valid(): return JsonResponse({'errors':form.errors},status=400)
    try:
        with transaction.atomic():
            obj=form.save()
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
    if request.method=='GET': return JsonResponse({'item':serialize(obj),'fields':schema(formclass(instance=obj))})
    d=data(request)
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
            merged = model_to_dict(obj)
            merged.update(d)
            form = formclass(merged, instance=obj)
            if resource == 'facturas' and form.is_valid() and form.cleaned_data['monto'] <= 0:
                form.add_error('monto', 'El monto debe ser mayor que cero.')
            if not form.is_valid():
                return JsonResponse({'errors': form.errors}, status=400)
            obj = form.save()
            registrar_cambio(request.user, 'EDITAR', obj, antes=antes)
    except model.DoesNotExist:
        return error('Registro no encontrado.', 404)
    except IntegrityError:
        return error('No se pudo guardar el registro.')
    return JsonResponse({'item': serialize(obj)})
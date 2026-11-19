"""Operaciones comunes del catálogo con controles de rol en el servidor."""
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from usuarios.forms import TrabajadorEditarForm
from frio_agroindustria.api_common import error, data, allowed, schema, serialize
from frio_agroindustria.api_resources import RESOURCES
from inventario.api import movements

@require_http_methods(['GET','POST'])
def collection(request,resource):
    if not request.user.is_authenticated: return error('Inicia sesión.',401)
    if resource in ('ingresos','salidas','kardex'):
        return movements(request,resource)
    if resource not in RESOURCES: return error('Recurso no encontrado.',404)
    model,formclass,roles=RESOURCES[resource]
    read_stock=resource=='articulos' and request.method=='GET'
    if not read_stock and not allowed(request.user,roles): return error('No tienes permisos.',403)
    if request.method=='GET':
        return JsonResponse({'items':[serialize(x) for x in model.objects.order_by('pk')], 'fields':schema(formclass()),'can_write':allowed(request.user,roles),'can_delete':resource in ('clientes','trabajadores')})
    form=formclass(data(request))
    if resource=='facturas' and form.is_valid() and form.cleaned_data['monto']<=0:
        form.add_error('monto','El monto debe ser mayor que cero.')
    if not form.is_valid(): return JsonResponse({'errors':form.errors},status=400)
    try:
        with transaction.atomic(): obj=form.save()
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
        try: obj.delete()
        except ProtectedError: return error('Hay registros asociados; no se puede eliminar.')
        return JsonResponse({'ok':True})
    try:
        with transaction.atomic():
            obj = model.objects.select_for_update().get(pk=pk)
            form = formclass(d, instance=obj)
            if resource == 'facturas' and form.is_valid() and form.cleaned_data['monto'] <= 0:
                form.add_error('monto', 'El monto debe ser mayor que cero.')
            if not form.is_valid():
                return JsonResponse({'errors': form.errors}, status=400)
            obj = form.save()
    except model.DoesNotExist:
        return error('Registro no encontrado.', 404)
    except IntegrityError:
        return error('No se pudo guardar el registro.')
    return JsonResponse({'item': serialize(obj)})

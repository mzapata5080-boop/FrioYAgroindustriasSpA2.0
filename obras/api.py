from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods, require_GET
from frio_agroindustria.api_common import (
    allowed, error, data, schema, serialize, permission_denied,
)
from frio_agroindustria.common import (
    open_private_file,
    registrar_cambio,
    save_private_file,
    snapshot_instance,
    worker_display,
)
from frio_agroindustria.models import ArchivoPrivado
from inventario.models import Repuesto
from obras.forms import ObraForm, PresupuestoForm, SolicitudMaterialForm
from obras.models import Obra, Presupuesto, SolicitudMaterial
from reportes.filters import FILTER_FIELDS, InvalidReportFilter, filter_queryset


SUPERVISOR_ROLES = ('supervisor de obra', 'supervisor', 'obras')


def is_supervisor_only(user):
    return user.is_authenticated and not user.is_superuser and user.rol in SUPERVISOR_ROLES


def obras_queryset_for(user):
    qs = Obra.objects.select_related('cliente', 'supervisor', 'creado_por').prefetch_related('tecnicos')
    if user.is_superuser or user.rol in ('gerencia', 'bodega', 'finanzas'):
        return qs
    if is_supervisor_only(user):
        return qs.filter(Q(supervisor=user) | Q(tecnicos=user)).distinct()
    return qs.none()


def can_access_obra(user, obra):
    if user.is_superuser or user.rol in ('gerencia', 'bodega', 'finanzas'):
        return True
    if is_supervisor_only(user):
        return obra.supervisor_id == user.pk or obra.tecnicos.filter(pk=user.pk).exists()
    return False


def serialize_obra(obra):
    row = serialize(obra)
    tecnicos_qs = list(obra.tecnicos.all())
    row['tecnicos'] = [t.pk for t in tecnicos_qs]
    row['tecnicos_detalle'] = [
        {'id': t.pk, 'nombre': t.get_full_name().strip() or t.username}
        for t in tecnicos_qs
    ]
    if obra.cliente_id:
        row['cliente_nombre'] = obra.cliente.razon_social
    if obra.supervisor_id:
        row['supervisor_nombre'] = obra.supervisor.get_full_name().strip() or obra.supervisor.username
    row['presupuesto_activo_id'] = (
        obra.presupuestos.filter(estado='APROBADO').values_list('id', flat=True).first()
    )
    return row


def serialize_solicitud(sol):
    row = serialize(sol)
    sol_id, sol_name = worker_display(sol.solicitado_por)
    apr_id, apr_name = worker_display(sol.aprobado_por)
    row.update(
        obra_codigo=sol.obra.codigo_ot,
        obra_nombre=sol.obra.nombre,
        cliente_id=sol.obra.cliente_id,
        cliente_nombre=str(sol.obra.cliente),
        articulo_codigo=sol.articulo.codigo_parte,
        articulo_nombre=str(sol.articulo),
        unidad_medida=sol.articulo.unidad_medida,
        cantidad_pendiente=sol.cantidad_pendiente,
        solicitado_por_id=sol_id,
        solicitado_por_nombre=sol_name,
        aprobado_por_id=apr_id,
        aprobado_por_nombre=apr_name,
        creado_el=sol.creado_el,
    )
    return row


def serialize_presupuesto(pres):
    row = serialize(pres)
    apr_id, apr_name = worker_display(pres.aprobado_por)
    row.update(
        obra_codigo=pres.obra.codigo_ot,
        obra_nombre=pres.obra.nombre,
        total_estimado=pres.total_estimado,
        aprobado_por_id=apr_id,
        aprobado_por_nombre=apr_name,
        creado_el=pres.creado_el,
    )
    return row


def _filter_form_obras(form, user):
    if 'obra' in form.fields:
        form.fields['obra'].queryset = obras_queryset_for(user)
    return form


def obras_collection(request):
    roles = ('gerencia', 'bodega', 'finanzas', *SUPERVISOR_ROLES)
    if not allowed(request.user, roles):
        return permission_denied()
    can_write = allowed(request.user, ('gerencia', *SUPERVISOR_ROLES))
    if request.method == 'GET':
        try:
            qs = filter_queryset('obras', obras_queryset_for(request.user), request.GET)
        except InvalidReportFilter as exc:
            return error(str(exc), 400)
        form = ObraForm()
        if is_supervisor_only(request.user):
            form.fields['supervisor'].initial = request.user.pk
        return JsonResponse({
            'items': [serialize_obra(o) for o in qs],
            'fields': schema(form),
            'filter_fields': FILTER_FIELDS['obras'],
            'can_write': can_write,
            'can_delete': False,
        })
    if not can_write:
        return permission_denied()
    payload = data(request)
    if is_supervisor_only(request.user):
        payload['supervisor'] = request.user.pk
    form = ObraForm(payload)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    try:
        with transaction.atomic():
            obra = form.save(commit=False)
            obra.creado_por = request.user
            obra.save()
            form.save_m2m()
            registrar_cambio(request.user, 'CREAR', obra)
    except IntegrityError:
        return error('Ya existe una obra con ese código OT o referencias inválidas.')
    return JsonResponse({'item': serialize_obra(obra)}, status=201)


def obra_detail(request, pk):
    roles = ('gerencia', 'bodega', 'finanzas', *SUPERVISOR_ROLES)
    if not allowed(request.user, roles):
        return permission_denied()
    obra = Obra.objects.select_related('cliente', 'supervisor', 'creado_por').prefetch_related('tecnicos').filter(pk=pk).first()
    if obra is None:
        return error('Obra no encontrada.', 404)
    if not can_access_obra(request.user, obra):
        return permission_denied()
    if request.method == 'GET':
        docs = list(
            ArchivoPrivado.objects.filter(modelo='obras.obra', objeto_id=str(obra.pk)).values(
                'id', 'nombre_original', 'tamano_bytes', 'creado_el'
            )
        )
        return JsonResponse({
            'item': serialize_obra(obra),
            'fields': schema(ObraForm(instance=obra)),
            'documentos': docs,
        })
    if not allowed(request.user, ('gerencia', *SUPERVISOR_ROLES)):
        return permission_denied()
    payload = data(request)
    if is_supervisor_only(request.user) and obra.supervisor_id != request.user.pk:
        return permission_denied()
    try:
        with transaction.atomic():
            obra_locked = Obra.objects.select_for_update().get(pk=pk)
            antes = snapshot_instance(obra_locked)
            if is_supervisor_only(request.user):
                payload['supervisor'] = obra_locked.supervisor_id
            form = ObraForm(payload, instance=obra_locked)
            if not form.is_valid():
                return JsonResponse({'errors': form.errors}, status=400)
            obra_saved = form.save()
            registrar_cambio(request.user, 'EDITAR', obra_saved, antes=antes)
    except IntegrityError:
        return error('No se pudo actualizar la obra.')
    return JsonResponse({'item': serialize_obra(obra_saved)})


def presupuestos_collection(request):
    roles = ('gerencia', 'finanzas', *SUPERVISOR_ROLES)
    if not allowed(request.user, roles):
        return permission_denied()
    allowed_obras = obras_queryset_for(request.user)
    if request.method == 'GET':
        qs = (
            Presupuesto.objects.select_related('obra', 'aprobado_por')
            .filter(obra__in=allowed_obras)
            .order_by('-creado_el', '-pk')
        )
        form = _filter_form_obras(PresupuestoForm(), request.user)
        return JsonResponse({
            'items': [serialize_presupuesto(p) for p in qs],
            'fields': schema(form),
            'can_write': True,
            'can_delete': False,
        })
    form = _filter_form_obras(PresupuestoForm(data(request)), request.user)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    try:
        with transaction.atomic():
            pres = form.save(commit=False)
            if pres.estado == 'APROBADO':
                pres.aprobado_por = request.user
            pres.save()
            registrar_cambio(request.user, 'CREAR', pres)
    except IntegrityError:
        return error('Ya existe esa versión de presupuesto para esta obra.')
    return JsonResponse({'item': serialize_presupuesto(pres)}, status=201)


def solicitudes_collection(request):
    roles = ('gerencia', 'bodega', *SUPERVISOR_ROLES)
    if not allowed(request.user, roles):
        return permission_denied()
    allowed_obras = obras_queryset_for(request.user)
    if request.method == 'GET':
        qs = (
            SolicitudMaterial.objects.select_related('obra__cliente', 'articulo', 'solicitado_por', 'aprobado_por')
            .filter(obra__in=allowed_obras)
            .order_by('-creado_el', '-pk')
        )
        try:
            qs = filter_queryset('solicitudes', qs, request.GET)
        except InvalidReportFilter as exc:
            return error(str(exc), 400)
        form = _filter_form_obras(SolicitudMaterialForm(), request.user)
        return JsonResponse({
            'items': [serialize_solicitud(s) for s in qs],
            'fields': schema(form),
            'filter_fields': FILTER_FIELDS['solicitudes'],
            'can_write': allowed(request.user, ('gerencia', *SUPERVISOR_ROLES)),
            'can_delete': False,
            'articles': list(
                Repuesto.objects.filter(activo=True).values(
                    'id', 'codigo_parte', 'descripcion', 'unidad_medida', 'stock_actual', 'stock_reservado'
                )
            ),
        })
    if not allowed(request.user, ('gerencia', *SUPERVISOR_ROLES)):
        return permission_denied()
    form = _filter_form_obras(SolicitudMaterialForm(data(request)), request.user)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    with transaction.atomic():
        sol = form.save(commit=False)
        sol.solicitado_por = request.user
        sol.estado = 'PENDIENTE'
        sol.save()
        registrar_cambio(request.user, 'CREAR', sol)
    return JsonResponse({'item': serialize_solicitud(sol)}, status=201)


def solicitud_detail(request, pk):
    """Gestiona consulta y transiciones de estado: aprobar (reservar), rechazar y cancelar (liberar)."""
    roles = ('gerencia', 'bodega', *SUPERVISOR_ROLES)
    if not allowed(request.user, roles):
        return permission_denied()
    sol = (
        SolicitudMaterial.objects.select_related('obra__cliente', 'articulo', 'solicitado_por', 'aprobado_por')
        .filter(pk=pk)
        .first()
    )
    if sol is None:
        return error('Solicitud no encontrada.', 404)
    if not can_access_obra(request.user, sol.obra):
        return permission_denied()
    if request.method == 'GET':
        return JsonResponse({'item': serialize_solicitud(sol), 'fields': []})

    payload = data(request)
    accion = (payload.get('accion') or '').strip().lower()
    if accion not in ('aprobar', 'rechazar', 'cancelar'):
        return error('Acción inválida. Usa aprobar, rechazar o cancelar.', 400)

    if accion in ('aprobar', 'rechazar') and not allowed(request.user, ('gerencia', 'bodega')):
        return permission_denied()

    with transaction.atomic():
        sol_locked = SolicitudMaterial.objects.select_for_update().select_related('obra', 'articulo').get(pk=pk)
        article = Repuesto.objects.select_for_update().get(pk=sol_locked.articulo_id)
        antes = snapshot_instance(sol_locked)

        if accion == 'aprobar':
            if sol_locked.estado != 'PENDIENTE':
                return error('Solo se pueden aprobar solicitudes en estado pendiente.', 400)
            if article.stock_disponible < sol_locked.cantidad_solicitada:
                return error('No hay stock disponible suficiente para reservar esta solicitud.', 400)
            article.stock_reservado += sol_locked.cantidad_solicitada
            article.save(update_fields=['stock_reservado'])
            sol_locked.cantidad_reservada = sol_locked.cantidad_solicitada
            sol_locked.estado = 'APROBADA'
            sol_locked.aprobado_por = request.user
            sol_locked.save(update_fields=['cantidad_reservada', 'estado', 'aprobado_por', 'actualizado_el'])
            registrar_cambio(request.user, 'EDITAR', sol_locked, antes=antes)

        elif accion == 'rechazar':
            if sol_locked.estado != 'PENDIENTE':
                return error('Solo se pueden rechazar solicitudes en estado pendiente.', 400)
            sol_locked.estado = 'RECHAZADA'
            sol_locked.motivo_rechazo = (payload.get('motivo_rechazo') or '').strip()
            sol_locked.aprobado_por = request.user
            sol_locked.save(update_fields=['estado', 'motivo_rechazo', 'aprobado_por', 'actualizado_el'])
            registrar_cambio(request.user, 'EDITAR', sol_locked, antes=antes)

        elif accion == 'cancelar':
            if sol_locked.estado == 'ENTREGADA':
                return error('No se puede cancelar una solicitud ya entregada.', 400)
            if sol_locked.estado in ('CANCELADA', 'RECHAZADA'):
                return error('La solicitud ya se encuentra cerrada.', 400)
            pendiente_reserva = sol_locked.cantidad_pendiente
            if sol_locked.estado in ('APROBADA', 'PARCIAL') and pendiente_reserva > 0:
                article.stock_reservado = max(article.stock_reservado - pendiente_reserva, article.stock_reservado * 0)
                article.save(update_fields=['stock_reservado'])
                sol_locked.cantidad_reservada = sol_locked.cantidad_entregada
            sol_locked.estado = 'CANCELADA'
            sol_locked.save(update_fields=['cantidad_reservada', 'estado', 'actualizado_el'])
            registrar_cambio(request.user, 'EDITAR', sol_locked, antes=antes)

    return JsonResponse({'item': serialize_solicitud(sol_locked)})


@require_http_methods(['GET', 'POST'])
def obra_documentos(request, obra_pk):
    """Lista, sube y descarga documentos privados asociados a una Obra respetando permisos del supervisor."""
    roles = ('gerencia', 'bodega', 'finanzas', *SUPERVISOR_ROLES)
    if not allowed(request.user, roles):
        return permission_denied()
    obra = Obra.objects.filter(pk=obra_pk).first()
    if obra is None:
        return error('Obra no encontrada.', 404)
    if not can_access_obra(request.user, obra):
        return permission_denied()

    if request.method == 'GET':
        doc_id = request.GET.get('descargar')
        if doc_id:
            doc = ArchivoPrivado.objects.filter(pk=doc_id, modelo='obras.obra', objeto_id=str(obra.pk)).first()
            if doc is None:
                return error('Documento no encontrado.', 404)
            fh = open_private_file(doc.ruta_privada)
            return FileResponse(fh, as_attachment=True, filename=doc.nombre_original)
        docs = list(
            ArchivoPrivado.objects.filter(modelo='obras.obra', objeto_id=str(obra.pk)).values(
                'id', 'nombre_original', 'tamano_bytes', 'subido_por_id', 'creado_el'
            )
        )
        return JsonResponse({'items': docs})

    uploaded = request.FILES.get('archivo')
    try:
        meta = save_private_file(uploaded, 'obras')
    except Exception as exc:
        return error(str(exc), 400)
    doc = ArchivoPrivado.objects.create(
        modulo='obras',
        modelo='obras.obra',
        objeto_id=str(obra.pk),
        nombre_original=meta['nombre_original'],
        ruta_privada=meta['ruta_privada'],
        tamano_bytes=meta['tamano_bytes'],
        subido_por=request.user,
    )
    registrar_cambio(request.user, 'CREAR', doc)
    return JsonResponse(
        {
            'item': {
                'id': doc.pk,
                'nombre_original': doc.nombre_original,
                'tamano_bytes': doc.tamano_bytes,
                'subido_por_id': doc.subido_por_id,
            }
        },
        status=201,        
    )



@require_GET
def archivo_descargar(request, archivo_id):
    roles = ('gerencia', 'bodega', 'finanzas', *SUPERVISOR_ROLES)
    if not allowed(request.user, roles):
        return permission_denied()
    archivo = get_object_or_404(
        ArchivoPrivado,
        pk=archivo_id,
        modulo='obras',
        modelo='obras.obra',
    )
    obra = Obra.objects.filter(pk=archivo.objeto_id).first()
    if not obra or not can_access_obra(request.user, obra):
        return permission_denied()
    fh = open_private_file(archivo.ruta_privada)
    return FileResponse(fh, as_attachment=True, filename=archivo.nombre_original)
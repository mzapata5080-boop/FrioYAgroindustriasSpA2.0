from django.contrib import admin
from django.urls import path
from . import api
from inventario import operaciones_api
from obras import api as obras_api
from finanzas import api as finanzas_api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/session/', api.session),
    path('api/login/', api.sign_in),
    path('api/logout/', api.sign_out),
    path('api/obras/', obras_api.obras_collection),
    path('api/obras/<int:pk>/', obras_api.obra_detail),
    path('api/obras/<int:obra_pk>/documentos/', obras_api.obra_documentos),
    path('api/archivos/<int:archivo_id>/descargar/', obras_api.archivo_descargar),
    path('api/presupuestos/', obras_api.presupuestos_collection),
    path('api/solicitudes/', obras_api.solicitudes_collection),
    path('api/solicitudes/<int:pk>/', obras_api.solicitud_detail),
    path('api/operaciones/', operaciones_api.operaciones),
    path('api/operaciones/<uuid:operacion_id>/archivos/', operaciones_api.documentos),
    path('api/operaciones/<uuid:operacion_id>/archivos/<int:archivo_id>/', operaciones_api.descargar_documento),
    path('api/documentos-venta/<int:pk>/pagos/', finanzas_api.documento_pagos),
    path('api/presupuestos-venta/<int:pk>/decision/', finanzas_api.presupuesto_decision),
    path('api/documentos-venta/<int:pk>/anular/', finanzas_api.documento_anular),
    path('api/<str:resource>/', api.collection),
    path('api/<str:resource>/<int:pk>/', api.detail),
]

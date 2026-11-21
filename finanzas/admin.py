from django.contrib import admin
from .models import (
    Cliente,
    Proveedor,
    FacturaCompra
)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        'rut',
        'razon_social',
        'representante',
        'cargo_contacto',
        'correo',
        'telefono'
    )
    search_fields = (
        'rut',
        'razon_social',
        'representante',
        'correo'
    )
    readonly_fields = ('creado_el',)


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = (
        'rut',
        'razon_social',
        'encargado_pagos',
        'correo_pagos',
        'email',
        'telefono'
    )
    search_fields = (
        'rut',
        'razon_social',
        'encargado_pagos',
        'correo_pagos',
        'email'
    )
    readonly_fields = ('creado_el',)


admin.site.register(FacturaCompra)
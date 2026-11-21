from django.contrib import admin
from .models import (
    Cliente,
    Proveedor,
    FacturaCompra,
    FacturaCompraDetalle
)
from .forms import (
    FacturaCompraForm,
    FacturaCompraDetalleForm,
    FacturaCompraDetalleInlineFormSet
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



class FacturaCompraDetalleInline(admin.TabularInline):
    model = FacturaCompraDetalle
    form = FacturaCompraDetalleForm
    formset = FacturaCompraDetalleInlineFormSet
    extra = 1


@admin.register(FacturaCompra)
class FacturaCompraAdmin(admin.ModelAdmin):
    form = FacturaCompraForm
    list_display = (
        'numero_documento',
        'proveedor',
        'fecha',
        'monto',
        'cantidad_detalles'
    )
    search_fields = ('numero_documento', 'proveedor__razon_social')
    readonly_fields = ('creado_el',)
    inlines = (FacturaCompraDetalleInline,)

    @admin.display(description="Artículos")
    def cantidad_detalles(self, obj):
        return obj.detalles.count()
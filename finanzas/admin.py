from django.contrib import admin
from django.core.exceptions import ValidationError
from .models import (
    Cliente,
    Proveedor,
    FacturaCompra,
    FacturaCompraDetalle,
    Presupuesto,
    PresupuestoDetalle,
    DocumentoVenta,
    PagoDocumento,
    NotaCredito,
)
from .forms import (
    FacturaCompraForm,
    FacturaCompraDetalleForm,
    FacturaCompraDetalleInlineFormSet,
    PresupuestoForm,
    PresupuestoDetalleForm,
    DocumentoVentaForm,
    PagoDocumentoForm,
    NotaCreditoForm,
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


class PresupuestoDetalleInline(admin.TabularInline):
    model = PresupuestoDetalle
    form = PresupuestoDetalleForm
    extra = 1


@admin.register(Presupuesto)
class PresupuestoAdmin(admin.ModelAdmin):
    form = PresupuestoForm
    list_display = ("numero", "cliente", "obra", "fecha", "estado", "total")
    list_filter = ("estado", "fecha")
    search_fields = ("numero", "cliente__razon_social", "obra__codigo_ot")
    readonly_fields = (
        "estado", "motivo_rechazo", "aprobado_por", "aprobado_el",
        "rechazado_por", "rechazado_el", "creado_el",
    )
    inlines = (PresupuestoDetalleInline,)
    actions = ("aprobar_presupuestos",)

    @admin.display(description="Total")
    def total(self, obj):
        return obj.total

    @admin.action(
        description="Aprobar presupuestos seleccionados",
        permissions=("approve",),
    )
    def aprobar_presupuestos(self, request, queryset):
        aprobados = 0
        for presupuesto in queryset:
            try:
                presupuesto.aprobar(request.user)
            except ValidationError as exc:
                self.message_user(
                    request,
                    f"{presupuesto}: {' '.join(exc.messages)}",
                    level="error",
                )
            else:
                aprobados += 1
        if aprobados:
            self.message_user(request, f"{aprobados} presupuesto(s) aprobado(s).")

    def has_approve_permission(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "finanzas.aprobar_presupuesto"
        )


class PagoDocumentoInline(admin.TabularInline):
    model = PagoDocumento
    extra = 0
    can_delete = False
    fields = ("monto", "fecha_pago", "metodo", "referencia", "registrado_por")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class NotaCreditoInline(admin.TabularInline):
    model = NotaCredito
    extra = 0
    can_delete = False
    fields = ("numero_documento", "fecha", "motivo", "monto", "registrado_por")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DocumentoVenta)
class DocumentoVentaAdmin(admin.ModelAdmin):
    form = DocumentoVentaForm
    list_display = (
        "numero_documento", "cliente", "fecha", "vencimiento", "total",
        "saldo", "anulado",
    )
    list_filter = ("anulado", "fecha", "vencimiento")
    search_fields = ("numero_documento", "cliente__razon_social")
    readonly_fields = (
        "saldo", "anulado", "motivo_anulacion", "anulado_por", "anulado_el",
        "creado_el",
    )
    inlines = (PagoDocumentoInline, NotaCreditoInline)


@admin.register(PagoDocumento)
class PagoDocumentoAdmin(admin.ModelAdmin):
    form = PagoDocumentoForm
    list_display = (
        "documento", "monto", "fecha_pago", "metodo", "registrado_por"
    )
    list_filter = ("metodo", "fecha_pago")
    search_fields = ("documento__numero_documento", "referencia")
    exclude = ("registrado_por",)
    readonly_fields = ("creado_el",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        return obj is None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "finanzas.registrar_pago_documento"
        )


@admin.register(NotaCredito)
class NotaCreditoAdmin(admin.ModelAdmin):
    form = NotaCreditoForm
    list_display = (
        "numero_documento", "documento", "fecha", "monto", "registrado_por"
    )
    list_filter = ("fecha",)
    search_fields = ("numero_documento", "documento__numero_documento", "motivo")
    exclude = ("registrado_por",)
    readonly_fields = ("creado_el",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        return obj is None

    def has_delete_permission(self, request, obj=None):
        return False
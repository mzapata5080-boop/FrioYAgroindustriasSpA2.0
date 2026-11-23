import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.utils import timezone
from .validators import validar_rut_chileno


class Cliente(models.Model):

    rut = models.CharField(
        max_length=12,
        unique=True,
        validators=[validar_rut_chileno]
    )

    razon_social = models.CharField(
        max_length=150
    )

    telefono = models.CharField(
        max_length=20
    )

    correo = models.EmailField()

    direccion = models.CharField(
        max_length=200
    )

    representante = models.CharField(
        max_length=150,
        default="",
        blank=True,
        verbose_name="Representante"
    )

    cargo_contacto = models.CharField(
        max_length=100,
        default="",
        blank=True,
        verbose_name="Cargo del contacto"
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return f"{self.rut} - {self.razon_social}"


class Proveedor(models.Model):

    rut = models.CharField(
        max_length=12,
        unique=True,
        validators=[validar_rut_chileno]
    )

    razon_social = models.CharField(
        max_length=150
    )

    giro = models.CharField(
        max_length=100
    )

    telefono = models.CharField(
        max_length=20
    )

    email = models.EmailField()

    direccion = models.CharField(
        max_length=200
    )

    encargado_pagos = models.CharField(
        max_length=150,
        default="",
        blank=True,
        verbose_name="Encargado de pagos"
    )

    correo_pagos = models.EmailField(
        default="",
        blank=True,
        verbose_name="Correo de pagos"
    )

    banco = models.CharField(
        max_length=100,
        default="",
        blank=True
    )

    tipo_cuenta = models.CharField(
        max_length=50,
        choices=[
            ('Corriente', 'Corriente'),
            ('Vista', 'Vista'),
            ('Ahorro', 'Ahorro'),
        ],
        default="",
        blank=True
    )

    numero_cuenta = models.CharField(
        max_length=50,
        default="",
        blank=True
    )
    
    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"

    def __str__(self):
        return f"{self.rut} - {self.razon_social}"
    
class FacturaCompra(models.Model):

    proveedor = models.ForeignKey(
    Proveedor,
    on_delete=models.PROTECT
    )

    fecha = models.DateField()

    numero_documento = models.CharField(
        max_length=50
    )

    tipo_documento = models.CharField(
        max_length=50
    )

    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    observaciones = models.TextField(
        max_length=1000,
        default="",
        blank=True,
        verbose_name="Observaciones"
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.numero_documento


class FacturaCompraDetalle(models.Model):

    factura = models.ForeignKey(
        FacturaCompra,
        on_delete=models.CASCADE,
        related_name="detalles"
    )

    articulo = models.ForeignKey(
        "inventario.Repuesto",
        on_delete=models.PROTECT,
        related_name="detalles_factura_compra"
    )

    cantidad = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )

    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Precio unitario"
    )

    class Meta:
        verbose_name = "Detalle de factura de compra"
        verbose_name_plural = "Detalles de factura de compra"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name="fyag_fact_det_qty_pos"
            ),
            models.CheckConstraint(
                condition=models.Q(precio_unitario__gte=0),
                name="fyag_fact_det_price_nonneg"
            ),
        ]

    def __str__(self):
        return f"{self.articulo} x {self.cantidad}"


class RecepcionCompra(models.Model):

    solicitud_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    factura = models.ForeignKey(
        FacturaCompra,
        on_delete=models.PROTECT,
        related_name="recepciones_compra"
    )

    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recepciones_compra"
    )

    recibida_el = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Recepción de compra"
        verbose_name_plural = "Recepciones de compra"
        ordering = ["-recibida_el"]

    def __str__(self):
        return f"{self.factura} - {self.solicitud_id}"


class RecepcionDetalle(models.Model):

    recepcion = models.ForeignKey(
        RecepcionCompra,
        on_delete=models.CASCADE,
        related_name="detalles"
    )

    detalle_factura = models.ForeignKey(
        FacturaCompraDetalle,
        on_delete=models.PROTECT,
        related_name="recepciones"
    )

    cantidad = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )

    movimiento = models.OneToOneField(
        "inventario.MovimientoBodega",
        on_delete=models.PROTECT,
        related_name="detalle_recepcion_compra"
    )

    class Meta:
        verbose_name = "Detalle de recepción"
        verbose_name_plural = "Detalles de recepción"
        constraints = [
            models.UniqueConstraint(
                fields=["recepcion", "detalle_factura"],
                name="fyag_recep_line_unica"
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name="fyag_recep_cantidad_pos"
            ),
        ]

    def __str__(self):
        return f"{self.detalle_factura.articulo} x {self.cantidad}"


class Presupuesto(models.Model):
    ESTADOS = [
        ("BORRADOR", "Borrador"),
        ("APROBADO", "Aprobado"),
        ("RECHAZADO", "Rechazado"),
    ]

    numero = models.CharField(max_length=50, unique=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="presupuestos_venta",
    )
    obra = models.ForeignKey(
        "obras.Obra",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="presupuestos_venta",
    )
    fecha = models.DateField(default=timezone.localdate)
    vencimiento = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="BORRADOR")
    observaciones = models.TextField(blank=True, default="")
    motivo_rechazo = models.TextField(blank=True, default="")
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="presupuestos_venta_aprobados",
    )
    aprobado_el = models.DateTimeField(null=True, blank=True)
    rechazado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="presupuestos_venta_rechazados",
    )
    rechazado_el = models.DateTimeField(null=True, blank=True)
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_el", "-pk"]
        permissions = [
            ("aprobar_presupuesto", "Puede aprobar o rechazar presupuestos"),
        ]

    @property
    def total(self):
        return sum(
            (detalle.subtotal for detalle in self.detalles.all()),
            Decimal("0.00"),
        )

    def clean(self):
        if self.obra_id and self.cliente_id and self.obra.cliente_id != self.cliente_id:
            raise ValidationError(
                {"obra": "La obra seleccionada pertenece a otro cliente."}
            )
        if self.vencimiento and self.fecha and self.vencimiento < self.fecha:
            raise ValidationError(
                {"vencimiento": "El vencimiento no puede ser anterior a la fecha."}
            )
        if self.pk and self.estado != "BORRADOR":
            raise ValidationError("Solo se pueden editar presupuestos en borrador.")

    def aprobar(self, usuario):
        if self.estado != "BORRADOR":
            raise ValidationError("Solo se puede aprobar un presupuesto en borrador.")
        if not self.detalles.exists():
            raise ValidationError("Agregue al menos un artículo antes de aprobar.")
        self.estado = "APROBADO"
        self.aprobado_por = usuario
        self.aprobado_el = timezone.now()
        self.motivo_rechazo = ""
        self.save(update_fields=(
            "estado", "aprobado_por", "aprobado_el", "motivo_rechazo"
        ))

    def rechazar(self, usuario, motivo):
        motivo = (motivo or "").strip()
        if self.estado != "BORRADOR":
            raise ValidationError("Solo se puede rechazar un presupuesto en borrador.")
        if not motivo:
            raise ValidationError({"motivo": "Indique el motivo del rechazo."})
        self.estado = "RECHAZADO"
        self.rechazado_por = usuario
        self.rechazado_el = timezone.now()
        self.motivo_rechazo = motivo
        self.save(update_fields=(
            "estado", "rechazado_por", "rechazado_el", "motivo_rechazo"
        ))

    def __str__(self):
        return self.numero


class PresupuestoDetalle(models.Model):
    presupuesto = models.ForeignKey(
        Presupuesto,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    articulo = models.ForeignKey(
        "inventario.Repuesto",
        on_delete=models.PROTECT,
        related_name="detalles_presupuesto_venta",
    )
    cantidad = models.DecimalField(max_digits=15, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name="fyag_pres_det_qty_pos",
            ),
            models.CheckConstraint(
                condition=models.Q(precio_unitario__gte=0),
                name="fyag_pres_det_price_nonneg",
            ),
        ]

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def clean(self):
        if self.presupuesto_id and self.presupuesto.estado != "BORRADOR":
            raise ValidationError(
                "No se puede modificar el detalle de un presupuesto resuelto."
            )
        if self.cantidad is not None and self.cantidad <= 0:
            raise ValidationError({"cantidad": "La cantidad debe ser mayor que cero."})
        if self.precio_unitario is not None and self.precio_unitario < 0:
            raise ValidationError(
                {"precio_unitario": "El precio no puede ser negativo."}
            )
        if (
            self.articulo_id
            and self.cantidad is not None
            and self.articulo.unidad_medida == "unidad"
            and self.cantidad != self.cantidad.to_integral_value()
        ):
            raise ValidationError(
                {"cantidad": "La cantidad debe ser entera para artículos por unidad."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.presupuesto.estado != "BORRADOR":
            raise ValidationError(
                "No se puede eliminar el detalle de un presupuesto resuelto."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.articulo} x {self.cantidad}"


class DocumentoVenta(models.Model):
    numero_documento = models.CharField(max_length=50, unique=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="documentos_venta",
    )
    obra = models.ForeignKey(
        "obras.Obra",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documentos_venta",
    )
    fecha = models.DateField(default=timezone.localdate)
    vencimiento = models.DateField()
    total = models.DecimalField(max_digits=14, decimal_places=2)
    saldo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True, default="")
    anulado = models.BooleanField(default=False)
    motivo_anulacion = models.TextField(blank=True, default="")
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documentos_venta_anulados",
    )
    anulado_el = models.DateTimeField(null=True, blank=True)
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        permissions = [
            ("anular_documento_venta", "Puede anular documentos de venta"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gt=0), name="fyag_doc_venta_total_pos"),
            models.CheckConstraint(condition=models.Q(saldo__gte=0), name="fyag_doc_venta_saldo_no_neg"),
        ]

    def clean(self):
        if self.total is not None and self.total <= 0:
            raise ValidationError({"total": "El total debe ser mayor que cero."})
        if self.vencimiento and self.fecha and self.vencimiento < self.fecha:
            raise ValidationError(
                {"vencimiento": "El vencimiento no puede ser anterior a la fecha."}
            )
        if self.obra_id and self.cliente_id and self.obra.cliente_id != self.cliente_id:
            raise ValidationError(
                {"obra": "La obra seleccionada pertenece a otro cliente."}
            )
        if self.pk:
            actual = type(self).objects.get(pk=self.pk)
            if actual.total != self.total and (
                self.pagos.exists() or self.notas_credito.exists()
            ):
                raise ValidationError(
                    {"total": "No se puede cambiar el total con pagos o notas de crédito."}
                )

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.saldo = self.total
        elif self.pk and not self.pagos.exists() and not self.notas_credito.exists():
            self.saldo = self.total
        return super().save(*args, **kwargs)

    def anular_documento(self, usuario, motivo):
        motivo = (motivo or "").strip()
        if self.anulado:
            raise ValidationError("El documento ya está anulado.")
        if not motivo:
            raise ValidationError({"motivo": "Indique el motivo de la anulación."})
        if self.pagos.exists() or self.notas_credito.exists():
            raise ValidationError(
                "No se puede anular un documento con pagos o notas de crédito registrados."
            )
        self.anulado = True
        self.motivo_anulacion = motivo
        self.anulado_por = usuario
        self.anulado_el = timezone.now()
        self.save(update_fields=(
            "anulado", "motivo_anulacion", "anulado_por", "anulado_el"
        ))

    def __str__(self):
        return self.numero_documento


class PagoDocumento(models.Model):
    METODOS = [
        ("EFECTIVO", "Efectivo"),
        ("TRANSFERENCIA", "Transferencia"),
        ("TARJETA", "Tarjeta"),
        ("CHEQUE", "Cheque"),
        ("OTRO", "Otro"),
    ]

    documento = models.ForeignKey(
        DocumentoVenta,
        on_delete=models.PROTECT,
        related_name="pagos",
    )
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    fecha_pago = models.DateField(default=timezone.localdate)
    metodo = models.CharField(max_length=20, choices=METODOS, default="TRANSFERENCIA")
    referencia = models.CharField(max_length=100, blank=True, default="")
    observaciones = models.TextField(blank=True, default="")
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pagos_documentos_registrados",
    )
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_pago", "-pk"]
        permissions = [
            ("registrar_pago_documento", "Puede registrar pagos de documentos"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name="fyag_pago_doc_monto_pos"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Los pagos son inmutables; registre una corrección por separado.")
        if self.monto is None or self.monto <= 0:
            raise ValidationError({"monto": "El monto del pago debe ser mayor que cero."})
        with transaction.atomic():
            documento = DocumentoVenta.objects.select_for_update().get(pk=self.documento_id)
            if documento.anulado:
                raise ValidationError("No se pueden registrar pagos en un documento anulado.")
            if self.monto > documento.saldo:
                raise ValidationError({"monto": "El pago supera el saldo pendiente."})
            self.documento = documento
            super().save(*args, **kwargs)
            documento.saldo -= self.monto
            documento.save(update_fields=("saldo",))

    def delete(self, *args, **kwargs):
        raise ValidationError("Los pagos no se pueden eliminar.")

    def __str__(self):
        return f"{self.documento} - {self.monto}"


class NotaCredito(models.Model):
    documento = models.ForeignKey(
        DocumentoVenta,
        on_delete=models.PROTECT,
        related_name="notas_credito",
    )
    numero_documento = models.CharField(max_length=50, unique=True)
    fecha = models.DateField(default=timezone.localdate)
    motivo = models.TextField()
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    observaciones = models.TextField(blank=True, default="")
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notas_credito_registradas",
    )
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name="fyag_nota_cred_monto_pos"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Las notas de crédito son inmutables.")
        if self.monto is None or self.monto <= 0:
            raise ValidationError({"monto": "El monto debe ser mayor que cero."})
        if not self.motivo or not self.motivo.strip():
            raise ValidationError({"motivo": "Indique el motivo de la nota de crédito."})
        with transaction.atomic():
            documento = DocumentoVenta.objects.select_for_update().get(pk=self.documento_id)
            if documento.anulado:
                raise ValidationError("No se pueden emitir notas para un documento anulado.")
            if self.monto > documento.saldo:
                raise ValidationError(
                    {"monto": "El monto supera el saldo pendiente del documento."}
                )
            self.documento = documento
            super().save(*args, **kwargs)
            documento.saldo -= self.monto
            documento.save(update_fields=("saldo",))

    def delete(self, *args, **kwargs):
        raise ValidationError("Las notas de crédito no se pueden eliminar.")

    def __str__(self):
        return self.numero_documento
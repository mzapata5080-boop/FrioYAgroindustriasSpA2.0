from django.db import models
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
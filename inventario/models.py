from django.db import models
from django.conf import settings


class CategoriaRepuesto(models.Model):
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True, verbose_name='Activo')

    def __str__(self):
        return self.nombre


class Repuesto(models.Model):
    codigo_parte = models.CharField(max_length=50, unique=True, verbose_name='Código interno')
    descripcion = models.CharField(max_length=200, verbose_name='Nombre')
    ubicacion_bodega = models.CharField(max_length=50, verbose_name='Ubicación')
    unidad_medida = models.CharField(
        max_length=20,
        choices=[('unidad', 'Unidades'), ('m', 'Metros'), ('kg', 'Kilogramos'), ('l', 'Litros')],
        verbose_name='Unidad',
    )
    stock_actual = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Stock actual')
    stock_reservado = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Stock reservado')
    stock_minimo = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Stock mínimo')
    categoria = models.ForeignKey(CategoriaRepuesto, on_delete=models.PROTECT, verbose_name='Categoría')
    activo = models.BooleanField(default=True, verbose_name='Activo')

    @property
    def stock_disponible(self):
        return self.stock_actual - self.stock_reservado

    def __str__(self):
        return f'{self.codigo_parte} — {self.descripcion}'


class MovimientoBodega(models.Model):
    tipo = models.CharField(max_length=10)
    cantidad = models.DecimalField(max_digits=15, decimal_places=2)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    numero_ot = models.CharField(max_length=50, blank=True)
    obra = models.ForeignKey(
        'obras.Obra',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movimientos_bodega',
    )
    cliente = models.ForeignKey(
        'finanzas.Cliente',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movimientos_bodega',
    )
    solicitud_material = models.ForeignKey(
        'obras.SolicitudMaterial',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movimientos_salida',
    )
    repuesto = models.ForeignKey(Repuesto, on_delete=models.PROTECT)
    costo_total_fifo = models.DecimalField(max_digits=25, decimal_places=2, null=True, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    receptor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movimientos_recibidos',
    )
    receptor_nombre = models.CharField(max_length=150, blank=True, default='')
    observaciones = models.TextField(max_length=1500, blank=True, default='')
    solicitud_salida = models.UUIDField(null=True, blank=True, unique=True)


class RecepcionIngreso(models.Model):
    solicitud_id = models.UUIDField(primary_key=True)
    factura = models.ForeignKey('finanzas.FacturaCompra', on_delete=models.PROTECT)
    movimiento = models.OneToOneField(MovimientoBodega, on_delete=models.PROTECT)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    unidad_medida = models.CharField(max_length=20)
    precio_unitario_neto = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal_neto = models.DecimalField(max_digits=25, decimal_places=2)
    cantidad_disponible = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = "recepciones_ingreso"
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad_disponible__gte=0), name='fyag_lote_saldo_no_negativo'),
        ]


class DetalleConsumoFIFO(models.Model):
    salida = models.ForeignKey(MovimientoBodega, on_delete=models.PROTECT, related_name='detalles_fifo')
    lote = models.ForeignKey(RecepcionIngreso, on_delete=models.PROTECT, related_name='consumos_fifo')
    orden = models.PositiveIntegerField()
    cantidad = models.DecimalField(max_digits=15, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    costo_asignado = models.DecimalField(max_digits=25, decimal_places=2)

    class Meta:
        ordering = ['orden']
        constraints = [
            models.UniqueConstraint(fields=['salida', 'lote'], name='fyag_consumo_salida_lote_unico'),
            models.UniqueConstraint(fields=['salida', 'orden'], name='fyag_consumo_salida_orden_unico'),
            models.CheckConstraint(condition=models.Q(orden__gt=0), name='fyag_consumo_orden_positivo'),
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name='fyag_consumo_cantidad_positiva'),
            models.CheckConstraint(condition=models.Q(precio_unitario__gte=0), name='fyag_consumo_precio_no_negativo'),
            models.CheckConstraint(condition=models.Q(costo_asignado__gte=0), name='fyag_consumo_costo_no_negativo'),
        ]


class DevolucionFIFO(models.Model):
    solicitud_id = models.UUIDField(primary_key=True)
    consumo = models.ForeignKey(DetalleConsumoFIFO, on_delete=models.PROTECT, related_name='devoluciones')
    movimiento = models.OneToOneField(MovimientoBodega, on_delete=models.PROTECT, related_name='devolucion_fifo')
    cantidad = models.DecimalField(max_digits=15, decimal_places=2)
    costo_reintegrado = models.DecimalField(max_digits=25, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name='fyag_devolucion_cantidad_positiva'),
            models.CheckConstraint(condition=models.Q(costo_reintegrado__gte=0), name='fyag_devolucion_costo_no_negativo'),
        ]


class OperacionInventario(models.Model):
    TIPOS = [
        ('MERMA_BODEGA', 'Merma en Bodega'), ('MERMA_OBRA', 'Merma en Obra'),
        ('DEV_BODEGA', 'Devolución a Bodega'), ('DEV_PROVEEDOR', 'Devolución a proveedor'),
        ('USO_INTERNO', 'Uso interno'), ('CAMBIO', 'Cambio de artículo'),
        ('ANULAR', 'Anulación compensatoria'),
    ]
    solicitud_id = models.UUIDField(primary_key=True)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    articulo = models.ForeignKey(Repuesto, on_delete=models.PROTECT, related_name='+')
    articulo_nuevo = models.ForeignKey(Repuesto, on_delete=models.PROTECT,null=True, blank=True, related_name='+')
    origen = models.ForeignKey(MovimientoBodega, on_delete=models.PROTECT, null=True, blank=True, related_name='operaciones_referidas')
    lote = models.ForeignKey(RecepcionIngreso, on_delete=models.PROTECT,null=True, blank=True, related_name='operaciones_referidas')
    obra = models.ForeignKey('obras.Obra', on_delete=models.PROTECT, null=True, blank=True)
    cantidad = models.DecimalField(max_digits=15, decimal_places=2)
    cantidad_nueva = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    motivo = models.CharField(max_length=1000)
    destino = models.CharField(max_length=150, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    datos_solicitud = models.JSONField(default=dict)
    anula_a = models.OneToOneField('self', on_delete=models.PROTECT,null=True, blank=True, related_name='anulada_por')
    movimiento_anulado = models.OneToOneField(MovimientoBodega, on_delete=models.PROTECT,null=True, blank=True, related_name='anulacion_inventario')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name='fyag_op_cantidad_positiva'),
            models.CheckConstraint(condition=( models.Q(cantidad_nueva__isnull=True) | models.Q(cantidad_nueva__gt=0)), name='fyag_op_nueva_positiva'),
        ]


class MovimientoOperacion(models.Model):
    operacion = models.ForeignKey(OperacionInventario, on_delete=models.PROTECT, related_name='movimientos')
    movimiento = models.OneToOneField(MovimientoBodega, on_delete=models.PROTECT, related_name='detalle_operacion')
    funcion = models.CharField(max_length=25)


class MermaConsumoObra(models.Model):
    operacion = models.ForeignKey(OperacionInventario, on_delete=models.PROTECT, related_name='mermas')
    consumo = models.ForeignKey(DetalleConsumoFIFO, on_delete=models.PROTECT, related_name='mermas_operacion')
    cantidad = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['operacion', 'consumo'], name='fyag_op_merma_consumo_unico'),
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name='fyag_op_merma_positiva'),
        ]
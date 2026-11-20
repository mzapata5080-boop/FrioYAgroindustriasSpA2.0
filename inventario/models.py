from django.db import models
from django.conf import settings

class CategoriaRepuesto(models.Model):
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True, verbose_name='Activo')
    def __str__(self): return self.nombre

class Repuesto(models.Model):
    codigo_parte = models.CharField(max_length=50, unique=True, verbose_name='Código interno')
    descripcion = models.CharField(max_length=200, verbose_name='Nombre')
    ubicacion_bodega = models.CharField(max_length=50, verbose_name='Ubicación')
    unidad_medida = models.CharField(max_length=20, choices=[('unidad','Unidades'),('m','Metros'),('kg','Kilogramos'),('l','Litros')], verbose_name='Unidad')
    stock_actual = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Stock actual')
    stock_minimo = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Stock mínimo')
    categoria = models.ForeignKey(CategoriaRepuesto, on_delete=models.PROTECT, verbose_name='Categoría')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    def __str__(self): return f'{self.codigo_parte} — {self.descripcion}'

class MovimientoBodega(models.Model):
    tipo = models.CharField(max_length=10)
    cantidad = models.DecimalField(max_digits=15, decimal_places=2)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    numero_ot = models.CharField(max_length=50, blank=True)
    repuesto = models.ForeignKey(Repuesto, on_delete=models.PROTECT)
    costo_total_fifo = models.DecimalField(max_digits=25, decimal_places=2, null=True, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    # Identificador del envío: reintentar una salida no debe consumir dos veces.
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

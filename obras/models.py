from decimal import Decimal
from django.conf import settings
from django.db import models


class Obra(models.Model):
    ESTADOS = [
        ('PLANIFICADA', 'Planificada'),
        ('EN_EJECUCION', 'En ejecución'),
        ('PAUSADA', 'Pausada'),
        ('CERRADA', 'Cerrada'),
    ]
    TIPOS_SERVICIO = [
        ('INSTALACION', 'Instalación'),
        ('MANTENCION', 'Mantención preventiva'),
        ('REPARACION', 'Reparación / Emergencia'),
        ('PROYECTO', 'Proyecto integral'),
    ]

    codigo_ot = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=150)
    cliente = models.ForeignKey(
        'finanzas.Cliente',
        on_delete=models.PROTECT,
        related_name='obras',
    )
    tipo_servicio = models.CharField(max_length=25, choices=TIPOS_SERVICIO, default='INSTALACION')
    presupuesto_estimado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    direccion = models.CharField(max_length=200, blank=True, default='')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PLANIFICADA')
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_termino_estimada = models.DateField(null=True, blank=True)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='obras_supervisadas',
    )
    tecnicos = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='obras_asignadas_tecnico',
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='obras_creadas',
    )
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'obras_obra'
        ordering = ['-creado_el', '-pk']

    def __str__(self):
        return f'{self.codigo_ot} — {self.nombre}'


class Presupuesto(models.Model):
    ESTADOS = [
        ('BORRADOR', 'Borrador'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
    ]
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name='presupuestos')
    version = models.PositiveIntegerField(default=1)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='BORRADOR')
    monto_materiales_estimado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    monto_mano_obra_estimado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    monto_otros_estimado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    observaciones = models.TextField(blank=True, default='')
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='presupuestos_aprobados',
    )
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'obras_presupuesto'
        unique_together = ('obra', 'version')

    @property
    def total_estimado(self):
        return (
            self.monto_materiales_estimado
            + self.monto_mano_obra_estimado
            + self.monto_otros_estimado
        )

    def __str__(self):
        return f'{self.obra.codigo_ot} v{self.version}'


class SolicitudMaterial(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADA', 'Aprobada / Reservada'),
        ('RECHAZADA', 'Rechazada'),
        ('PARCIAL', 'Entrega parcial'),
        ('ENTREGADA', 'Entregada'),
        ('CANCELADA', 'Cancelada'),
    ]

    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name='solicitudes_material')
    articulo = models.ForeignKey('inventario.Repuesto', on_delete=models.PROTECT, related_name='solicitudes_material')
    cantidad_solicitada = models.DecimalField(max_digits=15, decimal_places=2)
    cantidad_reservada = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cantidad_entregada = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    motivo = models.TextField(blank=True, default='')
    motivo_rechazo = models.TextField(blank=True, default='')
    solicitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='solicitudes_material_creadas',
    )
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='solicitudes_material_aprobadas',
    )
    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'obras_solicitud_material'
        ordering = ['-creado_el', '-pk']

    @property
    def cantidad_pendiente(self):
        return self.cantidad_reservada - self.cantidad_entregada

    def __str__(self):
        return f'Sol #{self.pk} — {self.obra.codigo_ot} — {self.articulo.codigo_parte}'
"""Modelos transversales de auditoría y archivos privados para todos los módulos."""
from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    ACCIONES = [
        ('CREAR', 'Crear'),
        ('EDITAR', 'Editar'),
        ('ELIMINAR', 'Eliminar'),
    ]
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='auditorias_realizadas',
    )
    modelo = models.CharField(max_length=100, db_index=True)
    objeto_id = models.CharField(max_length=64, db_index=True)
    accion = models.CharField(max_length=12, choices=ACCIONES)
    cambios_json = models.TextField(default='{}')
    fecha_registro = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'fyag_registro_auditoria'
        ordering = ['-fecha_registro', '-pk']

    def __str__(self):
        return f'{self.accion} {self.modelo}#{self.objeto_id}'


class ArchivoPrivado(models.Model):
    modulo = models.CharField(max_length=50, db_index=True)
    modelo = models.CharField(max_length=100, db_index=True)
    objeto_id = models.CharField(max_length=64, db_index=True)
    nombre_original = models.CharField(max_length=255)
    ruta_privada = models.CharField(max_length=500, unique=True)
    tamano_bytes = models.PositiveBigIntegerField(default=0)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fyag_archivo_privado'
        ordering = ['-creado_el', '-pk']

    def __str__(self):
        return f'{self.modulo}: {self.nombre_original}'
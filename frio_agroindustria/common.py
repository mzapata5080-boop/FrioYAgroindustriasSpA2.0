"""Funciones comunes transversales: almacenamiento privado de archivos y auditoría de cambios."""
import json
import os
import uuid
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.forms.models import model_to_dict


ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.xlsx', '.xls', '.csv', '.doc', '.docx'}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def private_storage():
    """Almacenamiento privado fuera de STATIC_ROOT y sin URL pública directa."""
    root = getattr(settings, 'PRIVATE_MEDIA_ROOT', Path(settings.BASE_DIR) / 'private_media')
    Path(root).mkdir(parents=True, exist_ok=True)
    return FileSystemStorage(location=str(root), base_url=None)


def validate_private_file(uploaded_file, allowed_exts=ALLOWED_EXTENSIONS, max_bytes=MAX_UPLOAD_BYTES):
    """Valida extensión y tamaño antes de escribir en disco."""
    if uploaded_file is None:
        raise ValidationError('No se recibió ningún archivo.')
    name = getattr(uploaded_file, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed_exts:
        raise ValidationError(f'Extensión no permitida ({ext or "sin extensión"}).')
    size = getattr(uploaded_file, 'size', None)
    if size is not None and size > max_bytes:
        raise ValidationError(f'El archivo excede el máximo permitido ({max_bytes // (1024 * 1024)} MB).')
    return ext


def save_private_file(uploaded_file, module_name, allowed_exts=ALLOWED_EXTENSIONS, max_bytes=MAX_UPLOAD_BYTES):
    """Guarda un archivo en ruta privada por módulo con nombre UUID seguro y devuelve metadata."""
    ext = validate_private_file(uploaded_file, allowed_exts=allowed_exts, max_bytes=max_bytes)
    safe_module = ''.join(c for c in module_name.lower() if c.isalnum() or c in ('_', '-')) or 'general'
    storage = private_storage()
    rel_path = f'{safe_module}/{uuid.uuid4().hex}{ext}'
    saved_path = storage.save(rel_path, uploaded_file)
    return {
        'ruta_privada': saved_path,
        'nombre_original': os.path.basename(getattr(uploaded_file, 'name', saved_path)),
        'tamano_bytes': getattr(uploaded_file, 'size', 0),
    }


def open_private_file(rel_path):
    """Abre un archivo privado validando que no escape de PRIVATE_MEDIA_ROOT."""
    storage = private_storage()
    root = Path(storage.location).resolve()
    target = (root / rel_path).resolve()
    if root not in target.parents or not storage.exists(rel_path):
        raise FileNotFoundError('Archivo privado no encontrado.')
    return storage.open(rel_path, 'rb')


def _json_safe(value):
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, models.Model):
        return value.pk
    return value


def snapshot_instance(instance, exclude=('password',)):
    """Captura estado serializable de un modelo para comparar antes/después."""
    if instance is None or instance.pk is None:
        return {}
    raw = model_to_dict(instance)
    return {k: _json_safe(v) for k, v in raw.items() if k not in exclude}


def diff_snapshots(before, after):
    """Calcula solo los campos que cambiaron entre dos instantáneas."""
    keys = set(before.keys()) | set(after.keys())
    changes = {}
    for k in sorted(keys):
        old_val = before.get(k)
        new_val = after.get(k)
        if old_val != new_val:
            changes[k] = {'antes': old_val, 'despues': new_val}
    return changes


class AuditMixin(models.Model):
    """Campos opcionales/aditivos de auditoría reutilizables en modelos nuevos o actualizados."""
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='%(class)s_creados',
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='%(class)s_actualizados',
    )
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def registrar_cambio(usuario, accion, instancia, antes=None, despues=None):
    """Registra quién creó, editó o eliminó un registro en cualquier módulo."""
    from frio_agroindustria.models import RegistroAuditoria
    antes = antes or {}
    despues = snapshot_instance(instancia) if despues is None and accion != 'ELIMINAR' else (despues or {})
    cambios = diff_snapshots(antes, despues) if accion == 'EDITAR' else (
        {k: {'antes': None, 'despues': v} for k, v in despues.items()} if accion == 'CREAR' else
        {k: {'antes': v, 'despues': None} for k, v in antes.items()}
    )
    if accion == 'EDITAR' and not cambios:
        return None
    return RegistroAuditoria.objects.create(
        usuario=usuario if getattr(usuario, 'is_authenticated', False) else None,
        modelo=f'{instancia._meta.app_label}.{instancia._meta.model_name}',
        objeto_id=str(instancia.pk),
        accion=accion,
        cambios_json=json.dumps(cambios, ensure_ascii=False),
    )
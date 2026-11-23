from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from inventario.models import OperacionInventario, Repuesto, MovimientoBodega, RecepcionIngreso
from obras.models import Obra

CAMPOS_POR_TIPO = {
    'MERMA_BODEGA': ['articulo', 'obra', 'cantidad'],
    'MERMA_OBRA': ['origen', 'cantidad'],
    'DEV_BODEGA': ['origen', 'cantidad'],
    'DEV_PROVEEDOR': ['lote', 'cantidad'],
    'USO_INTERNO': ['articulo', 'cantidad', 'destino'],
    'CAMBIO': ['origen', 'cantidad', 'articulo_nuevo', 'cantidad_nueva'],
    'ANULAR': ['anula_a', 'movimiento_anulado'],
}
OPCIONALES = {'obra', 'anula_a', 'movimiento_anulado'}


class OperacionForm(forms.Form):
    solicitud_id = forms.UUIDField(widget=forms.HiddenInput)
    tipo = forms.ChoiceField(choices=OperacionInventario.TIPOS, widget=forms.HiddenInput)
    articulo = forms.ModelChoiceField(Repuesto.objects.all(), required=False, label='Artículo en Bodega')
    articulo_nuevo = forms.ModelChoiceField(Repuesto.objects.all(), required=False, label='Artículo de reemplazo')
    origen = forms.ModelChoiceField(MovimientoBodega.objects.all(), required=False, label='Salida original')
    lote = forms.ModelChoiceField(RecepcionIngreso.objects.all(), required=False, label='Ingreso que se devuelve al proveedor')
    obra = forms.ModelChoiceField(Obra.objects.all(), required=False, label='Obra asociada (opcional)')
    cantidad = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('.01'),required=False, label='Cantidad del artículo original')
    cantidad_nueva = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('.01'),required=False, label='Cantidad del artículo de reemplazo')
    motivo = forms.CharField(min_length=4, max_length=1000, widget=forms.Textarea, label='Motivo obligatorio')
    destino = forms.CharField(max_length=150, required=False, label='Destino y solicitante del uso interno')
    anula_a = forms.ModelChoiceField(OperacionInventario.objects.all(), required=False, label='Operación que se anula')
    movimiento_anulado = forms.ModelChoiceField(MovimientoBodega.objects.all(), required=False,label='O salida original de BC2 que se anula')

    def clean(self):
        datos = super().clean()
        campos = CAMPOS_POR_TIPO.get(datos.get('tipo'))
        if campos is None:
            return datos
        for nombre in campos:
            if nombre not in OPCIONALES and not datos.get(nombre):
                self.add_error(nombre, 'Este campo es obligatorio.')
        permitidos = set(campos) | {'tipo', 'solicitud_id', 'motivo'}
        for nombre in set(self.fields) - permitidos:
            if datos.get(nombre) not in (None, ''):
                self.add_error(nombre, 'Este campo no corresponde a la operación.')
        if datos.get('tipo') == 'ANULAR' and bool(datos.get('anula_a')) == bool(datos.get('movimiento_anulado')):
            raise ValidationError('Selecciona una operación O una salida original para anular.')
        return datos

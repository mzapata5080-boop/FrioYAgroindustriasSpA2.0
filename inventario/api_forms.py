"""Validaciones del catálogo y de la recepción de materiales."""
from decimal import Decimal
from django import forms
from inventario.models import CategoriaRepuesto, Repuesto
from finanzas.models import FacturaCompra

class CategoriaForm(forms.ModelForm):
    class Meta:
        model=CategoriaRepuesto
        fields=['nombre']
class ArticuloForm(forms.ModelForm):
    class Meta:
        model=Repuesto
        fields=['codigo_parte','descripcion','ubicacion_bodega','unidad_medida','categoria','stock_minimo']
    def clean_unidad_medida(self):
        unit = self.cleaned_data['unidad_medida']
        if self.instance.pk:
            original = Repuesto.objects.get(pk=self.instance.pk)
            if original.unidad_medida != unit and (
                original.stock_actual != 0 or original.movimientobodega_set.exists()
            ):
                raise forms.ValidationError(
                    'No puedes cambiar la unidad de un artículo con stock o movimientos. Crea otro artículo.'
                )
        return unit

    def clean_stock_minimo(self):
        n=self.cleaned_data['stock_minimo']
        if n < 0: raise forms.ValidationError('El stock mínimo no puede ser negativo.')
        return n
class IngresoForm(forms.Form):
    solicitud_id=forms.UUIDField(widget=forms.HiddenInput)
    factura=forms.ModelChoiceField(queryset=FacturaCompra.objects.all())
    articulo=forms.ModelChoiceField(queryset=Repuesto.objects.all())
    cantidad=forms.DecimalField(max_digits=15,decimal_places=2,min_value=Decimal('0.01'))
    precio=forms.DecimalField(max_digits=12,decimal_places=2,min_value=0)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['factura'].queryset = FacturaCompra.objects.select_related('proveedor').order_by('-fecha', '-pk')
        self.fields['factura'].label_from_instance = lambda invoice: (
            f'{invoice.numero_documento} — {invoice.proveedor.razon_social} — {invoice.fecha:%d/%m/%Y}'
        )

    def clean(self):
        d=super().clean()
        a=d.get('articulo'); n=d.get('cantidad')
        if a and n and a.unidad_medida=='unidad' and n != n.to_integral_value():
            self.add_error('cantidad','Debe ser una cantidad entera para artículos por unidad.')
        return d


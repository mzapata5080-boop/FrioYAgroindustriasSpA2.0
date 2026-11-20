"""Validaciones del catálogo y de la recepción de materiales."""
from decimal import Decimal
from django import forms
from django.db import models
from inventario.models import CategoriaRepuesto, Repuesto
from finanzas.models import FacturaCompra

class CategoriaForm(forms.ModelForm):
    activo = forms.BooleanField(required=False, initial=True, label='Activo')

    class Meta:
        model = CategoriaRepuesto
        fields = ['nombre', 'activo']
        labels = {
            'nombre': 'Nombre de la categoría',
            'activo': 'Activo',
        }

    def clean_activo(self):
        if 'activo' not in self.data:
            return self.instance.activo if self.instance.pk else True
        return bool(self.cleaned_data.get('activo'))


class ArticuloForm(forms.ModelForm):
    categoria = forms.ModelChoiceField(
        queryset=CategoriaRepuesto.objects.filter(activo=True),
        label='Categoría'
    )
    activo = forms.BooleanField(required=False, initial=True, label='Activo')

    class Meta:
        model = Repuesto
        fields = ['codigo_parte', 'descripcion', 'categoria', 'ubicacion_bodega', 'unidad_medida', 'stock_minimo', 'activo']
        labels = {
            'codigo_parte': 'Código interno',
            'descripcion': 'Nombre o descripción',
            'categoria': 'Categoría',
            'ubicacion_bodega': 'Ubicación en bodega',
            'unidad_medida': 'Unidad de medida',
            'stock_minimo': 'Stock mínimo',
            'activo': 'Activo',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and getattr(self.instance, 'categoria_id', None):
            self.fields['categoria'].queryset = CategoriaRepuesto.objects.filter(
                models.Q(activo=True) | models.Q(pk=self.instance.categoria_id)
            )
        else:
            self.fields['categoria'].queryset = CategoriaRepuesto.objects.filter(activo=True)

    def clean_activo(self):
        if 'activo' not in self.data:
            return self.instance.activo if self.instance.pk else True
        return bool(self.cleaned_data.get('activo'))

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
        n = self.cleaned_data.get('stock_minimo')
        if n is not None and n < 0:
            raise forms.ValidationError('El stock mínimo no puede ser negativo.')
        return n


class IngresoForm(forms.Form):
    solicitud_id = forms.UUIDField(widget=forms.HiddenInput)
    factura = forms.ModelChoiceField(queryset=FacturaCompra.objects.all(), label='Factura')
    articulo = forms.ModelChoiceField(queryset=Repuesto.objects.filter(activo=True), label='Artículo')
    cantidad = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'), label='Cantidad')
    precio = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label='Precio')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['factura'].queryset = FacturaCompra.objects.select_related('proveedor').order_by('-fecha', '-pk')
        self.fields['factura'].label_from_instance = lambda invoice: (
            f'{invoice.numero_documento} — {invoice.proveedor.razon_social} — {invoice.fecha:%d/%m/%Y}'
        )

    def clean(self):
        d = super().clean()
        a = d.get('articulo')
        n = d.get('cantidad')
        if a and n and a.unidad_medida == 'unidad' and n != n.to_integral_value():
            self.add_error('cantidad', 'Debe ser una cantidad entera para artículos por unidad.')
        return d


class SalidaForm(forms.Form):
    solicitud_id = forms.UUIDField(widget=forms.HiddenInput)
    articulo = forms.ModelChoiceField(queryset=Repuesto.objects.filter(activo=True), label='Artículo')
    cantidad = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'), label='Cantidad a retirar')
    numero_ot = forms.CharField(label='Orden de trabajo / obra (OT)', max_length=50)

    def clean(self):
        values = super().clean()
        article, quantity = values.get('articulo'), values.get('cantidad')
        if article and quantity and article.unidad_medida == 'unidad' and quantity != quantity.to_integral_value():
            self.add_error('cantidad', 'Debe ser una cantidad entera para artículos por unidad.')
        return values


class SolicitudMaterialForm(forms.Form):
    solicitud_id = forms.UUIDField(widget=forms.HiddenInput)
    numero_ot = forms.CharField(label='Orden de trabajo / Obra (OT)', max_length=50)
    articulo = forms.ModelChoiceField(queryset=Repuesto.objects.filter(activo=True), label='Artículo solicitado')
    cantidad = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'), label='Cantidad solicitada')
    fecha_requerida = forms.DateField(label='Fecha requerida en obra')
    observaciones = forms.CharField(label='Observaciones / Destino', required=False, max_length=200)

    def clean(self):
        values = super().clean()
        article, quantity = values.get('articulo'), values.get('cantidad')
        if article and quantity and article.unidad_medida == 'unidad' and quantity != quantity.to_integral_value():
            self.add_error('cantidad', 'Debe ser una cantidad entera para artículos por unidad.')
        return values

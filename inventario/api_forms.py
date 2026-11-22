"""Validaciones del catálogo y de la recepción/salida de materiales."""
from decimal import Decimal
from django import forms
from django.db import models
from inventario.models import CategoriaRepuesto, Repuesto
from finanzas.models import Cliente, FacturaCompra
from obras.models import Obra, SolicitudMaterial
from usuarios.models import Trabajador


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
        label='Categoría',
    )
    activo = forms.BooleanField(required=False, initial=True, label='Activo')

    class Meta:
        model = Repuesto
        fields = [
            'codigo_parte',
            'descripcion',
            'categoria',
            'ubicacion_bodega',
            'unidad_medida',
            'stock_minimo',
            'activo',
        ]
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['factura'].queryset = FacturaCompra.objects.select_related('proveedor').order_by('-fecha', '-pk')
        self.fields['factura'].label_from_instance = lambda invoice: (
            f'{invoice.numero_documento} — {invoice.proveedor.razon_social} — {invoice.fecha:%d/%m/%Y}'
        )


class SalidaForm(forms.Form):
    solicitud_id = forms.UUIDField(widget=forms.HiddenInput)
    solicitud_material = forms.ModelChoiceField(
        queryset=SolicitudMaterial.objects.select_related('obra__cliente', 'articulo').filter(
            estado__in=('APROBADA', 'PARCIAL')
        ),
        required=False,
        label='Solicitud aprobada (opcional)',
    )
    obra = forms.ModelChoiceField(
        queryset=Obra.objects.exclude(estado='CERRADA'),
        required=False,
        label='Obra / Proyecto',
    )
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all(),
        required=False,
        label='Cliente',
    )
    articulo = forms.ModelChoiceField(queryset=Repuesto.objects.filter(activo=True), label='Artículo')
    cantidad = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'), label='Cantidad a retirar')
    numero_ot = forms.CharField(label='Orden de trabajo / obra (OT)', max_length=50, required=False)
    receptor = forms.ModelChoiceField(
        queryset=Trabajador.objects.filter(is_active=True).order_by('first_name', 'username'),
        required=False,
        label='Trabajador receptor',
    )
    receptor_nombre = forms.CharField(label='Receptor externo (si no es trabajador)', max_length=150, required=False)
    observaciones = forms.CharField(label='Observaciones de entrega', max_length=1500, required=False)

    def clean(self):
        values = super().clean()
        article, quantity = values.get('articulo'), values.get('cantidad')
        sol = values.get('solicitud_material')
        obra = values.get('obra')

        if sol:
            if obra and obra.pk != sol.obra_id:
                self.add_error('obra', 'La obra no coincide con la solicitud seleccionada.')
            values['obra'] = sol.obra
            values['cliente'] = sol.obra.cliente
            if article and article.pk != sol.articulo_id:
                self.add_error('articulo', 'El artículo no coincide con la solicitud seleccionada.')
            if quantity and quantity > sol.cantidad_pendiente:
                self.add_error('cantidad', f'La cantidad excede lo pendiente ({sol.cantidad_pendiente}).')

        if values.get('obra'):
            if not (values.get('numero_ot') or '').strip():
                values['numero_ot'] = values['obra'].codigo_ot
            if not values.get('cliente'):
                values['cliente'] = values['obra'].cliente

        if not (values.get('numero_ot') or '').strip():
            self.add_error('numero_ot', 'Indica una Orden de Trabajo o selecciona una Obra.')

        if not values.get('receptor') and not (values.get('receptor_nombre') or '').strip():
            self.add_error('receptor', 'Indica el trabajador o nombre de quien recibe el material.')

        if article and quantity and article.unidad_medida == 'unidad' and quantity != quantity.to_integral_value():
            self.add_error('cantidad', 'Debe ser una cantidad entera para artículos por unidad.')
        return values
"""Formularios y validaciones de Obras, Presupuestos y Solicitudes de Material."""
from decimal import Decimal
from django import forms
from obras.models import Obra, Presupuesto, SolicitudMaterial
from usuarios.models import Trabajador


class ObraForm(forms.ModelForm):
    tecnicos = forms.ModelMultipleChoiceField(
        queryset=Trabajador.objects.filter(is_active=True).order_by('first_name', 'username'),
        required=False,
        label='Técnicos asignados',
    )

    class Meta:
        model = Obra
        fields = [
            'codigo_ot',
            'nombre',
            'cliente',
            'tipo_servicio',
            'presupuesto_estimado',
            'direccion',
            'estado',
            'fecha_inicio',
            'fecha_termino_estimada',
            'supervisor',
            'tecnicos',
        ]
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}),
            'fecha_termino_estimada': forms.DateInput(attrs={'type': 'date'}),
            'presupuesto_estimado': forms.NumberInput(attrs={'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            amount = Decimal(str(self.instance.presupuesto_estimado))
            if amount != amount.to_integral_value():
                self.fields['presupuesto_estimado'].widget.attrs['step'] = '0.01'

    def clean_presupuesto_estimado(self):
        monto = self.cleaned_data['presupuesto_estimado']
        if monto < 0:
            raise forms.ValidationError('El presupuesto estimado no puede ser negativo.')
        if (
            monto != monto.to_integral_value()
            and (
                not self.instance.pk
                or monto != Decimal(str(self.instance.presupuesto_estimado))
            )
        ):
            raise forms.ValidationError('El presupuesto debe ingresarse en pesos enteros, sin decimales.')
        return monto

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get('fecha_inicio')
        termino = cleaned.get('fecha_termino_estimada')
        if inicio and termino and termino < inicio:
            self.add_error('fecha_termino_estimada', 'La fecha de término no puede ser anterior al inicio.')
        return cleaned


class PresupuestoForm(forms.ModelForm):
    class Meta:
        model = Presupuesto
        fields = [
            'obra',
            'version',
            'estado',
            'monto_materiales_estimado',
            'monto_mano_obra_estimado',
            'monto_otros_estimado',
            'observaciones',
        ]
        widgets = {
            'monto_materiales_estimado': forms.NumberInput(attrs={'step': '1'}),
            'monto_mano_obra_estimado': forms.NumberInput(attrs={'step': '1'}),
            'monto_otros_estimado': forms.NumberInput(attrs={'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for name in (
                'monto_materiales_estimado',
                'monto_mano_obra_estimado',
                'monto_otros_estimado',
            ):
                amount = getattr(self.instance, name)
                amount = Decimal(str(amount))
                if amount != amount.to_integral_value():
                    self.fields[name].widget.attrs['step'] = '0.01'

    def clean_monto_materiales_estimado(self):
        return self._clean_whole_amount('monto_materiales_estimado')

    def clean_monto_mano_obra_estimado(self):
        return self._clean_whole_amount('monto_mano_obra_estimado')

    def clean_monto_otros_estimado(self):
        return self._clean_whole_amount('monto_otros_estimado')

    def _clean_whole_amount(self, field_name):
        amount = self.cleaned_data[field_name]
        if (
            amount != amount.to_integral_value()
            and (
                not self.instance.pk
                or amount != Decimal(str(getattr(self.instance, field_name)))
            )
        ):
            raise forms.ValidationError('El monto debe ingresarse en pesos enteros, sin decimales.')
        return amount


class SolicitudMaterialForm(forms.ModelForm):
    class Meta:
        model = SolicitudMaterial
        fields = ['obra', 'articulo', 'cantidad_solicitada', 'motivo']

    def clean_cantidad_solicitada(self):
        qty = self.cleaned_data['cantidad_solicitada']
        if qty <= Decimal('0.00'):
            raise forms.ValidationError('La cantidad solicitada debe ser mayor que cero.')
        return qty

    def clean(self):
        cleaned = super().clean()
        art = cleaned.get('articulo')
        qty = cleaned.get('cantidad_solicitada')
        obra = cleaned.get('obra')
        if obra and obra.estado == 'CERRADA':
            self.add_error('obra', 'No se pueden solicitar materiales para una obra cerrada.')
        if art and qty and art.unidad_medida == 'unidad' and qty != qty.to_integral_value():
            self.add_error('cantidad_solicitada', 'Debe ser una cantidad entera para artículos por unidad.')
        return cleaned
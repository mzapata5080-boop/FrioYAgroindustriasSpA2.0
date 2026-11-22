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
        }

    def clean_presupuesto_estimado(self):
        monto = self.cleaned_data['presupuesto_estimado']
        if monto < 0:
            raise forms.ValidationError('El presupuesto estimado no puede ser negativo.')
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
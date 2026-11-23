from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from .models import (
    Cliente,
    Proveedor,
    FacturaCompra,
    FacturaCompraDetalle,
    Presupuesto,
    PresupuestoDetalle,
    DocumentoVenta,
    PagoDocumento,
    NotaCredito,
)

class ClienteForm(forms.ModelForm):

    class Meta:
        model = Cliente

        fields = [
            'rut',
            'razon_social',
            'telefono',
            'correo',
            'direccion',
            'representante',
            'cargo_contacto'
        ]

        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'representante': forms.TextInput(attrs={'class': 'form-control'}),
            'cargo_contacto': forms.TextInput(attrs={'class': 'form-control'})
        }

    def clean_rut(self):
        rut = ProveedorForm().formatear_rut(self.cleaned_data.get('rut', ''))

        if Cliente.objects.filter(rut=rut)\
                .exclude(pk=self.instance.pk)\
                .exists():

            raise forms.ValidationError(
                "Ya existe un cliente con este RUT."
            )

        return rut


class ProveedorForm(forms.ModelForm):

    class Meta:
        model = Proveedor

        fields = [
            'rut',
            'razon_social',
            'giro',
            'telefono',
            'email',
            'direccion',
            'encargado_pagos',
            'correo_pagos',
            'banco',
            'tipo_cuenta',
            'numero_cuenta'
        ]

        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'giro': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'encargado_pagos': forms.TextInput(attrs={'class': 'form-control'}),
            'correo_pagos': forms.EmailInput(attrs={'class': 'form-control'}),
            'banco': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_cuenta': forms.Select(attrs={'class': 'form-control'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_rut(self):

        rut = self.cleaned_data.get(
            'rut',
            ''
        )

        rut_formateado = (
            self.formatear_rut(rut)
        )

        qs = (
            Proveedor.objects
            .filter(rut=rut_formateado)
        )

        if self.instance.pk:

            qs = qs.exclude(
                pk=self.instance.pk
            )

        if qs.exists():

            raise forms.ValidationError(
                'Ya existe un proveedor con este RUT.'
            )

        return rut_formateado

    def formatear_rut(self, rut):

        rut = (
            str(rut)
            .replace(".", "")
            .replace("-", "")
            .upper()
            .strip()
        )

        cuerpo = rut[:-1]
        dv = rut[-1]
        partes = []
        while cuerpo:
            partes.insert(0, cuerpo[-3:])
            cuerpo = cuerpo[:-3]
        return ".".join(partes) + "-" + dv

    def clean(self):

        cleaned = super().clean()

        if not cleaned.get("banco"):
            self.add_error(
                "banco",
                "Debe ingresar banco."
            )

        if not cleaned.get("numero_cuenta"):
            self.add_error(
                "numero_cuenta",
                "Debe ingresar cuenta."
            )

        return cleaned


class FacturaCompraForm(forms.ModelForm):
    class Meta:
        model = FacturaCompra
        fields = [
            'proveedor',
            'fecha',
            'numero_documento',
            'tipo_documento',
            'monto',
            'observaciones'
        ]

        widgets = {
            'fecha': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control'
                }
            ),

            'proveedor': forms.Select(
                attrs={
                    'class': 'form-control'
                }
            ),

            'numero_documento': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),

            'tipo_documento': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),

            'monto': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '1'
                }
            ),

            'observaciones': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            amount = Decimal(str(self.instance.monto))
            if amount != amount.to_integral_value():
                self.fields['monto'].widget.attrs['step'] = '0.01'

    def clean_monto(self):
        monto = self.cleaned_data['monto']
        if monto <= 0:
            raise forms.ValidationError(
                "El monto de la factura debe ser mayor que cero."
            )
        if (
            monto != monto.to_integral_value()
            and (not self.instance.pk or monto != Decimal(str(self.instance.monto)))
        ):
            raise forms.ValidationError(
                "El monto debe ingresarse en pesos enteros, sin decimales."
            )
        return monto


class FacturaCompraDetalleForm(forms.ModelForm):
    class Meta:
        model = FacturaCompraDetalle
        fields = ['articulo', 'cantidad', 'precio_unitario']

        widgets = {
            'articulo': forms.Select(attrs={'class': 'form-control'}),
            'cantidad': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}
            ),
            'precio_unitario': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '0', 'step': '1'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            price = Decimal(str(self.instance.precio_unitario))
            if price != price.to_integral_value():
                self.fields['precio_unitario'].widget.attrs['step'] = '0.01'

    def clean_cantidad(self):
        cantidad = self.cleaned_data['cantidad']
        if cantidad <= 0:
            raise forms.ValidationError(
                "La cantidad debe ser mayor que cero."
            )

        articulo = self.cleaned_data.get('articulo')
        if (
            articulo
            and articulo.unidad_medida == 'unidad'
            and cantidad != cantidad.to_integral_value()
        ):
            raise forms.ValidationError(
                "La cantidad debe ser entera para artículos por unidad."
            )
        return cantidad

    def clean_precio_unitario(self):
        precio = self.cleaned_data['precio_unitario']
        if precio < 0:
            raise forms.ValidationError(
                "El precio unitario no puede ser negativo."
            )
        if (
            precio != precio.to_integral_value()
            and (
                not self.instance.pk
                or precio != Decimal(str(self.instance.precio_unitario))
            )
        ):
            raise forms.ValidationError(
                "El precio unitario debe ingresarse en pesos enteros, sin decimales."
            )
        return precio

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.pk and (
            self.instance.recepciones.exists()
            or self.instance.factura.recepciones_compra.exists()
            or self._has_legacy_receptions()
        ):
            changed = any(
                cleaned_data.get(field) != getattr(self.instance, field)
                for field in ('articulo', 'cantidad', 'precio_unitario')
                if field in cleaned_data
            )
            if changed or cleaned_data.get('DELETE', False):
                raise ValidationError(
                    "No se puede modificar un artículo que ya tiene recepciones."
                )
        return cleaned_data

    def _has_legacy_receptions(self):
        from inventario.models import RecepcionIngreso
        return RecepcionIngreso.objects.filter(
            factura_id=self.instance.factura_id
        ).exists()


class FacturaCompraDetalleInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if self.instance.pk and (
            self.instance.recepciones_compra.exists()
            or self._has_legacy_receptions()
        ):
            if any(
                not form.instance.pk
                and form.cleaned_data
                and not form.cleaned_data.get('DELETE', False)
                for form in self.forms
            ):
                raise ValidationError(
                    "No se pueden agregar artículos después de iniciar la recepción."
                )
        if self.instance._state.adding and not any(
            form.cleaned_data and not form.cleaned_data.get('DELETE', False)
            for form in self.forms
        ):
            raise ValidationError(
                "Agregue al menos un artículo a la factura."
            )

    def _has_legacy_receptions(self):
        from inventario.models import RecepcionIngreso
        return RecepcionIngreso.objects.filter(factura=self.instance).exists()


FacturaCompraDetalleFormSet = inlineformset_factory(
    FacturaCompra,
    FacturaCompraDetalle,
    form=FacturaCompraDetalleForm,
    formset=FacturaCompraDetalleInlineFormSet,
    extra=1,
    can_delete=True
)


class RecepcionDetalleForm(forms.Form):
    detalle_factura = forms.ModelChoiceField(
        queryset=FacturaCompraDetalle.objects.select_related('articulo'),
        label='Artículo de la factura'
    )
    cantidad = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label='Cantidad recibida'
    )

    def clean(self):
        cleaned_data = super().clean()
        detalle = cleaned_data.get('detalle_factura')
        cantidad = cleaned_data.get('cantidad')
        if (
            detalle
            and cantidad
            and detalle.articulo.unidad_medida == 'unidad'
            and cantidad != cantidad.to_integral_value()
        ):
            self.add_error(
                'cantidad',
                "La cantidad debe ser entera para artículos por unidad."
            )
        return cleaned_data


class PresupuestoForm(forms.ModelForm):
    class Meta:
        model = Presupuesto
        fields = [
            "numero", "cliente", "obra", "fecha", "vencimiento", "observaciones"
        ]
        widgets = {
            "numero": forms.TextInput(attrs={"class": "form-control"}),
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "obra": forms.Select(attrs={"class": "form-select"}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "vencimiento": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "observaciones": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.estado != "BORRADOR":
            raise ValidationError("Solo se pueden editar presupuestos en borrador.")
        return cleaned


class PresupuestoDetalleForm(forms.ModelForm):
    class Meta:
        model = PresupuestoDetalle
        fields = ["presupuesto", "articulo", "cantidad", "precio_unitario"]
        widgets = {
            "presupuesto": forms.Select(attrs={"class": "form-select"}),
            "articulo": forms.Select(attrs={"class": "form-select"}),
            "cantidad": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.01", "step": "0.01"}
            ),
            "precio_unitario": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "step": "0.01"}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        presupuesto = cleaned.get("presupuesto")
        if presupuesto and presupuesto.estado != "BORRADOR":
            raise ValidationError(
                "No se puede modificar el detalle de un presupuesto resuelto."
            )
        cantidad = cleaned.get("cantidad")
        articulo = cleaned.get("articulo")
        if (
            cantidad is not None
            and articulo
            and articulo.unidad_medida == "unidad"
            and cantidad != cantidad.to_integral_value()
        ):
            self.add_error(
                "cantidad",
                "La cantidad debe ser entera para artículos por unidad.",
            )
        return cleaned


class DocumentoVentaForm(forms.ModelForm):
    class Meta:
        model = DocumentoVenta
        fields = [
            "numero_documento", "cliente", "obra", "fecha", "vencimiento",
            "total", "observaciones",
        ]
        widgets = {
            "numero_documento": forms.TextInput(attrs={"class": "form-control"}),
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "obra": forms.Select(attrs={"class": "form-select"}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "vencimiento": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "total": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.01", "step": "0.01"}
            ),
            "observaciones": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.anulado:
            raise ValidationError("No se puede editar un documento anulado.")
        total = cleaned.get("total")
        if (
            self.instance.pk
            and total is not None
            and total != self.instance.total
            and (self.instance.pagos.exists() or self.instance.notas_credito.exists())
        ):
            self.add_error(
                "total",
                "No se puede cambiar el total con pagos o notas de crédito registrados.",
            )
        return cleaned


class PagoDocumentoForm(forms.ModelForm):
    class Meta:
        model = PagoDocumento
        fields = [
            "documento", "monto", "fecha_pago", "metodo", "referencia",
            "observaciones",
        ]
        widgets = {
            "documento": forms.Select(attrs={"class": "form-select"}),
            "monto": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.01", "step": "0.01"}
            ),
            "fecha_pago": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "metodo": forms.Select(attrs={"class": "form-select"}),
            "referencia": forms.TextInput(attrs={"class": "form-control"}),
            "observaciones": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}
            ),
        }

    def clean_monto(self):
        monto = self.cleaned_data["monto"]
        documento = self.cleaned_data.get("documento")
        if monto <= 0:
            raise forms.ValidationError("El monto debe ser mayor que cero.")
        if documento and monto > documento.saldo:
            raise forms.ValidationError("El pago supera el saldo pendiente.")
        return monto

    def clean_documento(self):
        documento = self.cleaned_data["documento"]
        if documento.anulado:
            raise forms.ValidationError(
                "No se pueden registrar pagos en un documento anulado."
            )
        return documento


class NotaCreditoForm(forms.ModelForm):
    class Meta:
        model = NotaCredito
        fields = [
            "documento", "numero_documento", "fecha", "motivo", "monto",
            "observaciones",
        ]
        widgets = {
            "documento": forms.Select(attrs={"class": "form-select"}),
            "numero_documento": forms.TextInput(attrs={"class": "form-control"}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "motivo": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "monto": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.01", "step": "0.01"}
            ),
            "observaciones": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        documento = cleaned.get("documento")
        monto = cleaned.get("monto")
        motivo = cleaned.get("motivo")
        if documento and documento.anulado:
            self.add_error("documento", "El documento original está anulado.")
        if documento and monto is not None and monto > documento.saldo:
            self.add_error("monto", "El monto supera el saldo pendiente.")
        if motivo is not None and not motivo.strip():
            self.add_error("motivo", "Indique el motivo de la nota de crédito.")
        return cleaned
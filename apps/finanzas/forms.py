from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from .models import TransaccionDiaria, CategoriaFinanciera, OrdenDePago


class TransaccionDiariaForm(forms.ModelForm):
    monto = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
        error_messages={
            'required': 'El monto de la transacción es obligatorio.',
            'min_value': 'El monto debe ser estrictamente mayor a 0.00.'
        }
    )

    descripcion = forms.CharField(
        max_length=255,
        required=True,
        strip=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        error_messages={'required': 'Debe ingresar una descripción explicativa.'}
    )

    numero_comprobante = forms.CharField(
        max_length=100,
        required=True,
        strip=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        error_messages={'required': 'El número de comprobante o referencia es obligatorio.'}
    )

    comprobante_digital = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'})
    )

    class Meta:
        model = TransaccionDiaria
        fields = [
            'tipo',
            'categoria',
            'monto',
            'numero_comprobante',
            'descripcion',
            'comprobante_digital'
        ]
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        for field_name in ['tipo', 'categoria', 'monto', 'numero_comprobante', 'descripcion']:
            self.fields[field_name].required = True

        self.fields['categoria'].queryset = CategoriaFinanciera.objects.filter(activo=True)

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto is None or monto <= Decimal('0.00'):
            raise ValidationError("El monto no puede ser cero ni negativo.")
        return monto

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        categoria = cleaned_data.get('categoria')
        monto = cleaned_data.get('monto')

        if tipo and categoria and tipo != categoria.naturaleza:
            self.add_error(
                'categoria',
                f"La categoría seleccionada es de tipo {categoria.get_naturaleza_display()}, pero la transacción es {tipo}."
            )

        if tipo == TransaccionDiaria.TipoTransaccion.EGRESO and monto:
            if not self.user or not self.user.sede:
                raise ValidationError("No se puede validar el saldo: el usuario no posee una sede asignada.")
            saldo_disponible = self.user.sede.saldo_actual
            if saldo_disponible < monto:
                self.add_error(
                    'monto',
                    f"Fondos insuficientes en la sede {self.user.sede.nombre}. "
                    f"Saldo disponible: {saldo_disponible} USD, Monto solicitado: {monto} USD."
                )

        return cleaned_data


class SolicitudOrdenPagoForm(forms.ModelForm):
    class Meta:
        model = OrdenDePago
        fields = ['beneficiario', 'concepto', 'monto']
        widgets = {
            'beneficiario': forms.TextInput(attrs={'class': 'form-control'}),
            'concepto': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
        }

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if not monto or monto <= Decimal('0.00'):
            raise ValidationError("El monto de la orden debe ser estrictamente positivo.")
        return monto

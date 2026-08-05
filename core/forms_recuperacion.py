# core/forms_recuperacion.py — recuperación de contraseña por código de mail
from django import forms


class SolicitarRecuperacionForm(forms.Form):
    identificador = forms.CharField(
        label='Usuario o email',
        max_length=254,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'nombre.usuario o tu@email.com',
            'autocomplete': 'username',
            'autofocus': True,
        }),
    )

    def clean_identificador(self):
        return self.cleaned_data['identificador'].strip()


class VerificarCodigoForm(forms.Form):
    codigo = forms.CharField(
        label='Código de verificación',
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control codigo-input',
            'placeholder': '000000',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'autofocus': True,
        }),
    )

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip()
        if not codigo.isdigit():
            raise forms.ValidationError('El código solo tiene números.')
        return codigo


class NuevaPasswordForm(forms.Form):
    password_nueva = forms.CharField(
        label='Contraseña nueva',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mínimo 8 caracteres',
            'autocomplete': 'new-password',
            'autofocus': True,
        }),
    )
    password_confirmar = forms.CharField(
        label='Confirmá la contraseña nueva',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Repetí la contraseña nueva',
            'autocomplete': 'new-password',
        }),
    )

    def clean_password_nueva(self):
        nueva = self.cleaned_data.get('password_nueva', '')
        if len(nueva) < 8:
            raise forms.ValidationError('La contraseña nueva debe tener al menos 8 caracteres.')
        return nueva

    def clean(self):
        cleaned = super().clean()
        nueva = cleaned.get('password_nueva')
        confirmar = cleaned.get('password_confirmar')
        if nueva and confirmar and nueva != confirmar:
            self.add_error('password_confirmar', 'Las contraseñas no coinciden.')
        return cleaned

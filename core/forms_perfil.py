# core/forms_perfil.py
from django import forms
from django.contrib.auth import get_user_model

Usuario = get_user_model()


class CambiarUsernameForm(forms.Form):
    username = forms.CharField(
        label='Nuevo nombre de usuario',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingresá el nuevo usuario',
            'autocomplete': 'username',
        }),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_username(self):
        nuevo = self.cleaned_data['username'].strip()

        if not nuevo:
            raise forms.ValidationError('El nombre de usuario no puede estar vacío.')

        qs = Usuario.objects.filter(username__iexact=nuevo)
        if self.usuario:
            qs = qs.exclude(pk=self.usuario.pk)

        if qs.exists():
            raise forms.ValidationError('Ese nombre de usuario ya está en uso. Elegí otro.')

        return nuevo


class CambiarPasswordForm(forms.Form):
    password_actual = forms.CharField(
        label='Contraseña actual',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingresá tu contraseña actual',
            'autocomplete': 'current-password',
        }),
    )
    password_nueva = forms.CharField(
        label='Contraseña nueva',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mínimo 8 caracteres',
            'autocomplete': 'new-password',
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

    # El request.user se inyecta en la vista antes de llamar is_valid()
    # usando form.usuario = request.user  (ver views_perfil.py)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = None  # se asigna desde la vista

    def clean_password_actual(self):
        ingresada = self.cleaned_data.get('password_actual')
        if self.usuario and not self.usuario.check_password(ingresada):
            raise forms.ValidationError('La contraseña actual es incorrecta.')
        return ingresada

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
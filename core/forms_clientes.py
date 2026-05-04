# core/forms_clientes.py
from django import forms
from .models import Cliente, ClienteImagen, ClienteContactoAdicional, ClienteTelefono, GrupoFamiliar


class FormularioClienteBase(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            # Identidad
            'tipo', 'estado', 'nivel_riesgo',
            # Persona
            'nombre', 'apellido', 'dni', 'cuil', 'fecha_nacimiento', 'genero', 'ocupacion',
            # Empresa
            'razon_social', 'nombre_comercial', 'cuit', 'cond_iva',
            'rubro', 'sitio_web', 'fecha_fundacion',
            # Contacto digital
            'email_principal', 'email_secundario',
            'instagram', 'facebook', 'linkedin', 'canal_preferido',
            # Dirección
            'calle', 'numero', 'piso_depto', 'barrio',
            'localidad', 'partido', 'provincia', 'pais', 'codigo_postal',
            # Grupo familiar
            'grupo_familiar', 'unidad_habitacional',
            # Geo
            'latitud', 'longitud', 'maps_url',
            # CRM
            'notas', 'como_nos_conocio', 'tags', 'referido_por',
            'fecha_desde_cliente', 'fecha_ultimo_contacto', 'fecha_proximo_contacto',
            # Scoring (no se edita manualmente en el form base, pero sí en admin/vista especial)
        ]
        widgets = {
            'tipo':          forms.Select(attrs={'class': 'form-select'}),
            'estado':        forms.Select(attrs={'class': 'form-select'}),
            'nivel_riesgo':  forms.Select(attrs={'class': 'form-select'}),
            'canal_preferido': forms.Select(attrs={'class': 'form-select'}),
            'fecha_nacimiento':     forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fundacion':      forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_desde_cliente':  forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_ultimo_contacto':  forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_proximo_contacto': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notas':          forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'referido_por':   forms.Select(attrs={'class': 'form-select'}),
            'grupo_familiar': forms.Select(attrs={'class': 'form-select'}),
            'latitud':  forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
            'longitud': forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
            'tags':     forms.TextInput(attrs={'class': 'form-control',
                            'placeholder': 'Ej: VIP, moroso, potencial (separados por coma)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        self.fields['tipo'].required = True
        if self.instance and self.instance.pk:
            self.fields['referido_por'].queryset = Cliente.objects.exclude(pk=self.instance.pk)

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo')
        if tipo == 'persona':
            if not cleaned.get('nombre') and not cleaned.get('apellido'):
                self.add_error('nombre', 'Ingresá al menos el nombre o apellido.')
        elif tipo == 'empresa':
            if not cleaned.get('razon_social') and not cleaned.get('nombre_comercial'):
                self.add_error('razon_social', 'Ingresá al menos la razón social o nombre comercial.')
        return cleaned


class FormularioClienteTelefono(forms.ModelForm):
    class Meta:
        model = ClienteTelefono
        fields = ['numero', 'tipo', 'es_titular', 'descripcion', 'tiene_whatsapp']
        widgets = {
            'tipo':        forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'numero':      forms.TextInput(attrs={'class': 'form-control form-control-sm',
                               'placeholder': 'Ej: +54 9 11 1234-5678'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control form-control-sm',
                               'placeholder': 'Ej: trabajo, esposa, emergencia'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descripcion'].required = False
        self.fields['es_titular'].required = False
        self.fields['tiene_whatsapp'].required = False


class FormularioGrupoFamiliar(forms.ModelForm):
    class Meta:
        model = GrupoFamiliar
        fields = ['apellido_referencia', 'direccion_referencia', 'descripcion']
        widgets = {
            'apellido_referencia':  forms.TextInput(attrs={'class': 'form-control',
                                        'placeholder': 'Ej: López, Rodríguez'}),
            'direccion_referencia': forms.TextInput(attrs={'class': 'form-control',
                                        'placeholder': 'Ej: Av. San Martín 450'}),
            'descripcion':          forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['direccion_referencia'].required = False
        self.fields['descripcion'].required = False


class FormularioClienteImagen(forms.ModelForm):
    class Meta:
        model = ClienteImagen
        fields = ['imagen', 'tipo', 'descripcion', 'orden']
        widgets = {
            'tipo':        forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control form-control-sm',
                               'placeholder': 'Descripción opcional'}),
            'orden':       forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descripcion'].required = False
        self.fields['orden'].required = False


class FormularioContactoAdicional(forms.ModelForm):
    class Meta:
        model = ClienteContactoAdicional
        fields = ['nombre', 'apellido', 'rol', 'telefono', 'whatsapp', 'email', 'notas']
        widgets = {
            'rol':   forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'notas': forms.TextInput(attrs={'class': 'form-control form-control-sm',
                         'placeholder': 'Notas opcionales'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        self.fields['nombre'].required = True
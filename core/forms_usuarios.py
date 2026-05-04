# core/forms_usuarios.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario, UsuarioEstudio, UsuarioExperienciaLaboral, UsuarioCapacitacion, UsuarioDocumento

# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

DATE_WIDGET = {'type': 'date', 'class': 'form-control'}

def _base_init(form):
    """Aplica clases Bootstrap a todos los campos del form."""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, (forms.TextInput, forms.EmailInput,
                                forms.NumberInput, forms.URLInput,
                                forms.PasswordInput, forms.Textarea)):
            widget.attrs.setdefault('class', 'form-control')
        elif isinstance(widget, forms.Select):
            widget.attrs.setdefault('class', 'form-select')
        elif isinstance(widget, forms.DateInput):
            widget.attrs.setdefault('class', 'form-control')
            widget.attrs.setdefault('type', 'date')
        elif isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault('class', 'form-check-input')
        elif isinstance(widget, forms.FileInput):
            widget.attrs.setdefault('class', 'form-control')

# ══════════════════════════════════════════════════════════════════
#  FORMULARIO BASE (todos los campos)
# ══════════════════════════════════════════════════════════════════

class FormularioUsuarioBase(forms.ModelForm):
    """Formulario con todos los campos del modelo Usuario."""
    class Meta:
        model = Usuario
        fields = [
            # Credenciales
            'username', 'email',
            # Identidad
            'first_name', 'last_name', 'dni', 'cuil',
            'fecha_nacimiento', 'genero', 'estado_civil',
            'tiene_hijos', 'cantidad_hijos', 'nacionalidad',
            # Foto
            'foto_perfil',
            # Contacto
            'telefono_personal', 'telefono_alternativo', 'email_personal',
            # Dirección
            'calle', 'numero', 'piso_depto', 'barrio',
            'localidad', 'partido', 'provincia', 'pais', 'codigo_postal',
            # Laboral
            'legajo', 'puesto', 'area', 'sucursal',
            'fecha_ingreso', 'fecha_egreso',
            'estado_laboral', 'tipo_contrato', 'modalidad_trabajo',
            'salario_bruto', 'banco', 'cbu', 'alias_cbu',
            # Emergencia
            'emergencia_nombre', 'emergencia_vinculo', 'emergencia_telefono',
            # Salud
            'grupo_sanguineo', 'obra_social', 'nro_afiliado',
            'apto_psicofisico', 'fecha_apto', 'observaciones_salud',
            # Notas
            'notas_internas',
        ]
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs=DATE_WIDGET),
            'fecha_ingreso':    forms.DateInput(attrs=DATE_WIDGET),
            'fecha_egreso':     forms.DateInput(attrs=DATE_WIDGET),
            'fecha_apto':       forms.DateInput(attrs=DATE_WIDGET),
            'observaciones_salud': forms.Textarea(attrs={'rows': 3}),
            'notas_internas':     forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Todos los campos opcionales salvo username
        for field in self.fields.values():
            field.required = False
        self.fields['username'].required = True

        # Etiquetas en español
        labels = {
            'username': 'Usuario (acceso al sistema)',
            'email': 'Email del sistema',
            'first_name': 'Nombre/s',
            'last_name': 'Apellido/s',
            'dni': 'DNI',
            'cuil': 'CUIL',
            'fecha_nacimiento': 'Fecha de nacimiento',
            'genero': 'Género',
            'estado_civil': 'Estado civil',
            'tiene_hijos': '¿Tiene hijos?',
            'cantidad_hijos': 'Cantidad de hijos',
            'nacionalidad': 'Nacionalidad',
            'foto_perfil': 'Foto de perfil',
            'telefono_personal': 'Teléfono personal',
            'telefono_alternativo': 'Teléfono alternativo',
            'email_personal': 'Email personal',
            'calle': 'Calle',
            'numero': 'Número',
            'piso_depto': 'Piso / Depto',
            'barrio': 'Barrio',
            'localidad': 'Localidad',
            'partido': 'Partido / Municipio',
            'provincia': 'Provincia',
            'pais': 'País',
            'codigo_postal': 'Código postal',
            'legajo': 'Nº de legajo',
            'puesto': 'Puesto / Cargo',
            'area': 'Área / Departamento',
            'sucursal': 'Sucursal / Sede',
            'fecha_ingreso': 'Fecha de ingreso',
            'fecha_egreso': 'Fecha de egreso',
            'estado_laboral': 'Estado laboral',
            'tipo_contrato': 'Tipo de contrato',
            'modalidad_trabajo': 'Modalidad de trabajo',
            'salario_bruto': 'Salario bruto',
            'banco': 'Banco',
            'cbu': 'CBU / CVU',
            'alias_cbu': 'Alias CBU',
            'emergencia_nombre': 'Nombre del contacto',
            'emergencia_vinculo': 'Vínculo',
            'emergencia_telefono': 'Teléfono',
            'grupo_sanguineo': 'Grupo sanguíneo',
            'obra_social': 'Obra social / Prepaga',
            'nro_afiliado': 'Nº de afiliado',
            'apto_psicofisico': 'Apto psicofísico',
            'fecha_apto': 'Fecha del apto',
            'observaciones_salud': 'Observaciones de salud',
            'notas_internas': 'Notas internas (RRHH)',
        }
        for campo, etiqueta in labels.items():
            if campo in self.fields:
                self.fields[campo].label = etiqueta

        _base_init(self)


# ══════════════════════════════════════════════════════════════════
#  FORMULARIO DE CREACIÓN (con contraseñas y rol)
# ══════════════════════════════════════════════════════════════════

class FormularioCreacionUsuario(FormularioUsuarioBase, UserCreationForm):
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput, required=True)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput, required=True)
    rol_nombre = forms.CharField(
        label='Rol',
        required=False,
        max_length=50,
        help_text='Escribe el nombre del rol. Si no existe, se creará automáticamente.'
    )

    class Meta(FormularioUsuarioBase.Meta):
        fields = FormularioUsuarioBase.Meta.fields + ['password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['class'] = 'form-control'

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


# ══════════════════════════════════════════════════════════════════
#  FORMULARIO DE EDICIÓN (sin contraseñas)
# ══════════════════════════════════════════════════════════════════

class FormularioEdicionUsuario(FormularioUsuarioBase):
    rol_nombre = forms.CharField(
        label='Rol del sistema',
        required=False,
        max_length=50,
        help_text='Si no existe, se creará automáticamente.'
    )

    class Meta(FormularioUsuarioBase.Meta):
        pass


# ══════════════════════════════════════════════════════════════════
#  SUB‑FORMULARIOS (para el panel de detalle, se mantienen)
# ══════════════════════════════════════════════════════════════════

class FormularioEstudio(forms.ModelForm):
    class Meta:
        model = UsuarioEstudio
        fields = ['nivel', 'titulo', 'institucion', 'estado',
                  'fecha_inicio', 'fecha_fin', 'promedio', 'observaciones']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs=DATE_WIDGET),
            'fecha_fin':    forms.DateInput(attrs=DATE_WIDGET),
            'observaciones': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False
        self.fields['nivel'].required = True
        self.fields['titulo'].required = True
        _base_init(self)


class FormularioExperienciaLaboral(forms.ModelForm):
    class Meta:
        model = UsuarioExperienciaLaboral
        fields = ['empresa', 'puesto', 'area', 'descripcion',
                  'fecha_inicio', 'fecha_fin', 'trabajo_actual',
                  'motivo_egreso', 'referencia_nombre', 'referencia_contacto',
                  'observaciones']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs=DATE_WIDGET),
            'fecha_fin':    forms.DateInput(attrs=DATE_WIDGET),
            'descripcion':  forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'observaciones':forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False
        self.fields['empresa'].required = True
        self.fields['puesto'].required = True
        self.fields['fecha_inicio'].required = True
        _base_init(self)


class FormularioCapacitacion(forms.ModelForm):
    class Meta:
        model = UsuarioCapacitacion
        fields = ['nombre', 'tipo', 'modalidad', 'proveedor',
                  'fecha_inicio', 'fecha_fin', 'duracion_hs',
                  'resultado', 'calificacion', 'nota_maxima',
                  'es_obligatoria', 'certificado_emitido', 'vencimiento_cert',
                  'observaciones']
        widgets = {
            'fecha_inicio':    forms.DateInput(attrs=DATE_WIDGET),
            'fecha_fin':       forms.DateInput(attrs=DATE_WIDGET),
            'vencimiento_cert':forms.DateInput(attrs=DATE_WIDGET),
            'observaciones':   forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False
        self.fields['nombre'].required = True
        self.fields['tipo'].required = True
        _base_init(self)


class FormularioDocumento(forms.ModelForm):
    class Meta:
        model = UsuarioDocumento
        fields = ['tipo', 'nombre', 'archivo', 'fecha_doc', 'vencimiento', 'observaciones']
        widgets = {
            'fecha_doc':    forms.DateInput(attrs=DATE_WIDGET),
            'vencimiento':  forms.DateInput(attrs=DATE_WIDGET),
            'observaciones':forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Notas opcionales'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False
        self.fields['tipo'].required = True
        self.fields['nombre'].required = True
        self.fields['archivo'].required = True
        _base_init(self)
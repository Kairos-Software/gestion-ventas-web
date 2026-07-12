from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.db import transaction


# ══════════════════════════════════════════════════════════════════
#  CATÁLOGO DE PERMISOS DEL SISTEMA
#
#  Para agregar permisos de un nuevo módulo:
#  1. Agregá las tuplas acá abajo en la sección correspondiente
#  2. python manage.py makemigrations && migrate
#  3. Importá chequear_permiso() en el views_nuevo_modulo.py
# ══════════════════════════════════════════════════════════════════
PERMISOS_CHOICES = [
    # ── Módulo: Usuarios ──────────────────────────────────────────
    ('ver_usuarios',       'Ver lista de usuarios'),
    ('crear_usuarios',     'Crear usuarios'),
    ('editar_usuarios',    'Editar usuarios'),
    ('eliminar_usuarios',  'Eliminar usuarios'),
    ('gestionar_permisos', 'Gestionar permisos de otros usuarios'),

    # ── Módulo: Empresa ──────────────────────────────────────────
    ('editar_empresa',     'Editar datos de la empresa'),

    # ── Módulo: Cuentas de caja ───────────────────────────────────
    ('editar_cuentas',     'Cargar y editar cuentas de caja (tarjetas, billeteras, bancos)'),

    # ── Módulo: Clientes ──────────────────────────────────────────
    ('ver_clientes',       'Ver lista de clientes'),
    ('crear_clientes',     'Crear clientes'),
    ('editar_clientes',    'Editar clientes'),
    ('eliminar_clientes',  'Eliminar clientes'),

    # ── Módulo: Proveedores ───────────────────────────────────────
    ('ver_proveedores',      'Ver lista de proveedores'),
    ('crear_proveedores',    'Crear proveedores'),
    ('editar_proveedores',   'Editar proveedores'),
    ('eliminar_proveedores', 'Eliminar proveedores'),

    # ── Módulo: Stock ─────────────────────────────────────────────
    ('ver_stock',            'Ver niveles de stock'),
    ('ajustar_stock',        'Realizar ajustes de stock'),

    # ── Módulo: Productos ────────────────────────────────────────
    ('ver_productos',          'Ver lista de productos'),
    ('crear_productos',        'Crear productos'),
    ('editar_productos',       'Editar productos'),
    ('eliminar_productos',     'Eliminar productos'),
    ('gestionar_categorias',   'Gestionar categorías y tipos de producto'),
    ('gestionar_listas_descuento', 'Gestionar listas de descuento'),

    # ── Módulo: Compras ───────────────────────────────────────────────
    ('ver_compras',       'Ver historial de compras'),
    ('crear_compras',     'Crear nuevas compras'),
    ('editar_compras',    'Editar compras existentes'),   # ← NUEVO
    ('eliminar_compras',  'Eliminar compras'),            # ← NUEVO

    # ── Módulo: Ventas ───────────────────────────────────────────────
    ('ver_ventas',        'Ver historial de ventas'),
    ('crear_ventas',      'Crear nuevas ventas'),
    ('editar_ventas',     'Editar ventas existentes'),
    ('eliminar_ventas',   'Eliminar ventas'),

    # ── Módulo: Caja ───────────────────────────────────────────────
    ('ver_caja',              'Ver balance y movimientos de caja'),
    ('cargar_movimientos_caja', 'Cargar movimientos manuales en caja'),

    # ── Módulo: Ingresos y egresos ────────────────────────────────
    # (códigos sin cambiar a propósito: renombrarlos revocaría en
    # silencio el permiso de roles que ya lo tengan otorgado)
    ('ver_gastos',       'Ver historial de ingresos y egresos'),
    ('crear_gastos',     'Crear ingresos y egresos'),
    ('editar_gastos',    'Editar ingresos y egresos existentes'),
    ('eliminar_gastos',  'Eliminar ingresos y egresos'),

    # ── Módulo: Créditos y préstamos ──────────────────────────────
    ('ver_deudas',              'Ver créditos y préstamos'),
    ('crear_deudas',            'Crear créditos y préstamos'),
    ('editar_deudas',           'Editar créditos y préstamos existentes'),
    ('eliminar_deudas',         'Eliminar créditos y préstamos'),
    ('confirmar_cuotas_deuda',  'Confirmar el pago de una cuota'),
]

CODIGOS_PERMISOS = {codigo for codigo, _ in PERMISOS_CHOICES}

# Permisos que solo pueden ser otorgados por superusuarios
PERMISOS_RESTRINGIDOS = {
    'editar_empresa',
    'editar_cuentas',
}


# ══════════════════════════════════════════════════════════════════
#  HELPERS — rutas de archivos del personal
# ══════════════════════════════════════════════════════════════════

def _usuario_foto_path(instance, filename):
    import os
    ext    = os.path.splitext(filename)[1].lower()
    nombre = instance.username if instance.username else f'usuario_{instance.pk or "new"}'
    return f'personal/{nombre}/perfil{ext}'

def _usuario_doc_path(instance, filename):
    nombre = instance.usuario.username if instance.usuario_id else 'desconocido'
    return f'personal/{nombre}/documentos/{filename}'


# ══════════════════════════════════════════════════════════════════
#  MANAGER DE USUARIO
# ══════════════════════════════════════════════════════════════════

class UsuarioManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('El nombre de usuario es obligatorio')
        email = self.normalize_email(email) if email else ''
        user  = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(username, email, password, **extra_fields)


# ══════════════════════════════════════════════════════════════════
#  ROL
# ══════════════════════════════════════════════════════════════════

class Rol(models.Model):
    nombre      = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)
    permisos    = models.TextField(
        blank=True, default='',
        help_text='Códigos de permisos separados por coma.'
    )

    def __str__(self):
        return self.nombre

    def get_permisos(self):
        if not self.permisos:
            return set()
        return {p.strip() for p in self.permisos.split(',') if p.strip()}

    def set_permisos(self, lista_codigos):
        self.permisos = ','.join(sorted(lista_codigos))
        self.save()


# ══════════════════════════════════════════════════════════════════
#  USUARIO  (modelo principal — extiende AbstractBaseUser)
# ══════════════════════════════════════════════════════════════════

class Usuario(AbstractBaseUser, PermissionsMixin):

    # ── Credenciales del sistema ──────────────────────────────────
    username    = models.CharField(max_length=150, unique=True)
    email       = models.EmailField(blank=True, null=True)
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    rol         = models.ForeignKey(
        Rol, on_delete=models.SET_NULL, null=True, blank=True
    )

    # ── Identidad personal ────────────────────────────────────────
    first_name       = models.CharField('Nombre/s', max_length=150, blank=True, null=True)
    last_name        = models.CharField('Apellido/s', max_length=150, blank=True, null=True)
    dni              = models.CharField('DNI', max_length=20, blank=True, null=True)
    cuil             = models.CharField('CUIL', max_length=20, blank=True)
    fecha_nacimiento = models.DateField('Fecha de nacimiento', blank=True, null=True)

    GENERO_CHOICES = [
        ('masculino',  'Masculino'),
        ('femenino',   'Femenino'),
        ('no_binario', 'No binario'),
        ('otro',       'Otro'),
        ('nd',         'Prefiero no decir'),
    ]
    genero = models.CharField(max_length=15, choices=GENERO_CHOICES, blank=True)

    ESTADO_CIVIL_CHOICES = [
        ('soltero',    'Soltero/a'),
        ('casado',     'Casado/a'),
        ('divorciado', 'Divorciado/a'),
        ('viudo',      'Viudo/a'),
        ('union',      'Unión convivencial'),
        ('otro',       'Otro'),
    ]
    estado_civil   = models.CharField(max_length=15, choices=ESTADO_CIVIL_CHOICES, blank=True)
    tiene_hijos    = models.BooleanField('Tiene hijos', null=True, blank=True)
    cantidad_hijos = models.PositiveSmallIntegerField('Cantidad de hijos', default=0, null=True, blank=True)
    nacionalidad   = models.CharField(max_length=100, blank=True, default='Argentina')

    # ── Foto de perfil ────────────────────────────────────────────
    foto_perfil = models.ImageField(
        upload_to=_usuario_foto_path,
        blank=True, null=True,
        verbose_name='Foto de perfil'
    )

    # ── Contacto personal ─────────────────────────────────────────
    telefono_personal    = models.CharField(max_length=30, blank=True)
    telefono_alternativo = models.CharField(max_length=30, blank=True)
    email_personal       = models.EmailField('Email personal', blank=True)

    # ── Dirección personal ────────────────────────────────────────
    calle         = models.CharField(max_length=200, blank=True)
    numero        = models.CharField(max_length=20, blank=True)
    piso_depto    = models.CharField('Piso / Depto', max_length=50, blank=True)
    barrio        = models.CharField(max_length=100, blank=True)
    localidad     = models.CharField(max_length=100, blank=True)
    partido       = models.CharField('Partido / Municipio', max_length=100, blank=True)
    provincia     = models.CharField(max_length=100, blank=True)
    pais          = models.CharField(max_length=100, blank=True, default='Argentina')
    codigo_postal = models.CharField('Código postal', max_length=20, blank=True)

    # ── Datos laborales internos ──────────────────────────────────
    legajo        = models.CharField('Nº de legajo', max_length=30, blank=True)
    puesto        = models.CharField('Puesto / Cargo', max_length=150, blank=True)
    area          = models.CharField('Área / Departamento', max_length=100, blank=True)
    sucursal      = models.CharField('Sucursal / Sede', max_length=100, blank=True)
    fecha_ingreso = models.DateField('Fecha de ingreso', blank=True, null=True)
    fecha_egreso  = models.DateField(
        'Fecha de egreso', blank=True, null=True,
        help_text='Completar solo si el empleado se retiró.'
    )

    ESTADO_LABORAL_CHOICES = [
        ('activo',         'Activo'),
        ('licencia',       'En licencia'),
        ('suspendido',     'Suspendido'),
        ('egresado',       'Egresado / Desvinculado'),
        ('periodo_prueba', 'Período de prueba'),
    ]
    estado_laboral = models.CharField(
        max_length=20, choices=ESTADO_LABORAL_CHOICES,
        default='activo', blank=True
    )

    TIPO_CONTRATO_CHOICES = [
        ('indeterminado', 'Tiempo indeterminado'),
        ('determinado',   'Tiempo determinado'),
        ('pasantia',      'Pasantía'),
        ('eventual',      'Eventual / Temporario'),
        ('prestacion',    'Prestación de servicios (monotributista)'),
        ('otro',          'Otro'),
    ]
    tipo_contrato = models.CharField(max_length=20, choices=TIPO_CONTRATO_CHOICES, blank=True)

    MODALIDAD_CHOICES = [
        ('presencial', 'Presencial'),
        ('remoto',     'Remoto'),
        ('hibrido',    'Híbrido'),
    ]
    modalidad_trabajo = models.CharField(max_length=15, choices=MODALIDAD_CHOICES, blank=True)

    salario_bruto = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    banco         = models.CharField('Banco', max_length=100, blank=True)
    cbu           = models.CharField('CBU / CVU', max_length=30, blank=True)
    alias_cbu     = models.CharField('Alias CBU', max_length=50, blank=True)

    # ── Contacto de emergencia ────────────────────────────────────
    emergencia_nombre   = models.CharField('Nombre contacto emergencia', max_length=150, blank=True)
    emergencia_vinculo  = models.CharField(
        'Vínculo', max_length=80, blank=True,
        help_text='Ej: madre, cónyuge, hermano'
    )
    emergencia_telefono = models.CharField('Teléfono emergencia', max_length=30, blank=True)

    # ── Salud ─────────────────────────────────────────────────────
    grupo_sanguineo = models.CharField('Grupo sanguíneo', max_length=10, blank=True,
                          help_text='Ej: A+, O-, AB+')
    obra_social     = models.CharField('Obra social / Prepaga', max_length=150, blank=True)
    nro_afiliado    = models.CharField('Nº afiliado', max_length=50, blank=True)
    apto_psicofisico     = models.BooleanField('Apto psicofísico', null=True, blank=True)
    fecha_apto           = models.DateField('Fecha del apto', blank=True, null=True)
    observaciones_salud  = models.TextField(
        'Observaciones de salud', blank=True,
        help_text='Alergias, medicación habitual, condiciones relevantes'
    )

    # ── Notas internas ────────────────────────────────────────────
    notas_internas = models.TextField('Notas internas (RRHH)', blank=True)

    # ── Auditoría ─────────────────────────────────────────────────
    fecha_modificacion = models.DateTimeField(auto_now=True)

    objects         = UsuarioManager()
    USERNAME_FIELD  = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name        = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.username

    def get_full_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def get_edad(self):
        if not self.fecha_nacimiento:
            return None
        from datetime import date
        hoy  = date.today()
        edad = hoy.year - self.fecha_nacimiento.year
        if (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day):
            edad -= 1
        return edad

    def get_antiguedad(self):
        """Antigüedad como string legible. Ej: '2 años y 3 meses'."""
        if not self.fecha_ingreso:
            return None
        from datetime import date
        fin         = self.fecha_egreso or date.today()
        meses_total = (fin.year  - self.fecha_ingreso.year)  * 12 + \
                      (fin.month - self.fecha_ingreso.month)
        años  = meses_total // 12
        meses = meses_total  % 12
        if años > 0 and meses > 0:
            return f"{años} año{'s' if años > 1 else ''} y {meses} mes{'es' if meses > 1 else ''}"
        if años > 0:
            return f"{años} año{'s' if años > 1 else ''}"
        return f"{meses} mes{'es' if meses > 1 else ''}"

    def get_direccion_completa(self):
        partes = [self.calle, self.numero, self.piso_depto,
                  self.barrio, self.localidad, self.provincia]
        return ', '.join(p for p in partes if p)


# ══════════════════════════════════════════════════════════════════
#  PERMISO OVERRIDE
# ══════════════════════════════════════════════════════════════════

class UsuarioPermisoOverride(models.Model):
    """
    Override individual por usuario.
    concedido=True  → tiene el permiso aunque el rol no lo tenga.
    concedido=False → NO tiene el permiso aunque el rol sí lo tenga.
    """
    usuario   = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='overrides')
    permiso   = models.CharField(max_length=50, choices=PERMISOS_CHOICES)
    concedido = models.BooleanField()

    class Meta:
        unique_together = ('usuario', 'permiso')

    def __str__(self):
        estado = 'PERMITE' if self.concedido else 'DENIEGA'
        return f"{self.usuario.username} — {estado} — {self.permiso}"


# ══════════════════════════════════════════════════════════════════
#  ESTUDIOS DEL PERSONAL
# ══════════════════════════════════════════════════════════════════

class UsuarioEstudio(models.Model):

    NIVEL_CHOICES = [
        ('primario',      'Primario'),
        ('secundario',    'Secundario'),
        ('terciario',     'Terciario / Técnico'),
        ('universitario', 'Universitario'),
        ('posgrado',      'Posgrado / Maestría'),
        ('doctorado',     'Doctorado'),
        ('curso',         'Curso / Taller'),
        ('idioma',        'Idioma'),
        ('otro',          'Otro'),
    ]
    ESTADO_CHOICES = [
        ('completo',   'Completo'),
        ('en_curso',   'En curso'),
        ('incompleto', 'Incompleto / Abandonado'),
    ]

    usuario       = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='estudios')
    nivel         = models.CharField(max_length=20, choices=NIVEL_CHOICES)
    titulo        = models.CharField('Título / Carrera', max_length=200)
    institucion   = models.CharField('Institución', max_length=200, blank=True)
    estado        = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='completo')
    fecha_inicio  = models.DateField(blank=True, null=True)
    fecha_fin     = models.DateField('Fecha de finalización / egreso', blank=True, null=True)
    promedio      = models.DecimalField('Promedio / calificación', max_digits=4, decimal_places=2,
                        blank=True, null=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering        = ['-fecha_fin', '-fecha_inicio']
        verbose_name    = 'Estudio'
        verbose_name_plural = 'Estudios'

    def __str__(self):
        return f"{self.get_nivel_display()} — {self.titulo} ({self.usuario.username})"


# ══════════════════════════════════════════════════════════════════
#  EXPERIENCIA LABORAL PREVIA
# ══════════════════════════════════════════════════════════════════

class UsuarioExperienciaLaboral(models.Model):

    MOTIVO_EGRESO_CHOICES = [
        ('renuncia',      'Renuncia voluntaria'),
        ('despido',       'Despido'),
        ('mutuo_acuerdo', 'Mutuo acuerdo'),
        ('fin_contrato',  'Fin de contrato'),
        ('cierre',        'Cierre de empresa'),
        ('otro',          'Otro'),
    ]

    usuario             = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='experiencias')
    empresa             = models.CharField('Empresa / Empleador', max_length=200)
    puesto              = models.CharField('Puesto / Cargo', max_length=150)
    area                = models.CharField('Área', max_length=100, blank=True)
    descripcion         = models.TextField('Descripción de tareas', blank=True)
    fecha_inicio        = models.DateField()
    fecha_fin           = models.DateField(blank=True, null=True,
                              help_text='Dejar vacío si es el trabajo actual.')
    trabajo_actual      = models.BooleanField('Es trabajo actual', default=False)
    motivo_egreso       = models.CharField(max_length=20, choices=MOTIVO_EGRESO_CHOICES, blank=True)
    referencia_nombre   = models.CharField('Nombre referencia laboral', max_length=150, blank=True)
    referencia_contacto = models.CharField('Contacto referencia', max_length=150, blank=True,
                              help_text='Teléfono o email del referente')
    observaciones       = models.TextField(blank=True)

    class Meta:
        ordering        = ['-fecha_inicio']
        verbose_name    = 'Experiencia laboral'
        verbose_name_plural = 'Experiencias laborales'

    def __str__(self):
        return f"{self.puesto} en {self.empresa} ({self.usuario.username})"

    def get_duracion(self):
        from datetime import date
        fin   = self.fecha_fin or date.today()
        meses = (fin.year - self.fecha_inicio.year) * 12 + (fin.month - self.fecha_inicio.month)
        años  = meses // 12
        resto = meses  % 12
        if años > 0 and resto > 0:
            return f"{años}a {resto}m"
        if años > 0:
            return f"{años} año{'s' if años > 1 else ''}"
        return f"{meses} mes{'es' if meses > 1 else ''}"


# ══════════════════════════════════════════════════════════════════
#  CAPACITACIONES INTERNAS / ONBOARDING
# ══════════════════════════════════════════════════════════════════

class UsuarioCapacitacion(models.Model):

    TIPO_CHOICES = [
        ('onboarding', 'Onboarding / Inducción'),
        ('tecnica',    'Capacitación técnica'),
        ('seguridad',  'Seguridad e higiene'),
        ('blandas',    'Habilidades blandas'),
        ('normativa',  'Normativa / Compliance'),
        ('producto',   'Producto / Servicio'),
        ('otro',       'Otro'),
    ]
    RESULTADO_CHOICES = [
        ('aprobado',    'Aprobado'),
        ('desaprobado', 'Desaprobado'),
        ('en_curso',    'En curso'),
        ('pendiente',   'Pendiente'),
        ('no_aplica',   'No aplica'),
    ]
    MODALIDAD_CHOICES = [
        ('presencial',  'Presencial'),
        ('virtual',     'Virtual / Online'),
        ('mixta',       'Mixta'),
        ('autogestivo', 'Autogestivo'),
    ]

    usuario      = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='capacitaciones')
    nombre       = models.CharField('Nombre de la capacitación', max_length=200)
    tipo         = models.CharField(max_length=20, choices=TIPO_CHOICES, default='tecnica')
    modalidad    = models.CharField(max_length=15, choices=MODALIDAD_CHOICES, blank=True)
    proveedor    = models.CharField('Proveedor / Instructor', max_length=200, blank=True,
                       help_text='Empresa, persona o plataforma que dictó la capacitación')
    fecha_inicio = models.DateField(blank=True, null=True)
    fecha_fin    = models.DateField(blank=True, null=True)
    duracion_hs  = models.DecimalField('Duración (horas)', max_digits=6, decimal_places=1,
                       blank=True, null=True)
    resultado    = models.CharField(max_length=15, choices=RESULTADO_CHOICES, default='pendiente')
    calificacion = models.DecimalField('Calificación obtenida', max_digits=5, decimal_places=2,
                       blank=True, null=True,
                       help_text='Nota o puntaje según escala del proveedor')
    nota_maxima  = models.DecimalField('Nota máxima', max_digits=5, decimal_places=2,
                       blank=True, null=True,
                       help_text='Escala: ej. 10, 100, 5')
    es_obligatoria      = models.BooleanField('Es obligatoria', default=False)
    certificado_emitido = models.BooleanField('Se emitió certificado', default=False)
    vencimiento_cert    = models.DateField('Vencimiento del certificado', blank=True, null=True)
    observaciones       = models.TextField(blank=True)

    class Meta:
        ordering        = ['-fecha_inicio']
        verbose_name    = 'Capacitación'
        verbose_name_plural = 'Capacitaciones'

    def __str__(self):
        return f"{self.nombre} — {self.get_resultado_display()} ({self.usuario.username})"

    def certificado_vigente(self):
        """None = no vence / no aplica. True/False según fecha."""
        if not self.vencimiento_cert:
            return None
        from datetime import date
        return date.today() <= self.vencimiento_cert


# ══════════════════════════════════════════════════════════════════
#  DOCUMENTOS DEL PERSONAL
# ══════════════════════════════════════════════════════════════════

class UsuarioDocumento(models.Model):

    TIPO_CHOICES = [
        ('dni',           'DNI / Identidad'),
        ('contrato',      'Contrato laboral'),
        ('titulo',        'Título / Certificado de estudios'),
        ('certificado',   'Certificado de capacitación'),
        ('apto_medico',   'Apto médico / psicofísico'),
        ('recibo_sueldo', 'Recibo de sueldo'),
        ('constancia',    'Constancia (AFIP, obra social, etc.)'),
        ('obra_social',   'Documentación obra social'),
        ('otro',          'Otro'),
    ]

    usuario       = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='documentos')
    tipo          = models.CharField(max_length=20, choices=TIPO_CHOICES, default='otro')
    nombre        = models.CharField('Descripción del archivo', max_length=200)
    archivo       = models.FileField(upload_to=_usuario_doc_path)
    fecha_doc     = models.DateField('Fecha del documento', blank=True, null=True)
    vencimiento   = models.DateField('Fecha de vencimiento', blank=True, null=True)
    observaciones = models.CharField(max_length=300, blank=True)
    subido_el     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering        = ['-subido_el']
        verbose_name    = 'Documento'
        verbose_name_plural = 'Documentos'

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.nombre} ({self.usuario.username})"

    def vencido(self):
        if not self.vencimiento:
            return False
        from datetime import date
        return date.today() > self.vencimiento

    def proxima_a_vencer(self, dias=30):
        if not self.vencimiento:
            return False
        from datetime import date, timedelta
        return date.today() <= self.vencimiento <= date.today() + timedelta(days=dias)


# ══════════════════════════════════════════════════════════════════
#  CUENTAS BANCARIAS / BILLETERAS DEL PERSONAL
# ══════════════════════════════════════════════════════════════════

class UsuarioCuentaBancaria(models.Model):
    """
    Permite registrar N cuentas bancarias o billeteras por usuario.
    Reemplaza los campos banco/cbu/alias_cbu del modelo Usuario
    (que se conservan en la BD por compatibilidad pero ya no se usan en la UI).
    """
    TIPO_CHOICES = [
        ('banco',     'Banco'),
        ('billetera', 'Billetera virtual'),
        ('cripto',    'Cripto / Exchange'),
        ('otro',      'Otro'),
    ]

    usuario       = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name='cuentas_bancarias'
    )
    tipo          = models.CharField(max_length=15, choices=TIPO_CHOICES, default='banco')
    nombre        = models.CharField(
        'Banco / Entidad', max_length=150,
        help_text='Ej: Banco Nación, Mercado Pago, Ualá'
    )
    titular       = models.CharField(
        'Titular', max_length=150, blank=True,
        help_text='Solo si difiere del empleado'
    )
    cbu_cvu       = models.CharField('CBU / CVU', max_length=30, blank=True)
    alias         = models.CharField('Alias', max_length=50, blank=True)
    nro_cuenta    = models.CharField('Nº de cuenta', max_length=50, blank=True)
    es_principal  = models.BooleanField(
        'Cuenta principal (cobro de haberes)', default=False
    )
    observaciones = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering            = ['-es_principal', 'nombre']
        verbose_name        = 'Cuenta bancaria'
        verbose_name_plural = 'Cuentas bancarias'

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.nombre} ({self.usuario.username})"


# ══════════════════════════════════════════════════════════════════
#  CLIENTES — modelos auxiliares (van ANTES de Cliente)
# ══════════════════════════════════════════════════════════════════

class GrupoFamiliar(models.Model):
    """
    Agrupa clientes que comparten un mismo terreno, edificio o unidad habitacional.
    Ej: "Familia López — Terreno Av. San Martín 450"
    Dentro del grupo cada cliente tiene su propia unidad (Casa A, Depto 3B, etc.)
    """
    apellido_referencia  = models.CharField(max_length=100,
                               help_text='Apellido o nombre de referencia. Ej: López, Rodríguez')
    direccion_referencia = models.CharField(max_length=300, blank=True,
                               help_text='Dirección del terreno/edificio compartido')
    descripcion          = models.TextField(blank=True)
    fecha_creacion       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering        = ['apellido_referencia']
        verbose_name    = 'Grupo familiar'
        verbose_name_plural = 'Grupos familiares'

    def __str__(self):
        return f"Familia {self.apellido_referencia}" + (
            f" — {self.direccion_referencia}" if self.direccion_referencia else ''
        )

    def get_nombre_display(self):
        return f"Familia {self.apellido_referencia}"


# ══════════════════════════════════════════════════════════════════
#  CLIENTE — modelo principal
# ══════════════════════════════════════════════════════════════════

def _generar_codigo_cliente():
    """
    Genera el próximo código único con formato GK-NNNNNN-XX.
    Números: 000001 → 999999 → reset + avance de letras.
    Letras:  AA → AZ → BA → ... → ZZ.
    Protegido con select_for_update para evitar race conditions.
    """
    ultimo = (
        Cliente.objects
        .select_for_update()
        .exclude(codigo='')
        .order_by('-codigo')
        .values_list('codigo', flat=True)
        .first()
    )

    if not ultimo:
        return 'GK-000001-AA'

    try:
        partes = ultimo.split('-')
        numero = int(partes[1])
        letras = partes[2]
        letra1 = ord(letras[0]) - ord('A')
        letra2 = ord(letras[1]) - ord('A')
    except (IndexError, ValueError):
        return 'GK-000001-AA'

    numero += 1
    if numero > 999999:
        numero  = 0
        letra2 += 1
        if letra2 > 25:
            letra2  = 0
            letra1 += 1
            if letra1 > 25:
                letra1 = 0

    nuevas_letras = chr(ord('A') + letra1) + chr(ord('A') + letra2)
    return f'GK-{numero:06d}-{nuevas_letras}'


class Cliente(models.Model):

    # ── Código único ──────────────────────────────────────────────
    codigo = models.CharField(max_length=15, unique=True, blank=True,
                 help_text='Generado automáticamente. Formato: GK-000000-AA')

    # ── Tipo ──────────────────────────────────────────────────────
    TIPO_CHOICES = [
        ('persona', 'Persona física'),
        ('empresa', 'Empresa / Persona jurídica'),
    ]
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='persona')

    # ── Estado ────────────────────────────────────────────────────
    ESTADO_CHOICES = [
        ('activo',     'Activo'),
        ('inactivo',   'Inactivo'),
        ('potencial',  'Potencial'),
        ('suspendido', 'Suspendido'),
    ]
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='activo')

    # ── Scoring y riesgo ──────────────────────────────────────────
    scoring = models.IntegerField(default=1000,
                  help_text='Puntuación del cliente. Inicia en 1000.')
    NIVEL_RIESGO_CHOICES = [
        ('bajo',  'Bajo'),
        ('medio', 'Medio'),
        ('alto',  'Alto'),
    ]
    nivel_riesgo = models.CharField(max_length=10, choices=NIVEL_RIESGO_CHOICES,
                       default='bajo', blank=True)

    # ── Identificación — Persona física ───────────────────────────
    nombre           = models.CharField(max_length=150, blank=True)
    apellido         = models.CharField(max_length=150, blank=True)
    dni              = models.CharField('DNI', max_length=20, blank=True)
    cuil             = models.CharField('CUIL', max_length=20, blank=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    genero           = models.CharField(max_length=20, blank=True)
    ocupacion        = models.CharField(max_length=100, blank=True)

    # ── Identificación — Empresa ──────────────────────────────────
    razon_social     = models.CharField('Razón social', max_length=200, blank=True)
    nombre_comercial = models.CharField('Nombre comercial', max_length=200, blank=True)
    cuit             = models.CharField('CUIT', max_length=20, blank=True)
    cond_iva         = models.CharField('Condición ante IVA', max_length=50, blank=True)
    rubro            = models.CharField(max_length=100, blank=True)
    sitio_web        = models.URLField(blank=True)
    fecha_fundacion  = models.DateField(blank=True, null=True)

    # ── Contacto digital ──────────────────────────────────────────
    email_principal  = models.EmailField(blank=True)
    email_secundario = models.EmailField(blank=True)
    instagram        = models.CharField(max_length=100, blank=True)
    facebook         = models.CharField(max_length=200, blank=True)
    linkedin         = models.URLField(blank=True)

    CANAL_PREFERIDO_CHOICES = [
        ('whatsapp',   'WhatsApp'),
        ('llamada',    'Llamada telefónica'),
        ('email',      'Email'),
        ('sms',        'SMS'),
        ('presencial', 'Presencial'),
    ]
    canal_preferido = models.CharField(max_length=15, choices=CANAL_PREFERIDO_CHOICES,
                          blank=True, default='whatsapp')

    # ── Dirección ─────────────────────────────────────────────────
    calle         = models.CharField(max_length=200, blank=True)
    numero        = models.CharField(max_length=20, blank=True)
    piso_depto    = models.CharField('Piso / Depto', max_length=50, blank=True)
    barrio        = models.CharField(max_length=100, blank=True)
    localidad     = models.CharField(max_length=100, blank=True)
    partido       = models.CharField('Partido / Municipio', max_length=100, blank=True)
    provincia     = models.CharField(max_length=100, blank=True)
    pais          = models.CharField(max_length=100, blank=True, default='Argentina')
    codigo_postal = models.CharField('Código postal', max_length=20, blank=True)

    # ── Grupo familiar / convivencia ──────────────────────────────
    grupo_familiar = models.ForeignKey(
        GrupoFamiliar, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='clientes',
        verbose_name='Grupo familiar / Terreno'
    )
    unidad_habitacional = models.CharField(max_length=50, blank=True,
                              help_text='Ej: Casa A, Depto 3B, Lote 2')

    # ── Geolocalización ───────────────────────────────────────────
    latitud  = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitud = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    maps_url = models.URLField('URL de mapa', blank=True)

    # ── Foto de perfil ────────────────────────────────────────────
    foto_perfil = models.ImageField(upload_to='clientes/perfiles/', blank=True, null=True)

    # ── CRM ───────────────────────────────────────────────────────
    notas            = models.TextField('Notas internas', blank=True)
    como_nos_conocio = models.CharField('¿Cómo nos conoció?', max_length=200, blank=True)
    tags             = models.CharField(max_length=500, blank=True,
                           help_text='Etiquetas separadas por coma. Ej: VIP, moroso, potencial')
    referido_por = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='referidos',
        verbose_name='Referido por'
    )
    fecha_desde_cliente    = models.DateField('Cliente desde', blank=True, null=True)
    fecha_ultimo_contacto  = models.DateField(blank=True, null=True)
    fecha_proximo_contacto = models.DateField(blank=True, null=True)

    # ── Auditoría ─────────────────────────────────────────────────
    creado_por         = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='clientes_creados'
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['apellido', 'nombre', 'razon_social']
        verbose_name    = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        if self.tipo == 'empresa':
            return self.razon_social or self.nombre_comercial or f'Empresa #{self.pk}'
        return f"{self.nombre} {self.apellido}".strip() or f'Cliente #{self.pk}'

    def get_nombre_display(self):
        if self.tipo == 'empresa':
            return self.nombre_comercial or self.razon_social or str(self)
        return f"{self.nombre} {self.apellido}".strip() or str(self)

    def get_direccion_completa(self):
        partes = [self.calle, self.numero, self.piso_depto,
                  self.barrio, self.localidad, self.provincia]
        return ', '.join(p for p in partes if p)

    def tiene_geolocalizacion(self):
        return self.latitud is not None and self.longitud is not None

    def get_tags_lista(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def telefono_titular_movil(self):
        return self.telefonos.filter(tipo='movil', es_titular=True).first()

    def telefono_titular_fijo(self):
        return self.telefonos.filter(tipo='fijo', es_titular=True).first()

    def save(self, *args, **kwargs):
        if not self.codigo:
            with transaction.atomic():
                self.codigo = _generar_codigo_cliente()
        super().save(*args, **kwargs)


# ══════════════════════════════════════════════════════════════════
#  TELÉFONOS DEL CLIENTE
# ══════════════════════════════════════════════════════════════════

class ClienteTelefono(models.Model):
    """
    Teléfonos del cliente. Modelo separado para N teléfonos sin límite.
    Regla: solo puede haber UN titular por tipo (móvil/fijo) por cliente.
    """
    TIPO_CHOICES = [
        ('movil', 'Móvil'),
        ('fijo',  'Fijo'),
    ]
    cliente        = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='telefonos')
    numero         = models.CharField(max_length=30)
    tipo           = models.CharField(max_length=5, choices=TIPO_CHOICES, default='movil')
    es_titular     = models.BooleanField(default=False,
                         help_text='Número principal de este tipo. Solo uno por tipo por cliente.')
    descripcion    = models.CharField(max_length=100, blank=True,
                         help_text='Ej: trabajo, esposa, emergencia')
    tiene_whatsapp = models.BooleanField(default=False)

    class Meta:
        ordering        = ['-es_titular', 'tipo', 'id']
        verbose_name    = 'Teléfono'
        verbose_name_plural = 'Teléfonos'

    def __str__(self):
        titular = ' (titular)' if self.es_titular else ''
        return f"{self.numero} [{self.get_tipo_display()}]{titular} — {self.cliente}"

    def save(self, *args, **kwargs):
        # Si se marca como titular, desmarcar los otros del mismo tipo
        if self.es_titular:
            ClienteTelefono.objects.filter(
                cliente=self.cliente, tipo=self.tipo, es_titular=True
            ).exclude(pk=self.pk).update(es_titular=False)
        super().save(*args, **kwargs)


# ══════════════════════════════════════════════════════════════════
#  IMÁGENES DEL CLIENTE
# ══════════════════════════════════════════════════════════════════

def _cliente_imagen_path(instance, filename):
    """
    Guarda en media/clientes/<codigo_gk>/filename
    Usa el código GK si está disponible, sino el pk.
    """
    import os
    cliente      = instance.cliente
    carpeta      = cliente.codigo if cliente.codigo else str(cliente.pk)
    nombre_limpio = os.path.basename(filename)
    return f'clientes/{carpeta}/{nombre_limpio}'


class ClienteImagen(models.Model):
    TIPO_CHOICES = [
        ('local',     'Foto del local / oficina'),
        ('fachada',   'Fachada exterior'),
        ('producto',  'Producto o servicio'),
        ('documento', 'Documento'),
        ('equipo',    'Equipo / Instalación'),
        ('otro',      'Otro'),
    ]
    cliente     = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='imagenes')
    imagen      = models.ImageField(upload_to=_cliente_imagen_path)
    tipo        = models.CharField(max_length=20, choices=TIPO_CHOICES, default='otro')
    descripcion = models.CharField(max_length=200, blank=True)
    orden       = models.PositiveIntegerField(default=0)
    subida_el   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['orden', 'subida_el']

    def __str__(self):
        return f"Imagen de {self.cliente} — {self.get_tipo_display()}"


# ══════════════════════════════════════════════════════════════════
#  CONTACTOS ADICIONALES DEL CLIENTE
# ══════════════════════════════════════════════════════════════════

class ClienteContactoAdicional(models.Model):
    ROL_CHOICES = [
        ('administrativo', 'Administrativo'),
        ('tecnico',        'Técnico'),
        ('gerencia',       'Gerencia / Dirección'),
        ('ventas',         'Ventas / Comercial'),
        ('cobranza',       'Cobranza'),
        ('familiar',       'Familiar'),
        ('otro',           'Otro'),
    ]
    cliente  = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='contactos_adicionales')
    nombre   = models.CharField(max_length=150)
    apellido = models.CharField(max_length=150, blank=True)
    rol      = models.CharField(max_length=20, choices=ROL_CHOICES, default='otro')
    telefono = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    email    = models.EmailField(blank=True)
    notas    = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['apellido', 'nombre']

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.get_rol_display()}) — {self.cliente}"


# ══════════════════════════════════════════════════════════════════
#  DATOS DE LA EMPRESA
# ══════════════════════════════════════════════════════════════════

class CondicionIVA(models.TextChoices):
    RESPONSABLE_INSCRIPTO = 'RI', 'Responsable Inscripto'
    MONOTRIBUTISTA = 'M', 'Monotributista'
    EXENTO = 'E', 'Exento'
    CONSUMIDOR_FINAL = 'CF', 'Consumidor Final'


def _empresa_logo_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'empresa/logo{ext}'


class DatosEmpresa(models.Model):
    """
    Modelo singleton para guardar los datos de la empresa.
    Solo debe existir un registro en la base de datos.
    """
    nombre_comercial = models.CharField(max_length=200, default='Mi Empresa')
    razon_social = models.CharField(max_length=200, blank=True)
    cuit = models.CharField(max_length=13, blank=True, help_text='XX-XXXXXXXX-X')
    condicion_iva = models.CharField(max_length=3, choices=CondicionIVA.choices, blank=True)
    domicilio = models.CharField(max_length=300, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to=_empresa_logo_path, blank=True, null=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Datos de la empresa'
        verbose_name_plural = 'Datos de la empresa'

    def __str__(self):
        return self.nombre_comercial

    @classmethod
    def get_solo(cls):
        """
        Devuelve el único registro de DatosEmpresa, creándolo si no existe.
        """
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'nombre_comercial': 'Mi Empresa',
            }
        )
        return obj

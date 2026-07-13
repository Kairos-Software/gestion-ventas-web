from django import forms
from .models import (
    Proveedor,
    Producto, ProductoImagen, ModoPrecio,
    CategoriaProducto, TipoProducto,
    Variante, OpcionVariante, CombinacionVariante,
)

class ProveedorForm(forms.ModelForm):

    class Meta:
        model  = Proveedor
        fields = [
            # Identidad
            'nombre', 'cuit', 'tipo', 'activo', 'sitio_web', 'descripcion',
            # Contacto
            'email', 'telefono', 'contacto_nombre', 'contacto_cargo',
            # Dirección
            'calle', 'ciudad', 'provincia', 'pais',
            # Comercial
            'condicion_pago', 'moneda', 'dias_entrega', 'notas',
        ]
        widgets = {
            'nombre':           forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Razón social o nombre'}),
            'cuit':             forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'XX-XXXXXXXX-X'}),
            'tipo':             forms.Select(attrs={'class': 'form-select nx-input'}),
            'activo':           forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sitio_web':        forms.URLInput(attrs={'class': 'form-control nx-input', 'placeholder': 'https://'}),
            'descripcion':      forms.Textarea(attrs={'class': 'form-control nx-input', 'rows': 3, 'placeholder': 'Descripción interna...'}),
            'email':            forms.EmailInput(attrs={'class': 'form-control nx-input', 'placeholder': 'contacto@proveedor.com'}),
            'telefono':         forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': '+54 11 XXXX-XXXX'}),
            'contacto_nombre':  forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Nombre del contacto'}),
            'contacto_cargo':   forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Cargo'}),
            'calle':            forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Calle y número'}),
            'ciudad':           forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Ciudad'}),
            'provincia':        forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Provincia'}),
            'pais':             forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'País'}),
            'condicion_pago':   forms.Select(attrs={'class': 'form-select nx-input'}),
            'moneda':           forms.Select(attrs={'class': 'form-select nx-input'}),
            'dias_entrega':     forms.NumberInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Ej: 5', 'min': 0}),
            'notas':            forms.Textarea(attrs={'class': 'form-control nx-input', 'rows': 3, 'placeholder': 'Notas internas...'}),
        }

    def clean_cuit(self):
        cuit = self.cleaned_data.get('cuit', '').strip()
        # Elimina guiones para validar solo dígitos
        solo_digitos = cuit.replace('-', '')
        if cuit and (not solo_digitos.isdigit() or len(solo_digitos) != 11):
            raise forms.ValidationError('El CUIT debe tener 11 dígitos (formato XX-XXXXXXXX-X).')
        return cuit

    def clean_sitio_web(self):
        url = self.cleaned_data.get('sitio_web', '').strip()
        if url and not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url
    

# ══════════════════════════════════════════════════════════════════
#  CATEGORÍA  (AJAX — crear/editar desde modal)
# ══════════════════════════════════════════════════════════════════
 
class CategoriaProductoForm(forms.ModelForm):
    class Meta:
        model  = CategoriaProducto
        fields = ['nombre', 'descripcion', 'orden', 'activo']
        widgets = {
            'nombre':      forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Ej: Electrónica, Indumentaria, Automotriz...',
                'autofocus': True,
            }),
            'descripcion': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Descripción breve (opcional)',
            }),
            'orden':       forms.NumberInput(attrs={
                'class': 'form-control nx-input',
                'min': 0,
            }),
            'activo':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
 
    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        qs = CategoriaProducto.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe una categoría con ese nombre.')
        return nombre
 
 
# ══════════════════════════════════════════════════════════════════
#  TIPO DE PRODUCTO  (AJAX — crear/editar desde modal)
# ══════════════════════════════════════════════════════════════════
 
class TipoProductoForm(forms.ModelForm):
    class Meta:
        model  = TipoProducto
        fields = ['nombre', 'descripcion', 'orden', 'activo']
        widgets = {
            'nombre':      forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Ej: Sedán, Remera, Industrial...',
                'autofocus': True,
            }),
            'descripcion': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Descripción breve (opcional)',
            }),
            'orden':       forms.NumberInput(attrs={
                'class': 'form-control nx-input',
                'min': 0,
            }),
            'activo':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
 
    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        qs = TipoProducto.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un tipo con ese nombre.')
        return nombre
 
 
# ══════════════════════════════════════════════════════════════════
#  VARIANTES GENÉRICAS  (AJAX — crear/editar desde modal)
# ══════════════════════════════════════════════════════════════════

class VarianteForm(forms.ModelForm):
    class Meta:
        model  = Variante
        fields = ['nombre', 'descripcion', 'orden', 'activo']
        widgets = {
            'nombre':      forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Ej: Color, Sabor, Talle, Aroma...',
                'autofocus': True,
            }),
            'descripcion': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Descripción breve (opcional)',
            }),
            'orden':       forms.NumberInput(attrs={
                'class': 'form-control nx-input',
                'min': 0,
            }),
            'activo':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        qs = Variante.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe una variante con ese nombre.')
        return nombre


class OpcionVarianteForm(forms.ModelForm):
    class Meta:
        model  = OpcionVariante
        fields = ['variante', 'nombre', 'descripcion', 'orden', 'activo']
        widgets = {
            'variante':    forms.Select(attrs={'class': 'form-select nx-input'}),
            'nombre':      forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Ej: Rojo, Verde, S, M, L, Naranja...',
                'autofocus': True,
            }),
            'descripcion': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Descripción breve (opcional)',
            }),
            'orden':       forms.NumberInput(attrs={
                'class': 'form-control nx-input',
                'min': 0,
            }),
            'activo':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo mostrar variantes activas
        self.fields['variante'].queryset = Variante.objects.filter(activo=True).order_by('orden', 'nombre')

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        variante = self.cleaned_data.get('variante')
        qs = OpcionVariante.objects.filter(variante=variante, nombre__iexact=nombre)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe una opción con ese nombre para esta variante.')
        return nombre


class CombinacionVarianteForm(forms.ModelForm):
    class Meta:
        model  = CombinacionVariante
        fields = ['codigo_barras', 'sku_variante', 'stock_actual', 'activo']
        widgets = {
            'codigo_barras': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Código de barras específico para esta combinación',
            }),
            'sku_variante': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'SKU específico (opcional)',
            }),
            'stock_actual': forms.NumberInput(attrs={
                'class': 'form-control nx-input',
                'min': 0,
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ══════════════════════════════════════════════════════════════════
#  PRODUCTO  (form principal)
# ══════════════════════════════════════════════════════════════════

class ProductoForm(forms.ModelForm):
    class Meta:
        model  = Producto
        fields = [
            # Identificación
            'codigo', 'sku', 'codigo_barras',
            'nombre', 'nombre_corto',
            'descripcion', 'descripcion_publica',
            # Clasificación
            'categoria', 'tipo',
            # Marca
            'marca', 'modelo', 'fabricante', 'pais_origen',
            # Unidad
            'unidad_medida', 'contenido_neto',
            # Dimensiones
            'peso_kg', 'alto_cm', 'ancho_cm', 'profundidad_cm',
            # Precios
            'precio_venta', 'modo_precio', 'porcentaje_ganancia',
            # Estado y visibilidad (publicado se maneja con botón toggle en tabla)
            'estado', 'publicado', 'destacado',
            # Logística
            'requiere_refrigeracion', 'es_fragil', 'es_peligroso',
            'posicion_deposito',
            # Stock
            'gestiona_stock', 'permite_stock_negativo',
            # Variantes
            'gestiona_variantes',
            # Perecedero
            'es_perecedero',
            # Notas
            'notas', 'tags',
        ]
        widgets = {
            # — Identificación —
            'codigo':       forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Dejar vacío para generar automáticamente',
            }),
            'sku':          forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'SKU / código interno',
            }),
            'codigo_barras': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'EAN-13, UPC...',
            }),
            'nombre':       forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Nombre completo del producto',
                'autofocus': True,
            }),
            'nombre_corto': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Nombre corto para tickets y etiquetas',
            }),
            'descripcion':  forms.Textarea(attrs={
                'class': 'form-control nx-input',
                'rows': 3,
                'placeholder': 'Descripción interna...',
            }),
            'descripcion_publica': forms.Textarea(attrs={
                'class': 'form-control nx-input',
                'rows': 3,
                'placeholder': 'Descripción para catálogo público...',
            }),
 
            # — Clasificación —
            'categoria':    forms.Select(attrs={'class': 'form-select nx-input'}),
            'tipo':         forms.Select(attrs={'class': 'form-select nx-input'}),
 
            # — Marca —
            'marca':        forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Marca'}),
            'modelo':       forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Modelo'}),
            'fabricante':   forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Fabricante'}),
            'pais_origen':  forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'País de origen'}),
 
            # — Unidad —
            'unidad_medida':  forms.Select(attrs={'class': 'form-select nx-input'}),
            'contenido_neto': forms.NumberInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Ej: 500',
                'step': '0.001', 'min': '0',
            }),
 
            # — Dimensiones —
            'peso_kg':       forms.NumberInput(attrs={'class': 'form-control nx-input', 'step': '0.001', 'min': '0', 'placeholder': '0.000'}),
            'alto_cm':       forms.NumberInput(attrs={'class': 'form-control nx-input', 'step': '0.01',  'min': '0', 'placeholder': '0.00'}),
            'ancho_cm':      forms.NumberInput(attrs={'class': 'form-control nx-input', 'step': '0.01',  'min': '0', 'placeholder': '0.00'}),
            'profundidad_cm':forms.NumberInput(attrs={'class': 'form-control nx-input', 'step': '0.01',  'min': '0', 'placeholder': '0.00'}),
 
            # — Precios —
            'precio_venta':     forms.NumberInput(attrs={'class': 'form-control nx-input', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'modo_precio':      forms.Select(attrs={'class': 'form-select nx-input'}),
            'porcentaje_ganancia': forms.NumberInput(attrs={'class': 'form-control nx-input', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
 
            # — Estado —
            'estado':     forms.Select(attrs={'class': 'form-select nx-input'}),
            'publicado':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'destacado':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
 
            # — Logística —
            'requiere_refrigeracion': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_fragil':              forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_peligroso':           forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_perecedero':          forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'posicion_deposito':      forms.TextInput(attrs={'class': 'form-control nx-input', 'placeholder': 'Ej: A3-P2'}),

            # — Stock —
            'gestiona_stock':         forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'permite_stock_negativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # — Variantes genéricas —
            'gestiona_variantes':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # — Notas —
            'notas': forms.Textarea(attrs={
                'class': 'form-control nx-input',
                'rows': 3,
                'placeholder': 'Notas internas del equipo...',
            }),
            'tags': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Ej: importado, liquidación, nuevo (separadas por coma)',
            }),
        }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo mostrar categorías y tipos activos en los selects
        self.fields['categoria'].queryset = CategoriaProducto.objects.filter(activo=True).order_by('orden', 'nombre')
        self.fields['tipo'].queryset      = TipoProducto.objects.filter(activo=True).order_by('orden', 'nombre')
        # Campos opcionales — no requeridos en el form
        self.fields['categoria'].required = False
        self.fields['tipo'].required      = False
 
    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo', '').strip()
        if not codigo:
            return codigo  # Se genera en el modelo
        qs = Producto.objects.filter(codigo__iexact=codigo)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un producto con ese código.')
        return codigo

    def clean(self):
        cleaned_data = super().clean()
        modo_precio = cleaned_data.get('modo_precio')
        porcentaje_ganancia = cleaned_data.get('porcentaje_ganancia')
        if modo_precio == ModoPrecio.AUTOMATICO and porcentaje_ganancia is None:
            self.add_error('porcentaje_ganancia', 'Requerido cuando el precio es automático.')
        return cleaned_data
 
 
 
# ══════════════════════════════════════════════════════════════════
#  IMAGEN DE PRODUCTO  (para upload individual vía AJAX)
# ══════════════════════════════════════════════════════════════════
 
class ProductoImagenForm(forms.ModelForm):
    class Meta:
        model  = ProductoImagen
        fields = ['imagen', 'es_portada', 'descripcion', 'orden']
        widgets = {
            'imagen':      forms.ClearableFileInput(attrs={'class': 'form-control nx-input'}),
            'es_portada':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'descripcion': forms.TextInput(attrs={
                'class': 'form-control nx-input',
                'placeholder': 'Descripción de la imagen (opcional)',
            }),
            'orden':       forms.NumberInput(attrs={'class': 'form-control nx-input', 'min': 0}),
        }
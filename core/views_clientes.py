# core/views_clientes.py
import os
import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import transaction
from django.conf import settings

from .models import (
    Cliente, ClienteImagen, ClienteContactoAdicional,
    ClienteTelefono, GrupoFamiliar
)
from .forms_clientes import (
    FormularioClienteBase, FormularioClienteImagen,
    FormularioContactoAdicional, FormularioClienteTelefono,
    FormularioGrupoFamiliar,
)
from .permisos import chequear_permiso


# ── Serialización ─────────────────────────────────────────────────

def _telefono_a_dict(t):
    return {
        'id':           t.pk,
        'numero':       t.numero,
        'tipo':         t.tipo,
        'tipo_display': t.get_tipo_display(),
        'es_titular':   t.es_titular,
        'descripcion':  t.descripcion,
        'tiene_whatsapp': t.tiene_whatsapp,
    }


def _cliente_a_dict(c):
    return {
        'id':             c.pk,
        'codigo':         c.codigo,
        'tipo':           c.tipo,
        'estado':         c.estado,
        'scoring':        c.scoring,
        'nivel_riesgo':   c.nivel_riesgo,
        'nombre_display': c.get_nombre_display(),
        # Persona
        'nombre':           c.nombre,
        'apellido':         c.apellido,
        'dni':              c.dni,
        'cuil':             c.cuil,
        'fecha_nacimiento': str(c.fecha_nacimiento) if c.fecha_nacimiento else '',
        'genero':           c.genero,
        'ocupacion':        c.ocupacion,
        # Empresa
        'razon_social':     c.razon_social,
        'nombre_comercial': c.nombre_comercial,
        'cuit':             c.cuit,
        'cond_iva':         c.cond_iva,
        'rubro':            c.rubro,
        'sitio_web':        c.sitio_web,
        'fecha_fundacion':  str(c.fecha_fundacion) if c.fecha_fundacion else '',
        # Contacto
        'email_principal':  c.email_principal,
        'email_secundario': c.email_secundario,
        'instagram':        c.instagram,
        'facebook':         c.facebook,
        'linkedin':         c.linkedin,
        'canal_preferido':  c.canal_preferido,
        # Teléfonos
        'telefonos': [_telefono_a_dict(t) for t in c.telefonos.all()],
        # Dirección
        'calle':          c.calle,
        'numero':         c.numero,
        'piso_depto':     c.piso_depto,
        'barrio':         c.barrio,
        'localidad':      c.localidad,
        'partido':        c.partido,
        'provincia':      c.provincia,
        'pais':           c.pais,
        'codigo_postal':  c.codigo_postal,
        'direccion_completa': c.get_direccion_completa(),
        # Grupo familiar
        'grupo_familiar_id':    c.grupo_familiar_id,
        'grupo_familiar_nombre': str(c.grupo_familiar) if c.grupo_familiar else '',
        'unidad_habitacional':  c.unidad_habitacional,
        # Geo
        'latitud':   str(c.latitud) if c.latitud is not None else '',
        'longitud':  str(c.longitud) if c.longitud is not None else '',
        'maps_url':  c.maps_url,
        # CRM
        'notas':             c.notas,
        'como_nos_conocio':  c.como_nos_conocio,
        'tags':              c.tags,
        'tags_lista':        c.get_tags_lista(),
        'referido_por_id':   c.referido_por_id,
        'referido_por_nombre': c.referido_por.get_nombre_display() if c.referido_por else '',
        'fecha_desde_cliente':     str(c.fecha_desde_cliente) if c.fecha_desde_cliente else '',
        'fecha_ultimo_contacto':   str(c.fecha_ultimo_contacto) if c.fecha_ultimo_contacto else '',
        'fecha_proximo_contacto':  str(c.fecha_proximo_contacto) if c.fecha_proximo_contacto else '',
        # Imágenes
        'imagenes': [
            {
                'id':   img.pk,
                'url':  img.imagen.url,
                'tipo': img.get_tipo_display(),
            }
            for img in c.imagenes.all()
        ],
        # Auditoría
        'fecha_alta':         c.fecha_alta.strftime('%d/%m/%Y %H:%M'),
        'fecha_modificacion': c.fecha_modificacion.strftime('%d/%m/%Y %H:%M'),
        'creado_por':         c.creado_por.username if c.creado_por else '',
    }


# ── Lista de clientes ─────────────────────────────────────────────

class GestionClientesView(LoginRequiredMixin, View):
    def get(self, request):
        puede_ver = chequear_permiso(request.user, 'ver_clientes')

        if puede_ver:
            qs = Cliente.objects.select_related('creado_por', 'referido_por', 'grupo_familiar')

            q = request.GET.get('q', '').strip()
            if q:
                qs = qs.filter(
                    Q(codigo__icontains=q) |
                    Q(nombre__icontains=q) |
                    Q(apellido__icontains=q) |
                    Q(razon_social__icontains=q) |
                    Q(nombre_comercial__icontains=q) |
                    Q(email_principal__icontains=q) |
                    Q(dni__icontains=q) | Q(cuit__icontains=q) |
                    Q(tags__icontains=q) |
                    Q(telefonos__numero__icontains=q)
                ).distinct()

            tipo   = request.GET.get('tipo', '')
            estado = request.GET.get('estado', '')
            riesgo = request.GET.get('riesgo', '')
            if tipo:   qs = qs.filter(tipo=tipo)
            if estado: qs = qs.filter(estado=estado)
            if riesgo: qs = qs.filter(nivel_riesgo=riesgo)

            paginator = Paginator(qs, 25)
            clientes  = paginator.get_page(request.GET.get('page', 1))
        else:
            clientes = []

        context = {
            'clientes':      clientes,
            'sin_permiso':   not puede_ver,
            'q':             request.GET.get('q', ''),
            'filtro_tipo':   request.GET.get('tipo', ''),
            'filtro_estado': request.GET.get('estado', ''),
            'filtro_riesgo': request.GET.get('riesgo', ''),
            'puede_crear':   chequear_permiso(request.user, 'crear_clientes'),
            'puede_editar':  chequear_permiso(request.user, 'editar_clientes'),
            'puede_eliminar':chequear_permiso(request.user, 'eliminar_clientes'),
            'tipo_choices':   Cliente.TIPO_CHOICES,
            'estado_choices': Cliente.ESTADO_CHOICES,
            'riesgo_choices': Cliente.NIVEL_RIESGO_CHOICES,
        }
        return render(request, 'core/gestion_clientes.html', context)


# ── Detalle de cliente ────────────────────────────────────────────

class ClienteDetalleView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not chequear_permiso(request.user, 'ver_clientes'):
            return render(request, 'core/gestion_clientes.html', {
                'clientes': [], 'sin_permiso': True,
                'puede_crear': False, 'puede_editar': False, 'puede_eliminar': False,
                'error_msg': 'No tenés permiso para ver clientes.',
            }, status=403)

        cliente = get_object_or_404(
            Cliente.objects.prefetch_related(
                'imagenes', 'contactos_adicionales', 'telefonos'
            ).select_related('grupo_familiar', 'referido_por', 'creado_por'),
            pk=pk
        )

        # Clientes del mismo grupo familiar (excluyendo el actual)
        convivientes = []
        if cliente.grupo_familiar:
            convivientes = Cliente.objects.filter(
                grupo_familiar=cliente.grupo_familiar
            ).exclude(pk=pk)

        context = {
            'cliente':        cliente,
            'imagenes':       cliente.imagenes.all(),
            'contactos':      cliente.contactos_adicionales.all(),
            'telefonos':      cliente.telefonos.all(),
            'convivientes':   convivientes,
            'puede_editar':   chequear_permiso(request.user, 'editar_clientes'),
            'puede_eliminar': chequear_permiso(request.user, 'eliminar_clientes'),
        }
        return render(request, 'core/detalle_cliente.html', context)


# ── AJAX: Crear / Editar cliente ─────────────────────────────────

class ClienteCrearEditarAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.GET.get('get_pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido'}, status=400)
        cliente = get_object_or_404(
            Cliente.objects.prefetch_related('telefonos', 'imagenes'), pk=pk
        )
        return JsonResponse({'cliente': _cliente_a_dict(cliente)})

    def post(self, request):
        pk = request.POST.get('pk')

        if pk:
            if not chequear_permiso(request.user, 'editar_clientes'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            cliente = get_object_or_404(Cliente, pk=pk)
            # Guardar la foto anterior para eliminarla si se sube una nueva
            old_photo = cliente.foto_perfil if cliente.foto_perfil else None
            form = FormularioClienteBase(request.POST, request.FILES, instance=cliente)
        else:
            if not chequear_permiso(request.user, 'crear_clientes'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = FormularioClienteBase(request.POST, request.FILES)
            old_photo = None

        if form.is_valid():
            cliente = form.save(commit=False)
            if not pk:
                cliente.creado_por = request.user

            # Si se sube una nueva foto de perfil y hay una anterior, eliminar la anterior
            if pk and 'foto_perfil' in request.FILES and old_photo and os.path.isfile(old_photo.path):
                os.remove(old_photo.path)

            cliente.save()

            # Guardar teléfonos enviados desde el formulario (listas paralelas)
            numeros   = request.POST.getlist('tel_numero[]')
            tipos     = request.POST.getlist('tel_tipo[]')
            descs     = request.POST.getlist('tel_desc[]')
            titulares = request.POST.getlist('tel_titular[]')
            whatsapps = request.POST.getlist('tel_whatsapp[]')

            if numeros:
                # En edición: reemplazar todos los teléfonos
                if pk:
                    cliente.telefonos.all().delete()
                for i, numero in enumerate(numeros):
                    numero = numero.strip()
                    if not numero:
                        continue
                    ClienteTelefono.objects.create(
                        cliente       = cliente,
                        numero        = numero,
                        tipo          = tipos[i] if i < len(tipos) else 'movil',
                        descripcion   = descs[i] if i < len(descs) else '',
                        es_titular    = (titulares[i] == '1') if i < len(titulares) else False,
                        tiene_whatsapp= (whatsapps[i] == '1') if i < len(whatsapps) else False,
                    )

            return JsonResponse({'success': True, 'cliente': _cliente_a_dict(cliente)})

        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


# ── AJAX: Eliminar cliente ────────────────────────────────────────

class ClienteEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.POST.get('pk') or request.GET.get('pk')
        cliente = get_object_or_404(Cliente, pk=pk)

        # Borrar carpeta completa media/clientes/<codigo>/ de una sola vez
        import shutil
        from django.conf import settings
        carpeta = os.path.join(settings.MEDIA_ROOT, 'clientes', cliente.codigo or str(cliente.pk))
        if os.path.isdir(carpeta):
            shutil.rmtree(carpeta, ignore_errors=True)

        # Eliminar el cliente (cascade borra las relaciones en la BD)
        cliente.delete()
        return JsonResponse({'success': True})


# ── AJAX: Teléfonos ───────────────────────────────────────────────

class ClienteTelefonoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        accion = request.POST.get('_action', 'guardar')

        if accion == 'eliminar':
            tel_pk = request.POST.get('telefono_pk')
            tel = get_object_or_404(ClienteTelefono, pk=tel_pk, cliente__pk=pk)
            tel.delete()
            return JsonResponse({'success': True})

        cliente  = get_object_or_404(Cliente, pk=pk)
        tel_pk   = request.POST.get('telefono_pk')
        if tel_pk:
            tel  = get_object_or_404(ClienteTelefono, pk=tel_pk, cliente=cliente)
            form = FormularioClienteTelefono(request.POST, instance=tel)
        else:
            form = FormularioClienteTelefono(request.POST)

        if form.is_valid():
            tel = form.save(commit=False)
            tel.cliente = cliente
            tel.save()
            return JsonResponse({'success': True, 'telefono': _telefono_a_dict(tel)})

        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


# ── AJAX: Grupo familiar ──────────────────────────────────────────

class GrupoFamiliarAjax(LoginRequiredMixin, View):
    def get(self, request):
        """Lista de grupos para el selector en el formulario."""
        if not chequear_permiso(request.user, 'ver_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        q = request.GET.get('q', '').strip()
        qs = GrupoFamiliar.objects.all()
        if q:
            qs = qs.filter(
                Q(apellido_referencia__icontains=q) |
                Q(direccion_referencia__icontains=q)
            )
        return JsonResponse({
            'grupos': [
                {'id': g.pk, 'label': str(g), 'apellido': g.apellido_referencia}
                for g in qs[:20]
            ]
        })

    def post(self, request):
        """Crear un nuevo grupo familiar desde el formulario de cliente."""
        if not chequear_permiso(request.user, 'crear_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        form = FormularioGrupoFamiliar(request.POST)
        if form.is_valid():
            grupo = form.save()
            return JsonResponse({
                'success': True,
                'grupo': {'id': grupo.pk, 'label': str(grupo)}
            })
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


# ── AJAX: Imágenes ────────────────────────────────────────────────

class ClienteImagenAjax(LoginRequiredMixin, View):
    def get(self, request, pk):
        """Lista las imágenes existentes de un cliente (usado por el modal de edición)."""
        if not chequear_permiso(request.user, 'ver_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        cliente = get_object_or_404(Cliente, pk=pk)
        return JsonResponse({
            'imagenes': [
                {
                    'id':   img.pk,
                    'url':  img.imagen.url,
                    'tipo': img.get_tipo_display(),
                }
                for img in cliente.imagenes.all()
            ]
        })

    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        if request.POST.get('_action') == 'eliminar':
            imagen = get_object_or_404(ClienteImagen,
                pk=request.POST.get('imagen_pk'), cliente__pk=pk)
            if imagen.imagen and os.path.isfile(imagen.imagen.path):
                os.remove(imagen.imagen.path)
            imagen.delete()
            return JsonResponse({'success': True})

        cliente = get_object_or_404(Cliente, pk=pk)
        form    = FormularioClienteImagen(request.POST, request.FILES)
        if form.is_valid():
            imagen = form.save(commit=False)
            imagen.cliente = cliente
            imagen.save()
            return JsonResponse({
                'success': True,
                'imagen': {
                    'id': imagen.pk, 'url': imagen.imagen.url,
                    'tipo': imagen.get_tipo_display(),
                    'descripcion': imagen.descripcion, 'orden': imagen.orden,
                }
            })
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    def delete(self, request, pk):
        """Elimina una imagen individual. El JS manda el ID en el body JSON."""
        if not chequear_permiso(request.user, 'editar_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        try:
            body = json.loads(request.body)
            img_id = body.get('imagen_id')
        except Exception:
            img_id = None

        if not img_id:
            return JsonResponse({'error': 'imagen_id requerido'}, status=400)

        imagen = get_object_or_404(ClienteImagen, pk=img_id, cliente__pk=pk)
        if imagen.imagen and os.path.isfile(imagen.imagen.path):
            os.remove(imagen.imagen.path)
        imagen.delete()
        return JsonResponse({'success': True})


# ── AJAX: Contactos adicionales ───────────────────────────────────

class ClienteContactoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        if request.POST.get('_action') == 'eliminar':
            contacto = get_object_or_404(ClienteContactoAdicional,
                pk=request.POST.get('contacto_pk'), cliente__pk=pk)
            contacto.delete()
            return JsonResponse({'success': True})

        cliente     = get_object_or_404(Cliente, pk=pk)
        contacto_pk = request.POST.get('contacto_pk')
        if contacto_pk:
            contacto = get_object_or_404(ClienteContactoAdicional, pk=contacto_pk, cliente=cliente)
            form = FormularioContactoAdicional(request.POST, instance=contacto)
        else:
            form = FormularioContactoAdicional(request.POST)

        if form.is_valid():
            contacto = form.save(commit=False)
            contacto.cliente = cliente
            contacto.save()
            return JsonResponse({
                'success': True,
                'contacto': {
                    'id': contacto.pk, 'nombre': contacto.nombre,
                    'apellido': contacto.apellido, 'rol': contacto.get_rol_display(),
                    'telefono': contacto.telefono, 'whatsapp': contacto.whatsapp,
                    'email': contacto.email, 'notas': contacto.notas,
                }
            })
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


# ── AJAX: Búsqueda rápida ─────────────────────────────────────────

class ClienteBuscarAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_clientes'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        q = request.GET.get('q', '').strip()
        if len(q) < 2:
            return JsonResponse({'clientes': []})
        qs = Cliente.objects.filter(
            Q(nombre__icontains=q) | Q(apellido__icontains=q) |
            Q(razon_social__icontains=q) | Q(nombre_comercial__icontains=q) |
            Q(codigo__icontains=q)
        )[:15]
        return JsonResponse({
            'clientes': [
                {'id': c.pk, 'label': f"{c.get_nombre_display()} ({c.codigo})",
                 'tipo': c.tipo, 'estado': c.estado}
                for c in qs
            ]
        })
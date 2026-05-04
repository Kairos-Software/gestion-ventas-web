# core/views_usuarios.py
import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from .models import (
    Usuario, Rol,
    UsuarioEstudio, UsuarioExperienciaLaboral,
    UsuarioCapacitacion, UsuarioDocumento,
    UsuarioCuentaBancaria,
)
from .forms_usuarios import (
    FormularioCreacionUsuario, FormularioEdicionUsuario,
    FormularioEstudio, FormularioExperienciaLaboral,
    FormularioCapacitacion, FormularioDocumento,
)
from .permisos import chequear_permiso

# ══════════════════════════════════════════════════════════════════
#  LISTADO / GESTIÓN
# ══════════════════════════════════════════════════════════════════

class GestionUsuariosView(LoginRequiredMixin, View):
    def get(self, request):
        puede_ver = chequear_permiso(request.user, 'ver_usuarios')

        if puede_ver:
            qs = Usuario.objects.filter(is_superuser=False).order_by('username')
            if not request.user.is_superuser:
                qs = qs.exclude(pk=request.user.pk)
        else:
            qs = Usuario.objects.none()

        context = {
            'usuarios':                qs,
            'sin_permiso':             not puede_ver,
            'puede_crear':             chequear_permiso(request.user, 'crear_usuarios'),
            'puede_editar':            chequear_permiso(request.user, 'editar_usuarios'),
            'puede_eliminar':          chequear_permiso(request.user, 'eliminar_usuarios'),
            'puede_gestionar_permisos':chequear_permiso(request.user, 'gestionar_permisos'),
        }
        return render(request, 'core/gestion_usuarios.html', context)


# ══════════════════════════════════════════════════════════════════
#  CREAR / EDITAR (modal AJAX — completo con sub‑recursos)
# ══════════════════════════════════════════════════════════════════

class UsuarioCrearEditarAjax(LoginRequiredMixin, View):
    def get(self, request):
        """Devuelve los datos completos de un usuario (para editar)."""
        if not chequear_permiso(request.user, 'ver_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        pk = request.GET.get('get_pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido'}, status=400)

        usuario = get_object_or_404(
            Usuario.objects.prefetch_related('estudios', 'experiencias', 'capacitaciones', 'documentos', 'cuentas_bancarias'),
            pk=pk
        )

        # Serializar todos los campos del modelo Usuario
        data = {
            'id': usuario.pk,
            'username': usuario.username,
            'email': usuario.email or '',
            'first_name': usuario.first_name or '',
            'last_name': usuario.last_name or '',
            'dni': usuario.dni or '',
            'cuil': usuario.cuil or '',
            'fecha_nacimiento': usuario.fecha_nacimiento.strftime('%Y-%m-%d') if usuario.fecha_nacimiento else '',
            'genero': usuario.genero or '',
            'estado_civil': usuario.estado_civil or '',
            'tiene_hijos': usuario.tiene_hijos if usuario.tiene_hijos is not None else False,
            'cantidad_hijos': usuario.cantidad_hijos or 0,
            'nacionalidad': usuario.nacionalidad or '',
            'foto_url': usuario.foto_perfil.url if usuario.foto_perfil else '',
            'telefono_personal': usuario.telefono_personal or '',
            'telefono_alternativo': usuario.telefono_alternativo or '',
            'email_personal': usuario.email_personal or '',
            'calle': usuario.calle or '',
            'numero': usuario.numero or '',
            'piso_depto': usuario.piso_depto or '',
            'barrio': usuario.barrio or '',
            'localidad': usuario.localidad or '',
            'partido': usuario.partido or '',
            'provincia': usuario.provincia or '',
            'pais': usuario.pais or '',
            'codigo_postal': usuario.codigo_postal or '',
            'legajo': usuario.legajo or '',
            'puesto': usuario.puesto or '',
            'area': usuario.area or '',
            'sucursal': usuario.sucursal or '',
            'fecha_ingreso': usuario.fecha_ingreso.strftime('%Y-%m-%d') if usuario.fecha_ingreso else '',
            'fecha_egreso': usuario.fecha_egreso.strftime('%Y-%m-%d') if usuario.fecha_egreso else '',
            'estado_laboral': usuario.estado_laboral or '',
            'tipo_contrato': usuario.tipo_contrato or '',
            'modalidad_trabajo': usuario.modalidad_trabajo or '',
            'salario_bruto': str(usuario.salario_bruto) if usuario.salario_bruto else '',
            'banco': usuario.banco or '',
            'cbu': usuario.cbu or '',
            'alias_cbu': usuario.alias_cbu or '',
            'emergencia_nombre': usuario.emergencia_nombre or '',
            'emergencia_vinculo': usuario.emergencia_vinculo or '',
            'emergencia_telefono': usuario.emergencia_telefono or '',
            'grupo_sanguineo': usuario.grupo_sanguineo or '',
            'obra_social': usuario.obra_social or '',
            'nro_afiliado': usuario.nro_afiliado or '',
            'apto_psicofisico': usuario.apto_psicofisico if usuario.apto_psicofisico is not None else False,
            'fecha_apto': usuario.fecha_apto.strftime('%Y-%m-%d') if usuario.fecha_apto else '',
            'observaciones_salud': usuario.observaciones_salud or '',
            'notas_internas': usuario.notas_internas or '',
            'rol_nombre': usuario.rol.nombre if usuario.rol else '',
        }

        # Agregar sub‑recursos
        data.update({
            'estudios': [{
                'nivel': e.nivel,
                'titulo': e.titulo,
                'institucion': e.institucion,
                'estado': e.estado,
                'fecha_inicio': e.fecha_inicio.strftime('%Y-%m-%d') if e.fecha_inicio else '',
                'fecha_fin': e.fecha_fin.strftime('%Y-%m-%d') if e.fecha_fin else '',
                'promedio': str(e.promedio) if e.promedio else '',
                'observaciones': e.observaciones,
            } for e in usuario.estudios.all()],
            'experiencias': [{
                'empresa': e.empresa,
                'puesto': e.puesto,
                'area': e.area,
                'descripcion': e.descripcion,
                'fecha_inicio': e.fecha_inicio.strftime('%Y-%m-%d'),
                'fecha_fin': e.fecha_fin.strftime('%Y-%m-%d') if e.fecha_fin else '',
                'trabajo_actual': e.trabajo_actual,
                'motivo_egreso': e.motivo_egreso,
                'referencia_nombre': e.referencia_nombre,
                'referencia_contacto': e.referencia_contacto,
                'observaciones': e.observaciones,
            } for e in usuario.experiencias.all()],
            'capacitaciones': [{
                'nombre': c.nombre,
                'tipo': c.tipo,
                'modalidad': c.modalidad,
                'proveedor': c.proveedor,
                'fecha_inicio': c.fecha_inicio.strftime('%Y-%m-%d') if c.fecha_inicio else '',
                'fecha_fin': c.fecha_fin.strftime('%Y-%m-%d') if c.fecha_fin else '',
                'duracion_hs': str(c.duracion_hs) if c.duracion_hs else '',
                'resultado': c.resultado,
                'calificacion': str(c.calificacion) if c.calificacion else '',
                'nota_maxima': str(c.nota_maxima) if c.nota_maxima else '',
                'es_obligatoria': c.es_obligatoria,
                'certificado_emitido': c.certificado_emitido,
                'vencimiento_cert': c.vencimiento_cert.strftime('%Y-%m-%d') if c.vencimiento_cert else '',
                'observaciones': c.observaciones,
            } for c in usuario.capacitaciones.all()],
            'documentos': [{
                'tipo': d.tipo,
                'nombre': d.nombre,
                'fecha_doc': d.fecha_doc.strftime('%Y-%m-%d') if d.fecha_doc else '',
                'vencimiento': d.vencimiento.strftime('%Y-%m-%d') if d.vencimiento else '',
                'observaciones': d.observaciones,
                'archivo_url': d.archivo.url if d.archivo else '',
            } for d in usuario.documentos.all()],
            'cuentas_bancarias': [{
                'tipo':          cb.tipo,
                'nombre':        cb.nombre,
                'titular':       cb.titular,
                'cbu_cvu':       cb.cbu_cvu,
                'alias':         cb.alias,
                'nro_cuenta':    cb.nro_cuenta,
                'es_principal':  cb.es_principal,
                'observaciones': cb.observaciones,
            } for cb in usuario.cuentas_bancarias.all()],
        })
        return JsonResponse({'usuario': data})

    def post(self, request):
        pk = request.POST.get('pk')

        if pk:
            if not chequear_permiso(request.user, 'editar_usuarios'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            usuario = get_object_or_404(Usuario, pk=pk)
            form = FormularioEdicionUsuario(request.POST, request.FILES, instance=usuario)
        else:
            if not chequear_permiso(request.user, 'crear_usuarios'):
                return JsonResponse({'error': 'Sin permiso'}, status=403)
            form = FormularioCreacionUsuario(request.POST, request.FILES)

        if form.is_valid():
            usuario = form.save()
            _asignar_rol(usuario, request.POST.get('rol_nombre', ''))

            # Eliminar foto si se marcó
            if request.POST.get('foto_perfil_eliminar') == '1':
                if usuario.foto_perfil:
                    usuario.foto_perfil.delete(save=False)
                    usuario.foto_perfil = None
                    usuario.save()

            # Procesar sub‑recursos SOLO si se enviaron datos (evita pérdida accidental)
            if 'estudio_nivel[]' in request.POST:
                self._procesar_estudios(usuario, request.POST)
            if 'exp_empresa[]' in request.POST:
                self._procesar_experiencias(usuario, request.POST)
            if 'cap_nombre[]' in request.POST:
                self._procesar_capacitaciones(usuario, request.POST)
            if 'doc_tipo[]' in request.POST:
                self._procesar_documentos(usuario, request.POST, request.FILES)
            if 'cb_tipo[]' in request.POST:
                self._procesar_cuentas(usuario, request.POST)

            return JsonResponse({
                'success': True,
                'usuario': _serializar_usuario(usuario),
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)

    # ------------------------------------------------------------------
    #  Procesamiento de sub‑recursos (sin cambios)
    # ------------------------------------------------------------------
    def _procesar_estudios(self, usuario, post):
        usuario.estudios.all().delete()
        niveles = post.getlist('estudio_nivel[]')
        titulos = post.getlist('estudio_titulo[]')
        instituciones = post.getlist('estudio_institucion[]')
        estados = post.getlist('estudio_estado[]')
        fechas_inicio = post.getlist('estudio_fecha_inicio[]')
        fechas_fin = post.getlist('estudio_fecha_fin[]')
        promedios = post.getlist('estudio_promedio[]')
        observaciones = post.getlist('estudio_observaciones[]')

        for i in range(len(titulos)):
            if not titulos[i]:
                continue
            UsuarioEstudio.objects.create(
                usuario=usuario,
                nivel=niveles[i] if i < len(niveles) else 'otro',
                titulo=titulos[i],
                institucion=instituciones[i] if i < len(instituciones) else '',
                estado=estados[i] if i < len(estados) else 'completo',
                fecha_inicio=fechas_inicio[i] if i < len(fechas_inicio) and fechas_inicio[i] else None,
                fecha_fin=fechas_fin[i] if i < len(fechas_fin) and fechas_fin[i] else None,
                promedio=promedios[i] if i < len(promedios) and promedios[i] else None,
                observaciones=observaciones[i] if i < len(observaciones) else '',
            )

    def _procesar_experiencias(self, usuario, post):
        usuario.experiencias.all().delete()
        empresas = post.getlist('exp_empresa[]')
        puestos = post.getlist('exp_puesto[]')
        areas = post.getlist('exp_area[]')
        descripciones = post.getlist('exp_descripcion[]')
        fechas_inicio = post.getlist('exp_fecha_inicio[]')
        fechas_fin = post.getlist('exp_fecha_fin[]')
        trabajo_actual = post.getlist('exp_trabajo_actual[]')
        motivos = post.getlist('exp_motivo_egreso[]')
        ref_nombres = post.getlist('exp_referencia_nombre[]')
        ref_contactos = post.getlist('exp_referencia_contacto[]')
        observaciones = post.getlist('exp_observaciones[]')

        for i in range(len(empresas)):
            if not empresas[i] or not puestos[i] or not fechas_inicio[i]:
                continue
            UsuarioExperienciaLaboral.objects.create(
                usuario=usuario,
                empresa=empresas[i],
                puesto=puestos[i],
                area=areas[i] if i < len(areas) else '',
                descripcion=descripciones[i] if i < len(descripciones) else '',
                fecha_inicio=fechas_inicio[i],
                fecha_fin=fechas_fin[i] if i < len(fechas_fin) and fechas_fin[i] else None,
                trabajo_actual=(trabajo_actual[i] == '1') if i < len(trabajo_actual) else False,
                motivo_egreso=motivos[i] if i < len(motivos) else '',
                referencia_nombre=ref_nombres[i] if i < len(ref_nombres) else '',
                referencia_contacto=ref_contactos[i] if i < len(ref_contactos) else '',
                observaciones=observaciones[i] if i < len(observaciones) else '',
            )

    def _procesar_capacitaciones(self, usuario, post):
        usuario.capacitaciones.all().delete()
        nombres = post.getlist('cap_nombre[]')
        tipos = post.getlist('cap_tipo[]')
        modalidades = post.getlist('cap_modalidad[]')
        proveedores = post.getlist('cap_proveedor[]')
        fechas_inicio = post.getlist('cap_fecha_inicio[]')
        fechas_fin = post.getlist('cap_fecha_fin[]')
        duraciones = post.getlist('cap_duracion_hs[]')
        resultados = post.getlist('cap_resultado[]')
        calificaciones = post.getlist('cap_calificacion[]')
        notas_max = post.getlist('cap_nota_maxima[]')
        es_obligatoria = post.getlist('cap_es_obligatoria[]')
        cert_emitido = post.getlist('cap_certificado_emitido[]')
        venc_cert = post.getlist('cap_vencimiento_cert[]')
        observaciones = post.getlist('cap_observaciones[]')

        for i in range(len(nombres)):
            if not nombres[i] or not tipos[i]:
                continue
            UsuarioCapacitacion.objects.create(
                usuario=usuario,
                nombre=nombres[i],
                tipo=tipos[i],
                modalidad=modalidades[i] if i < len(modalidades) else '',
                proveedor=proveedores[i] if i < len(proveedores) else '',
                fecha_inicio=fechas_inicio[i] if i < len(fechas_inicio) and fechas_inicio[i] else None,
                fecha_fin=fechas_fin[i] if i < len(fechas_fin) and fechas_fin[i] else None,
                duracion_hs=duraciones[i] if i < len(duraciones) and duraciones[i] else None,
                resultado=resultados[i] if i < len(resultados) else 'pendiente',
                calificacion=calificaciones[i] if i < len(calificaciones) and calificaciones[i] else None,
                nota_maxima=notas_max[i] if i < len(notas_max) and notas_max[i] else None,
                es_obligatoria=(es_obligatoria[i] == '1') if i < len(es_obligatoria) else False,
                certificado_emitido=(cert_emitido[i] == '1') if i < len(cert_emitido) else False,
                vencimiento_cert=venc_cert[i] if i < len(venc_cert) and venc_cert[i] else None,
                observaciones=observaciones[i] if i < len(observaciones) else '',
            )

    def _procesar_documentos(self, usuario, post, files):
        usuario.documentos.all().delete()
        tipos         = post.getlist('doc_tipo[]')
        nombres       = post.getlist('doc_nombre[]')
        fechas_doc    = post.getlist('doc_fecha_doc[]')
        vencimientos  = post.getlist('doc_vencimiento[]')
        observaciones = post.getlist('doc_observaciones[]')
        archivos      = files.getlist('doc_archivo[]')

        for i in range(len(archivos)):
            if not archivos[i]:
                continue
            UsuarioDocumento.objects.create(
                usuario      = usuario,
                tipo         = tipos[i]         if i < len(tipos)         else 'otro',
                nombre       = nombres[i]        if i < len(nombres)       else archivos[i].name,
                archivo      = archivos[i],
                fecha_doc    = fechas_doc[i]     if i < len(fechas_doc)    and fechas_doc[i]    else None,
                vencimiento  = vencimientos[i]   if i < len(vencimientos)  and vencimientos[i]  else None,
                observaciones= observaciones[i]  if i < len(observaciones) else '',
            )

    def _procesar_cuentas(self, usuario, post):
        usuario.cuentas_bancarias.all().delete()
        tipos         = post.getlist('cb_tipo[]')
        nombres       = post.getlist('cb_nombre[]')
        titulares     = post.getlist('cb_titular[]')
        cbus          = post.getlist('cb_cbu_cvu[]')
        aliases       = post.getlist('cb_alias[]')
        nros          = post.getlist('cb_nro_cuenta[]')
        principales   = post.getlist('cb_es_principal[]')
        observaciones = post.getlist('cb_observaciones[]')

        for i in range(len(nombres)):
            if not nombres[i]:
                continue
            UsuarioCuentaBancaria.objects.create(
                usuario       = usuario,
                tipo          = tipos[i]        if i < len(tipos)         else 'banco',
                nombre        = nombres[i],
                titular       = titulares[i]    if i < len(titulares)     else '',
                cbu_cvu       = cbus[i]         if i < len(cbus)          else '',
                alias         = aliases[i]      if i < len(aliases)       else '',
                nro_cuenta    = nros[i]         if i < len(nros)          else '',
                es_principal  = (principales[i] == '1') if i < len(principales) else False,
                observaciones = observaciones[i] if i < len(observaciones) else '',
            )


# ══════════════════════════════════════════════════════════════════
#  ELIMINAR
# ══════════════════════════════════════════════════════════════════

class UsuarioEliminarAjax(LoginRequiredMixin, View):
    def delete(self, request):
        if not chequear_permiso(request.user, 'eliminar_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)
        pk = request.GET.get('pk')
        usuario = get_object_or_404(Usuario, pk=pk)
        usuario.delete()
        return JsonResponse({'success': True})


# ══════════════════════════════════════════════════════════════════
#  DETALLE DEL USUARIO
# ══════════════════════════════════════════════════════════════════

class DetalleUsuarioView(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not chequear_permiso(request.user, 'ver_usuarios'):
            return render(request, 'core/sin_permiso.html', status=403)

        usuario_obj = get_object_or_404(Usuario, pk=pk)

        context = {
            'usuario_obj':    usuario_obj,
            'estudios':       usuario_obj.estudios.all(),
            'experiencias':   usuario_obj.experiencias.all(),
            'capacitaciones': usuario_obj.capacitaciones.all(),
            'documentos':     usuario_obj.documentos.all(),
            'cuentas':        usuario_obj.cuentas_bancarias.all(),
            'puede_editar':   chequear_permiso(request.user, 'editar_usuarios'),
            'puede_eliminar': chequear_permiso(request.user, 'eliminar_usuarios'),
        }
        return render(request, 'core/detalle_usuario.html', context)


# ══════════════════════════════════════════════════════════════════
#  EDICIÓN COMPLETA (desde detalle)
# ══════════════════════════════════════════════════════════════════

class EditarUsuarioDetalleAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario = get_object_or_404(Usuario, pk=pk)
        form = FormularioEdicionUsuario(request.POST, request.FILES, instance=usuario)

        if form.is_valid():
            usuario = form.save()
            _asignar_rol(usuario, request.POST.get('rol_nombre', ''))
            return JsonResponse({'success': True, 'usuario': _serializar_usuario(usuario)})

        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


# ══════════════════════════════════════════════════════════════════
#  SUB‑RECURSOS (para el panel de detalle)
# ══════════════════════════════════════════════════════════════════

class UsuarioEstudioAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario = get_object_or_404(Usuario, pk=pk)
        accion  = request.POST.get('_action', 'crear')

        if accion == 'eliminar':
            estudio = get_object_or_404(UsuarioEstudio, pk=request.POST.get('estudio_pk'), usuario=usuario)
            estudio.delete()
            return JsonResponse({'success': True})

        estudio_pk = request.POST.get('estudio_pk')
        if estudio_pk:
            estudio = get_object_or_404(UsuarioEstudio, pk=estudio_pk, usuario=usuario)
            form = FormularioEstudio(request.POST, instance=estudio)
        else:
            form = FormularioEstudio(request.POST)

        if form.is_valid():
            obj = form.save(commit=False)
            obj.usuario = usuario
            obj.save()
            return JsonResponse({'success': True, 'estudio': {
                'id':           obj.pk,
                'nivel':        obj.get_nivel_display(),
                'titulo':       obj.titulo,
                'institucion':  obj.institucion,
                'estado':       obj.get_estado_display(),
                'fecha_fin':    obj.fecha_fin.strftime('%d/%m/%Y') if obj.fecha_fin else '',
                'promedio':     str(obj.promedio) if obj.promedio else '',
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class UsuarioExperienciaAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario = get_object_or_404(Usuario, pk=pk)
        accion  = request.POST.get('_action', 'crear')

        if accion == 'eliminar':
            exp = get_object_or_404(UsuarioExperienciaLaboral, pk=request.POST.get('exp_pk'), usuario=usuario)
            exp.delete()
            return JsonResponse({'success': True})

        exp_pk = request.POST.get('exp_pk')
        if exp_pk:
            exp  = get_object_or_404(UsuarioExperienciaLaboral, pk=exp_pk, usuario=usuario)
            form = FormularioExperienciaLaboral(request.POST, instance=exp)
        else:
            form = FormularioExperienciaLaboral(request.POST)

        if form.is_valid():
            obj = form.save(commit=False)
            obj.usuario = usuario
            obj.save()
            return JsonResponse({'success': True, 'experiencia': {
                'id':           obj.pk,
                'empresa':      obj.empresa,
                'puesto':       obj.puesto,
                'area':         obj.area,
                'fecha_inicio': obj.fecha_inicio.strftime('%d/%m/%Y'),
                'fecha_fin':    obj.fecha_fin.strftime('%d/%m/%Y') if obj.fecha_fin else 'Actualidad',
                'duracion':     obj.get_duracion(),
                'motivo_egreso':obj.get_motivo_egreso_display() if obj.motivo_egreso else '',
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class UsuarioCapacitacionAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario = get_object_or_404(Usuario, pk=pk)
        accion  = request.POST.get('_action', 'crear')

        if accion == 'eliminar':
            cap = get_object_or_404(UsuarioCapacitacion, pk=request.POST.get('cap_pk'), usuario=usuario)
            cap.delete()
            return JsonResponse({'success': True})

        cap_pk = request.POST.get('cap_pk')
        if cap_pk:
            cap  = get_object_or_404(UsuarioCapacitacion, pk=cap_pk, usuario=usuario)
            form = FormularioCapacitacion(request.POST, instance=cap)
        else:
            form = FormularioCapacitacion(request.POST)

        if form.is_valid():
            obj = form.save(commit=False)
            obj.usuario = usuario
            obj.save()
            return JsonResponse({'success': True, 'capacitacion': {
                'id':          obj.pk,
                'nombre':      obj.nombre,
                'tipo':        obj.get_tipo_display(),
                'resultado':   obj.get_resultado_display(),
                'calificacion':str(obj.calificacion) if obj.calificacion else '',
                'nota_maxima': str(obj.nota_maxima) if obj.nota_maxima else '',
                'fecha_fin':   obj.fecha_fin.strftime('%d/%m/%Y') if obj.fecha_fin else '',
                'es_obligatoria': obj.es_obligatoria,
                'certificado_emitido': obj.certificado_emitido,
                'vencimiento_cert': obj.vencimiento_cert.strftime('%d/%m/%Y') if obj.vencimiento_cert else '',
                'vigente':     obj.certificado_vigente(),
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class UsuarioDocumentoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario = get_object_or_404(Usuario, pk=pk)
        accion  = request.POST.get('_action', 'subir')

        if accion == 'eliminar':
            doc = get_object_or_404(UsuarioDocumento, pk=request.POST.get('doc_pk'), usuario=usuario)
            doc.archivo.delete(save=False)
            doc.delete()
            return JsonResponse({'success': True})

        form = FormularioDocumento(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.usuario = usuario
            obj.save()
            return JsonResponse({'success': True, 'documento': {
                'id':        obj.pk,
                'tipo':      obj.get_tipo_display(),
                'nombre':    obj.nombre,
                'url':       obj.archivo.url,
                'fecha_doc': obj.fecha_doc.strftime('%d/%m/%Y') if obj.fecha_doc else '',
                'vencimiento':obj.vencimiento.strftime('%d/%m/%Y') if obj.vencimiento else '',
                'vencido':   obj.vencido(),
                'proximo':   obj.proxima_a_vencer(),
            }})
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class UsuarioFotoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'editar_usuarios'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario = get_object_or_404(Usuario, pk=pk)
        accion  = request.POST.get('_action', 'subir')

        if accion == 'eliminar':
            if usuario.foto_perfil:
                usuario.foto_perfil.delete(save=False)
                usuario.foto_perfil = None
                usuario.save()
            return JsonResponse({'success': True, 'foto_url': ''})

        if 'foto_perfil' not in request.FILES:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

        # Borrar foto anterior si existe
        if usuario.foto_perfil:
            usuario.foto_perfil.delete(save=False)

        usuario.foto_perfil = request.FILES['foto_perfil']
        usuario.save()
        return JsonResponse({'success': True, 'foto_url': usuario.foto_perfil.url})


# ══════════════════════════════════════════════════════════════════
#  FUNCIONES AUXILIARES
# ══════════════════════════════════════════════════════════════════

def _asignar_rol(usuario, rol_nombre):
    rol_nombre = (rol_nombre or '').strip()
    if rol_nombre:
        rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
        usuario.rol = rol
    else:
        usuario.rol = None
    usuario.save()


def _serializar_usuario(u):
    return {
        'id':           u.pk,
        'username':     u.username,
        'first_name':   u.first_name or '',
        'last_name':    u.last_name or '',
        'email':        u.email or '',
        'dni':          u.dni or '',
        'puesto':       u.puesto or '',
        'area':         u.area or '',
        'estado_laboral': u.get_estado_laboral_display() if u.estado_laboral else '',
        'foto_url':     u.foto_perfil.url if u.foto_perfil else '',
        'rol_nombre':   u.rol.nombre if u.rol else '',
    }
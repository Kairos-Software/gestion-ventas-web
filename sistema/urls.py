from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # El catálogo público es ahora la portada del sitio (''). Va antes que
    # core.urls a propósito: core ya no define nada en '' (el login se movió
    # a 'login/'), así que no hay colisión de rutas.
    path('', include('catalogo.urls', namespace='catalogo')),
    path('', include('core.urls')),
    path('productos/', include('productos.urls', namespace='productos')),  # ← esto
    path('compras/', include('compras.urls', namespace='compras')),  # ← esto
    path('ventas/', include('ventas.urls', namespace='ventas')),  # ← esto
    path('presupuestos/', include('presupuestos.urls', namespace='presupuestos')),
    path('caja/', include('caja.urls', namespace='caja')),
    path('asistencia/', include('asistencia.urls', namespace='asistencia')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
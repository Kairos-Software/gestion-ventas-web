from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('productos/', include('productos.urls', namespace='productos')),  # ← esto
    path('compras/', include('compras.urls', namespace='compras')),  # ← esto
    path('ventas/', include('ventas.urls', namespace='ventas')),  # ← esto
    path('caja/', include('caja.urls', namespace='caja')),
    path('asistencia/', include('asistencia.urls', namespace='asistencia')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
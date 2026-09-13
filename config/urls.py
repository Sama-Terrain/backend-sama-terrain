"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from reservations.views import GerantReservationsView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Chaque app a ses propres routes, regroupées sous /api/auth/, /api/terrains/, etc.
    path('api/auth/', include('authentification.urls')),
    path('api/terrains/', include('terrains.urls')),
    path('api/creneaux/', include('creneaux.urls')),
    path('api/reservations/', include('reservations.urls')),
    path('api/gerant/reservations/', GerantReservationsView.as_view(), name='gerant-reservations'),
    path('api/paiements/', include('paiements.urls')),
    path('api/tickets/', include('tickets.urls')),
    path('api/avis/', include('avis.urls')),
    path('api/gerant/', include('gerant.urls')),
    path('api/ia/', include('gerant.ia_urls')),
    path('api/admin/', include('admin_panel.urls')),
]

# En développement, Django sert lui-même les fichiers uploadés (photos...).
# En production, ce sera le rôle du serveur web (nginx, etc.).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

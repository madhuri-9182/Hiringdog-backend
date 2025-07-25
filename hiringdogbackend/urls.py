"""
URL configuration for hiringdogbackend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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

from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from core.views import custom_404
from django.conf.urls import handler404

handler404 = custom_404

urlpatterns = (
    [
        path("hiringdog/admin/", admin.site.urls),
        path("api/", include("core.urls")),
        path("api/", include("dashboard.urls")),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
)


if settings.DEBUG:
    from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView
    import debug_toolbar

    urlpatterns += [
        path(
            "",
            SpectacularRedocView.as_view(url_name="schema"),
            name="api-documentation",
        ),
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("__debug__/", include(debug_toolbar.urls)),
    ]

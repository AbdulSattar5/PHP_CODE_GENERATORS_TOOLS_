# gencode_project/urls.py (Update)

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from api.views import (
    home_view, login_view, register_view, logout_view,
    dashboard_view, projects_view, code_generation_view,
    codebase_upload_view, standards_upload_view,
    database_connections_view,
    settings_view, profile_view
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # ✅ FIX #7: Favicon redirect to prevent 404 errors
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
    
    # Authentication
    path('', home_view, name='home'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    
    # Main pages
    path('dashboard/', dashboard_view, name='dashboard'),
    path('projects/', projects_view, name='projects'),
    path('generate/', code_generation_view, name='code_generation'),
    path('codebase/', codebase_upload_view, name='codebase_upload'),
    path('standards/', standards_upload_view, name='standards_upload'),
    path('database-connections/', database_connections_view, name='database_connections'),
    path('settings/', settings_view, name='settings'),
    path('profile/', profile_view, name='profile'),
    
    # API endpoints
    path('api/', include('api.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

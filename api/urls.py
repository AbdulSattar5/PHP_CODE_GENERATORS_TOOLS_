"""
URL configuration for GenCode AI API
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProjectViewSet,
    CodeGenerationViewSet,
    CompanyCodebaseViewSet,
    CompanyStandardsViewSet,
    DatabaseConnectionViewSet
)

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'codebases', CompanyCodebaseViewSet, basename='codebase')
router.register(r'standards', CompanyStandardsViewSet, basename='standards')
router.register(r'database-connections', DatabaseConnectionViewSet, basename='database-connection')

urlpatterns = [
    # Router URLs (includes all detail actions like indexing_status)
    path('', include(router.urls)),
    
    # Code generation endpoints
    path('generate/', CodeGenerationViewSet.as_view({'post': 'generate'}), name='generate-code'),
    
    # Upload endpoints (explicit paths to avoid router conflicts)
    path('codebases/upload/', CompanyCodebaseViewSet.as_view({'post': 'upload'}), name='upload-codebase'),
    path('standards/upload/', CompanyStandardsViewSet.as_view({'post': 'upload'}), name='upload-standards'),
    
    # Authentication
    path('auth/', include('rest_framework.urls')),
]
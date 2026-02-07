from django.contrib import admin
from django.urls import path

from django.conf import settings
from django.conf.urls.static import static

from core import views
from tenant import views as tenant_views
from xero import views as xero_views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', views.index, name='index'),

    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('home/', views.home, name='home'),
    
    # Legal Entities
    path('legal-entities/', tenant_views.legal_entities_list, name='legal_entities_list'),
    path('legal-entities/create/', tenant_views.legal_entity_create, name='legal_entity_create'),
    
    # Xero Data Import
    path('import/start/', xero_views.start_import, name='start_import'),
    path('import/<int:legal_entity_id>/<int:dataset_type_id>/upload/', xero_views.import_upload, name='import_upload'),
    path('import/<int:import_id>/', xero_views.import_detail, name='import_detail'),
    path('import/history/', xero_views.import_history, name='import_history'),
]

# Serve static + media files during development (DEBUG = True)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
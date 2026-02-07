from django.contrib import admin
from django.urls import path

from django.conf import settings
from django.conf.urls.static import static

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', views.index, name='index'),

    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('home/', views.home, name='home'), 

    
]

# Serve static + media files during development (DEBUG = True)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
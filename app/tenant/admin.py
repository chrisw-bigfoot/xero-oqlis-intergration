from django.contrib import admin
from .models import Tenant, LegalEntity


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant')
    search_fields = ('name',)
    list_filter = ('tenant',)

from django.contrib import admin
from .models import DatasetType, XeroDataImport


@admin.register(DatasetType)
class DatasetTypeAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'name')
    search_fields = ('display_name', 'name')


@admin.register(XeroDataImport)
class XeroDataImportAdmin(admin.ModelAdmin):
    list_display = ('legal_entity', 'dataset_type', 'status', 'created_at', 'rows_processed')
    list_filter = ('status', 'dataset_type', 'created_at', 'legal_entity__tenant')
    search_fields = ('legal_entity__name', 'file_name', 'created_by__email')
    readonly_fields = ('created_at', 'processed_at', 'created_by')
    
    fieldsets = (
        ('Import Information', {
            'fields': ('legal_entity', 'dataset_type', 'file', 'file_name')
        }),
        ('Status & Results', {
            'fields': ('status', 'rows_processed', 'error_message')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new import
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

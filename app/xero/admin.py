from django.contrib import admin
from .models import DatasetType, XeroDataImport, FinancialReport


@admin.register(DatasetType)
class DatasetTypeAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'name', 'description_preview')
    list_filter = ('name',)
    search_fields = ('display_name', 'name', 'description')
    ordering = ('display_name',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'display_name')
        }),
        ('Details', {
            'fields': ('description',),
            'classes': ('wide',)
        }),
    )
    
    def description_preview(self, obj):
        """Show first 50 characters of description in list view"""
        if obj.description:
            return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
        return '—'
    description_preview.short_description = 'Description'


@admin.register(FinancialReport)
class FinancialReportAdmin(admin.ModelAdmin):
    list_display = ('report_id', 'legal_entity', 'status', 'created_at', 'data_imports_count', 'total_rows_processed')
    list_filter = ('status', 'created_at', 'legal_entity__tenant')
    search_fields = ('report_id', 'legal_entity__name', 'created_by__email')
    readonly_fields = ('report_id', 'created_at', 'completed_at')
    
    fieldsets = (
        ('Report Information', {
            'fields': ('report_id', 'legal_entity', 'report_month')
        }),
        ('Status & Metadata', {
            'fields': ('status', 'total_rows_processed', 'error_message')
        }),
        ('Tracking', {
            'fields': ('created_by', 'created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def data_imports_count(self, obj):
        """Display the count of associated data imports"""
        return obj.data_imports.count()
    data_imports_count.short_description = 'Files'


@admin.register(XeroDataImport)
class XeroDataImportAdmin(admin.ModelAdmin):
    list_display = ('legal_entity', 'tenant_name', 'dataset_type', 'report_id', 'status', 'created_at', 'rows_processed')
    list_filter = ('status', 'dataset_type', 'created_at', 'legal_entity__tenant', 'financial_report')
    search_fields = ('legal_entity__name', 'tenant_name', 'file_name', 'created_by__email', 'report_id')
    readonly_fields = ('created_at', 'processed_at', 'created_by', 'report_id', 'tenant_name')
    
    fieldsets = (
        ('Report Relationship', {
            'fields': ('financial_report', 'report_id')
        }),
        ('Import Information', {
            'fields': ('tenant_name', 'legal_entity', 'dataset_type', 'file', 'file_name')
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

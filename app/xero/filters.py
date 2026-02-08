import django_filters
from django import forms
from django.db.models import Q
from .models import XeroDataImport, LegalEntity, DatasetType


class XeroDataImportFilter(django_filters.FilterSet):
    """Filter for XeroDataImport records"""
    
    legal_entity = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        label="Legal Entity",
        empty_label="All Legal Entities",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = django_filters.ChoiceFilter(
        choices=[
            ('', 'All Statuses'),
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        label="Status",
        empty_label=None,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    dataset_type = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        label="Dataset Type",
        empty_label="All Dataset Types",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = XeroDataImport
        fields = ['legal_entity', 'dataset_type', 'status']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically set querysets to only show relevant choices from the current queryset
        if self.queryset is not None:
            legal_entity_ids = self.queryset.values_list('legal_entity_id', flat=True).distinct()
            self.filters['legal_entity'].extra['queryset'] = LegalEntity.objects.filter(id__in=legal_entity_ids)
            
            dataset_type_ids = self.queryset.values_list('dataset_type_id', flat=True).distinct()
            self.filters['dataset_type'].extra['queryset'] = DatasetType.objects.filter(id__in=dataset_type_ids)

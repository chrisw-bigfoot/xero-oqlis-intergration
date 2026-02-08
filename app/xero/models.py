from django.db import models
from django.contrib.auth import get_user_model
from tenant.models import LegalEntity

User = get_user_model()


class DatasetType(models.Model):
    """Available dataset types for Xero data imports"""
    
    name = models.CharField(max_length=50, unique=True, help_text="Internal identifier (lowercase, no spaces)")
    display_name = models.CharField(max_length=100, help_text="User-friendly display name")
    description = models.TextField(blank=True)

    def __str__(self):
        return self.display_name

    class Meta:
        verbose_name = "Dataset Type"
        verbose_name_plural = "Dataset Types"
        ordering = ['display_name']


class XeroDataImport(models.Model):
    """Track Xero data imports for each legal entity"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    legal_entity = models.ForeignKey(
        LegalEntity, 
        on_delete=models.CASCADE, 
        related_name="xero_imports"
    )
    dataset_type = models.ForeignKey(
        DatasetType,
        on_delete=models.PROTECT
    )
    
    # File upload
    file = models.FileField(upload_to="xero_imports/%Y/%m/%d/")
    file_name = models.CharField(max_length=255, blank=True)
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # User and timestamps
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="xero_imports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(blank=True)
    rows_processed = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.legal_entity} - {self.dataset_type} ({self.created_at.strftime('%Y-%m-%d')})"

    class Meta:
        verbose_name = "Xero Data Import"
        verbose_name_plural = "Xero Data Imports"
        ordering = ['-created_at']

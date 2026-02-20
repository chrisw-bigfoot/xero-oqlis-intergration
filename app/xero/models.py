from django.db import models
from django.contrib.auth import get_user_model
from tenant.models import LegalEntity
from uuid import uuid4

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


class FinancialReport(models.Model):
    """Container for a complete financial report consisting of multiple report types"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    report_id = models.CharField(
        max_length=100, 
        unique=True, 
        editable=False,
        help_text="Unique identifier for this financial report batch"
    )
    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.CASCADE,
        related_name="financial_reports"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="financial_reports"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    report_month = models.CharField(max_length=20, blank=True, help_text="Financial report month/period")
    total_rows_processed = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"{self.legal_entity} - {self.report_id}"

    def save(self, *args, **kwargs):
        """Generate report_id if not set"""
        if not self.report_id:
            self.report_id = f"{self.created_at.strftime('%B%Y')}-{str(uuid4()).split('-')[-1]}" if self.created_at else f"report-{uuid4()}"
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Financial Report"
        verbose_name_plural = "Financial Reports"
        ordering = ['-created_at']


class XeroDataImport(models.Model):
    """Track individual Xero data report uploads attached to a FinancialReport"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    financial_report = models.ForeignKey(
        FinancialReport,
        on_delete=models.CASCADE,
        related_name="data_imports",
        null=True,
        blank=True,
        help_text="Parent financial report this import belongs to"
    )
    legal_entity = models.ForeignKey(
        LegalEntity, 
        on_delete=models.CASCADE, 
        related_name="xero_imports"
    )
    dataset_type = models.ForeignKey(
        DatasetType,
        on_delete=models.PROTECT
    )
    
    # Report identification
    report_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Unique identifier linking to parent FinancialReport"
    )
    
    # File upload
    file = models.FileField(upload_to="xero_imports/%Y/%m/%d/")
    file_name = models.CharField(max_length=255, blank=True)
    tenant_name = models.CharField(max_length=255, blank=True, help_text="Name of the tenant/legal entity at time of import")
    
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
    
    # Processed data (JSON or DataFrame pickle)
    processed_data = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.legal_entity} - {self.dataset_type} ({self.created_at.strftime('%Y-%m-%d')})"

    class Meta:
        verbose_name = "Xero Data Import"
        verbose_name_plural = "Xero Data Imports"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_id']),
            models.Index(fields=['financial_report']),
        ]

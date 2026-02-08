from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.utils import timezone
import tempfile
import os
import traceback
from tenant.models import LegalEntity
from .models import DatasetType, XeroDataImport
from .filters import XeroDataImportFilter
from .datasets.budget_summary import transform_budget_summary
from .datasets.management_report import process_management_report


@login_required
def start_import(request):
    """Start a new import - select legal entity and dataset type"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    # Get legal entities for this tenant
    legal_entities = LegalEntity.objects.filter(tenant=request.user.tenant).order_by('name')
    dataset_types = DatasetType.objects.all().order_by('display_name')
    
    if request.method == 'POST':
        legal_entity_id = request.POST.get('legal_entity')
        dataset_type_id = request.POST.get('dataset_type')
        
        # Validate selections
        if not legal_entity_id:
            messages.error(request, "Please select a legal entity.")
            return render(request, 'xero/start_import.html', {
                'legal_entities': legal_entities,
                'dataset_types': dataset_types,
            })
        
        if not dataset_type_id:
            messages.error(request, "Please select a dataset type.")
            return render(request, 'xero/start_import.html', {
                'legal_entities': legal_entities,
                'dataset_types': dataset_types,
            })
        
        # Verify the user has access to this legal entity
        legal_entity = get_object_or_404(LegalEntity, id=legal_entity_id)
        if legal_entity.tenant_id != request.user.tenant_id:
            return HttpResponseForbidden("You don't have access to this legal entity.")
        
        dataset_type = get_object_or_404(DatasetType, id=dataset_type_id)
        
        # Redirect to file upload view
        return redirect('import_upload', legal_entity_id=legal_entity_id, dataset_type_id=dataset_type_id)
    
    context = {
        'legal_entities': legal_entities,
        'dataset_types': dataset_types,
    }
    return render(request, 'xero/start_import.html', context)


@login_required
def import_upload(request, legal_entity_id, dataset_type_id):
    """Upload file for data import"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    # Verify access to legal entity
    legal_entity = get_object_or_404(LegalEntity, id=legal_entity_id)
    if legal_entity.tenant_id != request.user.tenant_id:
        return HttpResponseForbidden("You don't have access to this legal entity.")
    
    dataset_type = get_object_or_404(DatasetType, id=dataset_type_id)
    
    if request.method == 'POST':
        file = request.FILES.get('file')
        
        if not file:
            messages.error(request, "Please select a file to upload.")
            return render(request, 'xero/import_upload.html', {
                'legal_entity': legal_entity,
                'dataset_type': dataset_type,
            })
        
        # Validate file extension (basic check for CSV/XLSX)
        allowed_extensions = ['csv', 'xlsx', 'xls']
        file_ext = file.name.split('.')[-1].lower()
        
        if file_ext not in allowed_extensions:
            messages.error(request, f"Please upload a file in one of these formats: {', '.join(allowed_extensions).upper()}")
            return render(request, 'xero/import_upload.html', {
                'legal_entity': legal_entity,
                'dataset_type': dataset_type,
            })
        
        # Create the import record
        import_record = XeroDataImport.objects.create(
            legal_entity=legal_entity,
            dataset_type=dataset_type,
            file=file,
            file_name=file.name,
            created_by=request.user,
            status='processing'
        )
        
        try:
            # Save file to temporary location for processing
            tmp_path = None
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                # Read file content and write to temp file
                for chunk in file.chunks():
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name
            
            # Process based on dataset type
            dataset_name = dataset_type.name.lower()
            
            print(f"\n{'='*60}")
            print(f"Processing {dataset_type.display_name} import for {legal_entity.name}")
            print(f"{'='*60}\n")
            
            if dataset_name == 'budget_summary':
                # Process budget summary
                df = transform_budget_summary(
                    file_path=tmp_path,
                    legal_entity=legal_entity.id
                )
                print(f"\nBudget Summary - First rows:")
                print(df.head(10))
                print(f"\nShape: {df.shape}")
                print(f"Columns: {df.columns.tolist()}\n")
                import_record.rows_processed = len(df)
                
            elif dataset_name == 'management_reports':
                # Process management reports
                result_dfs = process_management_report(
                    file_path=tmp_path,
                    legal_entity=legal_entity.id
                )
                print(f"\nManagement Reports Results:")
                total_rows = 0
                for report_name, df in result_dfs.items():
                    if df is not None:
                        print(f"\n{report_name.upper()}")
                        print(f"  Shape: {df.shape}")
                        print(f"  Columns: {df.columns.tolist()}")
                        print(f"  First rows:")
                        print(df.head(5))
                        total_rows += len(df)
                    else:
                        print(f"\n{report_name.upper()}: Failed to process")
                
                import_record.rows_processed = total_rows
                
            else:
                raise ValueError(f"Unknown dataset type: {dataset_name}")
            
            # Update import record status to completed
            import_record.status = 'completed'
            import_record.processed_at = timezone.now()
            import_record.save()
            
            messages.success(request, f"File processed successfully! {import_record.rows_processed} rows imported.")
            
            # Delete the uploaded file for data privacy/compliance
            if import_record.file:
                import_record.file.delete(save=False)
            
        except Exception as e:
            # Update import record with error
            import_record.status = 'failed'
            import_record.error_message = str(e)
            import_record.processed_at = timezone.now()
            import_record.save()
            
            print(f"\nERROR processing import: {str(e)}")
            traceback.print_exc()
            
            messages.error(request, f"Error processing file: {str(e)}")
            
            # Delete the uploaded file for data privacy/compliance
            if import_record.file:
                import_record.file.delete(save=False)
            
            return render(request, 'xero/import_upload.html', {
                'legal_entity': legal_entity,
                'dataset_type': dataset_type,
            })
            
        finally:
            # Clean up temporary file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except PermissionError:
                    # File might still be locked by openpyxl/pandas on Windows
                    # Let the OS clean it up from temp directory
                    print(f"Warning: Could not delete temp file {tmp_path}, will be cleaned by OS")
        
        return redirect('import_detail', import_id=import_record.id)
    
    context = {
        'legal_entity': legal_entity,
        'dataset_type': dataset_type,
    }
    return render(request, 'xero/import_upload.html', context)


@login_required
def import_detail(request, import_id):
    """View import details and status"""
    import_record = get_object_or_404(XeroDataImport, id=import_id)
    
    # Verify user has access to this import
    if import_record.legal_entity.tenant_id != request.user.tenant_id:
        return HttpResponseForbidden("You don't have access to this import.")
    
    context = {
        'import': import_record,
    }
    return render(request, 'xero/import_detail.html', context)


@login_required
def import_history(request):
    """View import history for the user's tenant"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    # Get all imports for this tenant's legal entities
    imports = XeroDataImport.objects.filter(
        legal_entity__tenant=request.user.tenant
    ).select_related('legal_entity', 'dataset_type', 'created_by').order_by('-created_at')
    
    # Apply filters
    import_filter = XeroDataImportFilter(request.GET, queryset=imports)
    filtered_imports = import_filter.qs
    
    # Calculate metrics on filtered results
    total_imports = filtered_imports.count()
    completed_imports = filtered_imports.filter(status='completed').count()
    failed_imports = filtered_imports.filter(status='failed').count()
    
    # Calculate failure rate percentage
    if total_imports > 0:
        failure_rate = round((failed_imports / total_imports) * 100)
    else:
        failure_rate = 0
    
    context = {
        'imports': filtered_imports,
        'filter': import_filter,
        'total_imports': total_imports,
        'completed_imports': completed_imports,
        'failed_imports': failed_imports,
        'failure_rate': failure_rate,
    }
    return render(request, 'xero/import_history.html', context)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.contrib import messages
from tenant.models import LegalEntity
from .models import DatasetType, XeroDataImport


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
            status='pending'
        )
        
        messages.success(request, f"File uploaded successfully. Processing {dataset_type.display_name} import...")
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
    
    context = {
        'imports': imports,
    }
    return render(request, 'xero/import_history.html', context)

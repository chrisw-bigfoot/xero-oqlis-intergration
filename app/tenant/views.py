from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import LegalEntity


@login_required
def legal_entities_list(request):
    """List all legal entities for the user's tenant"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    legal_entities = LegalEntity.objects.filter(tenant=request.user.tenant).order_by('name')
    
    context = {
        'legal_entities': legal_entities,
        'tenant': request.user.tenant,
    }
    return render(request, 'tenant/legal_entities_list.html', context)


@login_required
def legal_entity_create(request):
    """Create a new legal entity for the user's tenant"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        
        if not name:
            messages.error(request, "Legal entity name is required.")
            return redirect('legal_entities_list')
        
        # Check for duplicates
        if LegalEntity.objects.filter(tenant=request.user.tenant, name__iexact=name).exists():
            messages.error(request, "A legal entity with this name already exists in your tenant.")
            return redirect('legal_entities_list')
        
        # Create the legal entity
        legal_entity = LegalEntity.objects.create(
            name=name,
            tenant=request.user.tenant
        )
        
        messages.success(request, f"Legal entity '{legal_entity.name}' created successfully.")
        return redirect('legal_entities_list')
    
    context = {
        'tenant': request.user.tenant,
    }
    return render(request, 'tenant/legal_entity_form.html', context)

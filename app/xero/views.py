from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.utils import timezone
import tempfile
import os
import traceback
import json
from datetime import datetime
from uuid import uuid4
from tenant.models import LegalEntity
from .models import DatasetType, XeroDataImport, FinancialReport
from .filters import XeroDataImportFilter
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from financial_report import (
    transform_balance_sheet,
    transform_budget_summary,
    transform_budget_variance,
    transform_profit_loss,
    transform_profit_loss_ly
)


@login_required
def start_import(request):
    """Create financial report - select entity and upload report files"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    # Get legal entities and dataset types for this tenant
    legal_entities = LegalEntity.objects.filter(tenant=request.user.tenant).order_by('name')
    dataset_types = DatasetType.objects.all().order_by('display_name')
    
    if request.method == 'POST':
        legal_entity_id = request.POST.get('legal_entity')
        
        # Validate legal entity selection
        if not legal_entity_id:
            messages.error(request, "Please select a legal entity.")
            return render(request, 'xero/start_import.html', {
                'legal_entities': legal_entities,
                'dataset_types': dataset_types,
            })
        
        # Verify the user has access to this legal entity
        legal_entity = get_object_or_404(LegalEntity, id=legal_entity_id)
        if legal_entity.tenant_id != request.user.tenant_id:
            return HttpResponseForbidden("You don't have access to this legal entity.")
        
        # Check if at least one file was uploaded
        has_files = any(request.FILES.get(f'file_{dtype.id}') for dtype in dataset_types)
        
        if not has_files:
            messages.error(request, "Please upload at least one report file.")
            return render(request, 'xero/start_import.html', {
                'legal_entities': legal_entities,
                'dataset_types': dataset_types,
                'selected_entity_id': int(legal_entity_id),
            })
        
        # Create the financial report
        report_date = datetime.now()
        report_id = f"{report_date.strftime('%B%Y')}-{str(uuid4()).split('-')[-1]}"
        
        financial_report = FinancialReport.objects.create(
            report_id=report_id,
            legal_entity=legal_entity,
            created_by=request.user,
            status='processing',
            report_month=report_date.strftime("%B %Y")
        )
        
        # Track import records for error handling
        import_records = []
        all_succeeded = True
        total_rows_processed = 0
        
        # Process each file upload
        for dataset_type in dataset_types:
            file_key = f'file_{dataset_type.id}'
            file = request.FILES.get(file_key)
            
            if not file:
                # File is optional
                continue
            
            # Validate file extension
            allowed_extensions = ['csv', 'xlsx', 'xls']
            file_ext = file.name.split('.')[-1].lower()
            
            if file_ext not in allowed_extensions:
                messages.warning(request, f"{dataset_type.display_name}: File format not supported. Skipped.")
                continue
            
            # Create import record
            import_record = XeroDataImport.objects.create(
                financial_report=financial_report,
                legal_entity=legal_entity,
                dataset_type=dataset_type,
                report_id=report_id,
                file=file,
                file_name=file.name,
                tenant_name=legal_entity.tenant.name,
                created_by=request.user,
                status='processing'
            )
            import_records.append((dataset_type, import_record))
            
            try:
                # Save file to temporary location
                tmp_path = None
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                    for chunk in file.chunks():
                        tmp_file.write(chunk)
                    tmp_path = tmp_file.name
                
                print(f"\n{'='*60}")
                print(f"Processing {dataset_type.display_name} for {legal_entity.name}")
                print(f"Report ID: {report_id}")
                print(f"{'='*60}\n")
                
                # Transform based on dataset type
                df = None
                dataset_name = dataset_type.name.lower()
                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                try:
                    if dataset_name == 'balance_sheet':
                        df = transform_balance_sheet(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name == 'budget_summary':
                        df = transform_budget_summary(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name == 'budget_variance':
                        df = transform_budget_variance(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name == 'profit_and_loss':
                        df = transform_profit_loss(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name in ('profit_and_loss_vs_py', 'profit_and_loss_vs_ly'):
                        df = transform_profit_loss_ly(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    else:
                        raise ValueError(f"Unknown dataset type: {dataset_name}")
                    
                    if df is not None:
                        # Update import record with success info
                        rows_processed = len(df)
                        import_record.rows_processed = rows_processed
                        import_record.status = 'completed'
                        import_record.processed_at = timezone.now()
                        import_record.save()
                        
                        total_rows_processed += rows_processed
                        
                        print(f"\n✓ {dataset_type.display_name} - {rows_processed} rows processed")
                        print(f"Columns: {df.columns.tolist()}")
                    else:
                        raise ValueError("Data transformation returned None")
                        
                except Exception as e:
                    # Update import record with error
                    import_record.status = 'failed'
                    import_record.error_message = str(e)
                    import_record.processed_at = timezone.now()
                    import_record.save()
                    
                    all_succeeded = False
                    print(f"\n✗ Error processing {dataset_type.display_name}: {str(e)}")
                    traceback.print_exc()
                    
            except Exception as e:
                # Update import record with error
                import_record.status = 'failed'
                import_record.error_message = str(e)
                import_record.processed_at = timezone.now()
                import_record.save()
                
                all_succeeded = False
                print(f"\n✗ Error with {dataset_type.display_name}: {str(e)}")
                traceback.print_exc()
                
            finally:
                # Clean up temporary file
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except PermissionError:
                        print(f"Warning: Could not delete temp file {tmp_path}")
                
                # Delete uploaded file for data privacy
                if import_record.file:
                    import_record.file.delete(save=False)
        
        # Update financial report status
        financial_report.total_rows_processed = total_rows_processed
        if all_succeeded:
            financial_report.status = 'completed'
            financial_report.completed_at = timezone.now()
            messages.success(request, f"Financial report processed successfully! {total_rows_processed} total rows processed across {len(import_records)} reports.")
        else:
            financial_report.status = 'failed'
            financial_report.completed_at = timezone.now()
            messages.error(request, "One or more reports encountered errors. See details below.")
        
        financial_report.save()
        
        return redirect('import_detail', import_id=financial_report.id)
    
    context = {
        'legal_entities': legal_entities,
        'dataset_types': dataset_types,
    }
    return render(request, 'xero/start_import.html', context)


@login_required
def import_upload_multiple(request, legal_entity_id, dataset_type_ids):
    """Upload files for multiple report types in a single financial report"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    # Verify access to legal entity
    legal_entity = get_object_or_404(LegalEntity, id=legal_entity_id)
    if legal_entity.tenant_id != request.user.tenant_id:
        return HttpResponseForbidden("You don't have access to this legal entity.")
    
    # Parse dataset type IDs
    try:
        dataset_type_id_list = [int(id) for id in dataset_type_ids.split(',')]
    except (ValueError, AttributeError):
        messages.error(request, "Invalid dataset types specified.")
        return redirect('start_import')
    
    # Get selected dataset types
    selected_types = DatasetType.objects.filter(id__in=dataset_type_id_list).order_by('display_name')
    
    if not selected_types.exists():
        messages.error(request, "No valid dataset types selected.")
        return redirect('start_import')
    
    if request.method == 'POST':
        # Create the financial report
        report_date = datetime.now()
        report_id = f"{report_date.strftime('%B%Y')}-{str(uuid4()).split('-')[-1]}"
        
        financial_report = FinancialReport.objects.create(
            report_id=report_id,
            legal_entity=legal_entity,
            created_by=request.user,
            status='processing',
            report_month=report_date.strftime("%B %Y")
        )
        
        # Track import records for error handling
        import_records = []
        all_succeeded = True
        total_rows_processed = 0
        
        # Process each file upload
        for dataset_type in selected_types:
            file_key = f'file_{dataset_type.id}'
            file = request.FILES.get(file_key)
            
            if not file:
                # Optional: skip if not provided, or require all files
                continue
            
            # Validate file extension
            allowed_extensions = ['csv', 'xlsx', 'xls']
            file_ext = file.name.split('.')[-1].lower()
            
            if file_ext not in allowed_extensions:
                messages.warning(request, f"{dataset_type.display_name}: File format not supported. Skipped.")
                continue
            
            # Create import record
            import_record = XeroDataImport.objects.create(
                financial_report=financial_report,
                legal_entity=legal_entity,
                dataset_type=dataset_type,
                report_id=report_id,
                file=file,
                file_name=file.name,
                tenant_name=request.user.tenant.name,
                created_by=request.user,
                status='processing'
            )
            import_records.append((dataset_type, import_record))
            
            try:
                # Save file to temporary location
                tmp_path = None
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                    for chunk in file.chunks():
                        tmp_file.write(chunk)
                    tmp_path = tmp_file.name
                
                print(f"\n{'='*60}")
                print(f"Processing {dataset_type.display_name} for {legal_entity.name}")
                print(f"Report ID: {report_id}")
                print(f"{'='*60}\n")
                
                # Transform based on dataset type
                df = None
                dataset_name = dataset_type.name.lower()
                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                try:
                    if dataset_name == 'balance_sheet':
                        df = transform_balance_sheet(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name == 'budget_summary':
                        df = transform_budget_summary(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name == 'budget_variance':
                        df = transform_budget_variance(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name == 'profit_and_loss':
                        df = transform_profit_loss(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    elif dataset_name in ('profit_and_loss_vs_py', 'profit_and_loss_vs_ly'):
                        df = transform_profit_loss_ly(
                            file_path=tmp_path,
                            legal_entity=legal_entity.name,
                            report_id=report_id,
                            created_at=created_at
                        )
                    else:
                        raise ValueError(f"Unknown dataset type: {dataset_name}")
                    
                    if df is not None:
                        # Update import record with success info
                        rows_processed = len(df)
                        import_record.rows_processed = rows_processed
                        import_record.status = 'completed'
                        import_record.processed_at = timezone.now()
                        import_record.save()
                        
                        total_rows_processed += rows_processed
                        
                        print(f"\n✓ {dataset_type.display_name} - {rows_processed} rows processed")
                        print(f"Columns: {df.columns.tolist()}")
                    else:
                        raise ValueError("Data transformation returned None")
                        
                except Exception as e:
                    # Update import record with error
                    import_record.status = 'failed'
                    import_record.error_message = str(e)
                    import_record.processed_at = timezone.now()
                    import_record.save()
                    
                    all_succeeded = False
                    print(f"\n✗ Error processing {dataset_type.display_name}: {str(e)}")
                    traceback.print_exc()
                    
            except Exception as e:
                # Update import record with error
                import_record.status = 'failed'
                import_record.error_message = str(e)
                import_record.processed_at = timezone.now()
                import_record.save()
                
                all_succeeded = False
                print(f"\n✗ Error with {dataset_type.display_name}: {str(e)}")
                traceback.print_exc()
                
            finally:
                # Clean up temporary file
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except PermissionError:
                        print(f"Warning: Could not delete temp file {tmp_path}")
                
                # Delete uploaded file for data privacy
                if import_record.file:
                    import_record.file.delete(save=False)
        
        # Update financial report status
        financial_report.total_rows_processed = total_rows_processed
        if all_succeeded:
            financial_report.status = 'completed'
            financial_report.completed_at = timezone.now()
            messages.success(request, f"Financial report processed successfully! {total_rows_processed} total rows processed across {len(import_records)} reports.")
        else:
            financial_report.status = 'failed'
            financial_report.completed_at = timezone.now()
            messages.error(request, "One or more reports encountered errors. See details below.")
        
        financial_report.save()
        
        return redirect('import_detail', import_id=financial_report.id)
    
    context = {
        'legal_entity': legal_entity,
        'dataset_types': selected_types,
    }
    return render(request, 'xero/import_upload_multiple.html', context)


@login_required
def import_detail(request, import_id):
    """View financial report details and status"""
    report = get_object_or_404(FinancialReport, id=import_id)
    
    # Verify user has access
    if report.legal_entity.tenant_id != request.user.tenant_id:
        return HttpResponseForbidden("You don't have access to this report.")
    
    context = {
        'report': report,
        'import_records': report.data_imports.all(),
    }
    return render(request, 'xero/import_detail.html', context)


@login_required
def import_history(request):
    """View import history for the user's tenant"""
    if not request.user.tenant:
        messages.error(request, "Please contact your administrator to assign you to a tenant.")
        return redirect("home")
    
    # Get all financial reports for this tenant's legal entities
    reports = FinancialReport.objects.filter(
        legal_entity__tenant=request.user.tenant
    ).select_related('legal_entity', 'created_by').order_by('-created_at')
    
    # Calculate metrics
    total_reports = reports.count()
    completed_reports = reports.filter(status='completed').count()
    failed_reports = reports.filter(status='failed').count()
    
    # Calculate failure rate percentage
    if total_reports > 0:
        failure_rate = round((failed_reports / total_reports) * 100)
    else:
        failure_rate = 0
    
    context = {
        'reports': reports,
        'total_reports': total_reports,
        'completed_reports': completed_reports,
        'failed_reports': failed_reports,
        'failure_rate': failure_rate,
    }
    return render(request, 'xero/import_history.html', context)

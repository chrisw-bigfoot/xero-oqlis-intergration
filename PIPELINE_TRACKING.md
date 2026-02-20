# Pipeline Tracking Implementation

## Overview
Added comprehensive tracking for both the **transformation** and **database write** stages in the financial report import pipeline. Users can now see exactly which reports succeeded/failed at each stage.

## What Was Changed

### 1. Database Model (app/xero/models.py)
Added two new JSON fields to `XeroDataImport` model:

```python
# Track if report transformation succeeded/failed with details
transformation_status = models.JSONField(
    default=dict,
    blank=True,
    help_text="Track if report transformation succeeded/failed with details"
)

# Track if database write succeeded/failed with details
database_write_status = models.JSONField(
    default=dict,
    blank=True,
    help_text="Track if database write succeeded/failed with details"
)
```

**Migration**: `0007_xerodataimport_database_write_status_and_more.py` (Applied)

### 2. Data Structure Format

Each field stores JSON in this format:

```json
{
  "status": "success|failed|skipped",
  "rows": 1250,
  "error": null | "error message"
}
```

**Possible statuses**:
- `success`: Operation completed successfully
- `failed`: Operation failed with error details
- `skipped`: Operation was skipped (e.g., DB write skipped if transformation failed)

### 3. View Implementation (app/xero/views.py)

Both import views (`start_import` and `import_upload_multiple`) now track:

#### Transformation Stage
- ✅ Success: Records rows transformed, stores in `transformation_status`
- ❌ Failure: Records error message, stores in `transformation_status`

#### Database Write Stage
- ✅ Success: Records rows written, stores in `database_write_status`
- ❌ Failure: Records error message, stores in `database_write_status`
- ⏭️ Skipped: If transformation failed, marks as skipped with reason

### 4. Template Update (app/templates/xero/import_detail.html)

Updated import history table to display:
- **Report Type**: Dataset name and file
- **Overall**: Overall status badge
- **Transformation**: Shows ✓ Success / ✗ Failed / - Skipped with row count or error
- **Database Write**: Shows ✓ Success / ✗ Failed / - Skipped with row count or error
- **Rows**: Total processed rows

Example display:
```
Balance Sheet | Completed | ✓ Success (1250 rows) | ✓ Success (1250 rows) | 1250
Budget Summary | Completed | ✓ Success (520 rows) | ✗ Failed (Connection error) | 520
```

## How It Works

### Import Flow
```
File Upload
    ↓
Transformation (tracked)
    ├─ Success → Store in transformation_status
    └─ Failure → Store error, skip database write (mark as skipped)
    ↓
Database Write (tracked if transformation succeeded)
    ├─ Success → Store in database_write_status
    └─ Failure → Store error in database_write_status
```

### Error Visibility
- **Transformation errors**: Appear in "Transformation" column with truncated error message
- **Database write errors**: Appear in "Database Write" column with truncated error message
- **Full error messages**: Available on hover via title attribute

## Testing the Feature

### To verify the tracking works:

1. **Test successful import**:
   ```
   Upload a valid financial report → Check import_detail page → Both columns show ✓ Success
   ```

2. **Test transformation failure**:
   ```
   Upload invalid/malformed file → Transformation fails → Database Write column shows "- Skipped"
   ```

3. **Test database write failure**:
   ```
   Upload valid file → Transformation succeeds → Database connection fails → Database Write shows ✗ Failed
   ```

## Benefits

✅ **Complete Visibility**: Users see exactly where in the pipeline each report succeeded/failed  
✅ **Detailed Error Messages**: Truncated error messages on hover for full details  
✅ **Row Counts**: Track how many rows were processed at each stage  
✅ **Pipeline Transparency**: Clear indication of skipped stages (transformation failure → DB write skipped)  
✅ **Debugging Support**: Helps identify whether issues are in data transformation or database connectivity

## Example JSON Values

### Successful Transformation & Database Write
```json
{
  "transformation_status": {
    "status": "success",
    "rows": 1250,
    "error": null
  },
  "database_write_status": {
    "status": "success",
    "rows": 1250,
    "error": null
  }
}
```

### Failed Transformation, Skipped Database Write
```json
{
  "transformation_status": {
    "status": "failed",
    "rows": 0,
    "error": "Column 'Account' not found in sheet"
  },
  "database_write_status": {
    "status": "skipped",
    "rows": 0,
    "error": "Transformation failed, database write skipped"
  }
}
```

### Successful Transformation, Failed Database Write
```json
{
  "transformation_status": {
    "status": "success",
    "rows": 1250,
    "error": null
  },
  "database_write_status": {
    "status": "failed",
    "rows": 0,
    "error": "Failed to connect to SingleStore: Connection timeout"
  }
}
```

## Files Modified

1. **app/xero/models.py** - Added tracking fields to XeroDataImport
2. **app/xero/migrations/0007_...py** - Database migration (auto-generated)
3. **app/xero/views.py** - Updated both import views with tracking logic
4. **app/templates/xero/import_detail.html** - Enhanced import history table display

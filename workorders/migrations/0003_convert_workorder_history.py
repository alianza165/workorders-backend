# workorders/migrations/0004_convert_workorder_history.py
from django.db import migrations
from django.utils import timezone
import json

def convert_to_history(apps, schema_editor):
    WorkOrder = apps.get_model('workorders', 'workorders')
    WorkOrderHistory = apps.get_model('workorders', 'WorkOrderHistory')
    WorkStatus = apps.get_model('workorders', 'Work_Status')
    
    # Get all unique initiation dates
    dates = WorkOrder.objects.order_by().values_list('initiation_date', flat=True).distinct()
    
    for date in dates:
        # Get all workorders with this initiation_date, ordered by timestamp
        workorders = WorkOrder.objects.filter(initiation_date=date).order_by('timestamp')
        
        if workorders.count() <= 1:
            continue  # No history to convert
            
        # First workorder becomes the main record
        main_workorder = workorders[0]
        
        # Convert subsequent workorders to history entries
        for i, wo in enumerate(workorders[1:], start=1):
            # Create the snapshot
            snapshot = {
                'id': wo.id,
                'initiation_date': str(wo.initiation_date),
                'department': wo.department,
                'problem': wo.problem,
                'equipment': {
                    'id': wo.equipment.id,
                    'machine': wo.equipment.machine,
                    'machine_type': str(wo.equipment.machine_type)
                },
                'work_status': {
                    'id': wo.work_status.id if wo.work_status else None,
                    'work_status': wo.work_status.work_status if wo.work_status else None
                },
                # Include all other fields...
            }
            
            # Determine the action type
            if i == 1:
                action = 'created'
            elif wo.work_status and wo.work_status.work_status == 'Completed':
                action = 'completed'
            elif wo.accepted:
                action = 'accepted'
            else:
                action = 'updated'
            
            # Create the history entry
            WorkOrderHistory.objects.create(
                workorder=main_workorder,
                snapshot=snapshot,
                changed_by=wo.initiated_by,
                action=action,
                timestamp=wo.timestamp or wo.initiation_date
            )
            
            # Delete the duplicate workorder (optional)
            wo.delete()

class Migration(migrations.Migration):
    dependencies = [
        ('workorders', '0002_workorderhistory'),  # Update to your last migration
    ]

    operations = [
        migrations.RunPython(convert_to_history),
    ]
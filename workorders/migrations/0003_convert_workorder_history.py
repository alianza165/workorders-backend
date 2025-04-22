# workorders/migrations/0004_convert_workorder_history.py
from django.db import migrations
from django.utils import timezone
import json
from deepdiff import DeepDiff

def convert_to_history(apps, schema_editor):
    WorkOrder = apps.get_model('workorders', 'workorders')
    WorkOrderHistory = apps.get_model('workorders', 'WorkOrderHistory')
    
    # Get all unique initiation dates
    dates = WorkOrder.objects.order_by().values_list('initiation_date', flat=True).distinct()
    
    for date in dates:
        # Get all workorders with this initiation_date, ordered by timestamp
        workorders_list = WorkOrder.objects.filter(initiation_date=date).order_by('timestamp')
        
        if workorders_list.count() <= 1:
            continue
            
        # The LAST workorder becomes the main record with complete snapshot
        main_workorder = workorders_list.last()
        final_snapshot = create_complete_snapshot(main_workorder)
        
        # First create history entries for all workorders except the last one
        previous_snapshot = None
        for wo in workorders_list:
            if wo.id == main_workorder.id:
                continue  # Skip the main record we're keeping
                
            current_snapshot = create_complete_snapshot(wo)
            
            if previous_snapshot is None:
                # First entry gets a full snapshot with 'created' action
                WorkOrderHistory.objects.create(
                    workorder=main_workorder,
                    snapshot=current_snapshot,
                    changed_by=wo.initiated_by,
                    action='created',
                    timestamp=wo.timestamp or wo.initiation_date
                )
            else:
                # Subsequent entries get diffs
                diff = get_changed_fields(previous_snapshot, current_snapshot)
                minimal_snapshot = {}
                for field in diff['changed_fields']:
                    minimal_snapshot[field] = current_snapshot[field]
                minimal_snapshot['id'] = wo.id
                
                action = determine_action_based_on_changes(diff)
                
                WorkOrderHistory.objects.create(
                    workorder=main_workorder,
                    snapshot=minimal_snapshot,
                    changed_by=wo.initiated_by,
                    action=action,
                    timestamp=wo.timestamp or wo.initiation_date
                )
            
            previous_snapshot = current_snapshot
            wo.delete()  # Delete the duplicate workorder
            

def create_complete_snapshot(workorder):
    """Create a complete snapshot of all fields"""
    return {
        'id': workorder.id,
        'initiation_date': str(workorder.initiation_date),
        'department': workorder.department,
        'problem': workorder.problem,
        'initiated_by': {
            'id': workorder.initiated_by.id,
            'username': workorder.initiated_by.username
        },
        'equipment': {
            'id': workorder.equipment.id,
            'machine': workorder.equipment.machine,
            'machine_type': str(workorder.equipment.machine_type)
        },
        'part': workorder.part.id if workorder.part else None,
        'type_of_work': workorder.type_of_work.id,
        'closed': workorder.closed.id if workorder.closed else None,
        'closing_remarks': workorder.closing_remarks,
        'accepted': workorder.accepted,
        'assigned_to': workorder.assigned_to,
        'target_date': str(workorder.target_date) if workorder.target_date else None,
        'remarks': workorder.remarks,
        'replaced_part': workorder.replaced_part,
        'completion_date': str(workorder.completion_date),
        'work_status': {
            'id': workorder.work_status.id if workorder.work_status else None,
            'work_status': workorder.work_status.work_status if workorder.work_status else None
        },
        'pending': workorder.pending.id if workorder.pending else None,
        'pr_number': workorder.pr_number,
        'pr_date': str(workorder.pr_date) if workorder.pr_date else None,
        'timestamp': str(workorder.timestamp) if workorder.timestamp else None
    }

def get_changed_fields(previous, current):
    """Identify all changed fields between snapshots"""
    changed_fields = []
    action_hint = None
    
    # Compare each field
    for field in previous.keys():
        if field not in current or previous[field] != current[field]:
            changed_fields.append(field)
            
            # Detect specific important changes
            if field == 'work_status' and current.get('work_status', {}).get('work_status') == 'Completed':
                action_hint = 'completed'
            elif field == 'accepted' and current.get('accepted'):
                action_hint = 'accepted'
            elif field == 'closed' and current.get('closed'):
                action_hint = 'closed'
    
    return {
        'changed_fields': changed_fields,
        'action_hint': action_hint
    }

def determine_action_based_on_changes(diff):
    """Determine the most appropriate action based on changes"""
    if diff['action_hint']:
        return diff['action_hint']
    
    # Default to 'updated' if no specific action detected
    return 'updated'

class Migration(migrations.Migration):
    dependencies = [
        ('workorders', '0002_workorderhistory'),
    ]

    operations = [
        migrations.RunPython(convert_to_history),
    ]
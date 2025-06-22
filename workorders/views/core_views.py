from rest_framework import viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework import status
from django.contrib.auth.models import User
from django_filters import rest_framework as filters
from ..models import (
    Location, Machine_Type, Part_Type, Type_of_Work, Work_Status,
    Pending, Closed, Equipment, Part, workorders, WorkOrderHistory, UserPrompt
)
from ..serializers import (
    LocationSerializer, MachineTypeSerializer, PartTypeSerializer,
    TypeOfWorkSerializer, WorkStatusSerializer, PendingSerializer,
    ClosedSerializer, EquipmentSerializer, PartSerializer, WorkOrderSerializer, 
    WorkOrderHistorySerializer, WorkOrderCreateSerializer, WorkOrderSerializer, UserPromptSerializer
)
from django.db.models import Q
from django.utils import timezone
from rest_framework.pagination import LimitOffsetPagination


class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [permissions.IsAuthenticated]

class MachineTypeViewSet(viewsets.ModelViewSet):
    queryset = Machine_Type.objects.all()
    serializer_class = MachineTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

class PartTypeViewSet(viewsets.ModelViewSet):
    queryset = Part_Type.objects.all()
    serializer_class = PartTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

class TypeOfWorkViewSet(viewsets.ModelViewSet):
    queryset = Type_of_Work.objects.all()
    serializer_class = TypeOfWorkSerializer
    permission_classes = [permissions.IsAuthenticated]

class WorkStatusViewSet(viewsets.ModelViewSet):
    queryset = Work_Status.objects.all()
    serializer_class = WorkStatusSerializer
    permission_classes = [permissions.IsAuthenticated]

class PendingViewSet(viewsets.ModelViewSet):
    queryset = Pending.objects.all()
    serializer_class = PendingSerializer
    permission_classes = [permissions.IsAuthenticated]

class ClosedViewSet(viewsets.ModelViewSet):
    queryset = Closed.objects.all()
    serializer_class = ClosedSerializer
    permission_classes = [permissions.IsAuthenticated]

class EquipmentPagination(LimitOffsetPagination):
    default_limit = 1000  # Set a higher default limit
    max_limit = 1000     # Set a safe maximum limit

class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.all().select_related('machine_type', 'location')
    serializer_class = EquipmentSerializer
    pagination_class = EquipmentPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(machine__icontains=search) |
                Q(machine_type__machine_type__icontains=search) |
                Q(location__area__icontains=search)
            )
        return queryset

class PartViewSet(viewsets.ModelViewSet):
    queryset = Part.objects.all()
    serializer_class = PartSerializer
    permission_classes = [permissions.IsAuthenticated]

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_workorder_access(request, pk):
    workorder = get_object_or_404(workorders, pk=pk)
    
    # Implement your access logic here (same as in WorkOrderViewSet.get_queryset())
    if request.user.profile.is_manager:
        return Response({'status': 'ok'})
    
    if request.user.profile.is_utilities:
        user_dept = request.user.profile.department.department
        dept_mapping = {'Electrical': 'Electrical', 'Mechanical': 'Mechanical'}
        if user_dept in dept_mapping and workorder.department == dept_mapping[user_dept]:
            return Response({'status': 'ok'})
    
    if request.user.profile.is_production:
        if workorder.initiated_by == request.user:
            return Response({'status': 'ok'})
    
    return Response({'status': 'unauthorized'}, status=status.HTTP_403_FORBIDDEN)

class WorkOrderFilter(filters.FilterSet):
    work_status = filters.CharFilter(field_name='work_status__work_status')
    department = filters.CharFilter(field_name='department')
    accepted = filters.BooleanFilter(field_name='accepted')
    closed = filters.CharFilter(field_name='closed__closed')

    class Meta:
        model = workorders
        fields = ['work_status', 'department', 'accepted', 'closed']

class WorkOrderViewSet(viewsets.ModelViewSet):
    queryset = workorders.objects.all().order_by('-initiation_date')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = WorkOrderFilter
    
    def get_serializer_class(self):
        if self.action == 'create':
            return WorkOrderCreateSerializer
        return WorkOrderSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        if not hasattr(user, 'profile'):
            return queryset.none()
        
        # Apply permission-based filtering first
        if user.profile.is_manager:
            queryset = queryset
        elif user.profile.is_utilities:
            user_dept = user.profile.department.department
            dept_mapping = {
                'Electrical': 'Electrical',
                'Mechanical': 'Mechanical'
            }
            
            if user_dept in dept_mapping:
                queryset = queryset.filter(
                    department=dept_mapping[user_dept],
                    work_status__work_status__in=['Pending', 'In_Process', 'Completed']
                )
            else:
                return queryset.none()
        elif user.profile.is_production:
            queryset = queryset.filter(Q(initiated_by=user))
        else:
            return queryset.none()

        # Now apply the requested filters
        work_status = self.request.query_params.get('work_status')
        department = self.request.query_params.get('department')
        accepted = self.request.query_params.get('accepted')
        closed = self.request.query_params.get('closed')

        if work_status:
            queryset = queryset.filter(work_status__work_status=work_status)
        if department:
            queryset = queryset.filter(department=department)
        if accepted:
            queryset = queryset.filter(accepted=accepted.lower() == 'true')
        if closed:
            queryset = queryset.filter(closed__closed=closed)

        return queryset

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        workorder = self.get_object()
        user = request.user
        
        if not hasattr(user, 'profile') or not user.profile.is_utilities:
            return Response({"error": "Only utilities users can accept workorders"}, status=403)
            
        if workorder.work_status.work_status != 'Pending':
            return Response({"error": "Only pending workorders can be accepted"}, status=400)
        
        in_process_status = get_object_or_404(Work_Status, work_status='In_Process')
        
        # Get data from request
        assigned_to = request.data.get('assigned_to', f"{user.first_name} {user.last_name}")
        target_date = request.data.get('target_date')
        remarks = request.data.get('remarks')
        
        # Update fields
        workorder.accepted = True
        workorder.work_status = in_process_status
        workorder.assigned_to = assigned_to
        workorder.target_date = target_date
        workorder.remarks = remarks
        workorder.save()
        
        # Create history record
        self.create_history_record(
            workorder=workorder,
            changed_by=user,
            action='accepted',
            snapshot_data={
                'accepted': True,
                'work_status': {'id': in_process_status.id, 'work_status': 'In_Process'},
                'assigned_to': workorder.assigned_to,
                'target_date': workorder.target_date,
                'remarks': workorder.remarks
            }
        )
        
        serializer = self.get_serializer(workorder)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        workorder = self.get_object()
        user = request.user
        
        if not hasattr(user, 'profile') or not user.profile.is_utilities:
            return Response({"error": "Only utilities users can reject workorders"}, status=403)
        
        # Update fields directly (like in accept action)
        workorder.accepted = False
        workorder.assigned_to = ""  # Clear assigned_to when rejecting
        workorder.save()
        
        # Create history record
        self.create_history_record(
            workorder=workorder,
            changed_by=user,
            action='rejected',
            snapshot_data={
                'accepted': False,
                'assigned_to': ""  # Include cleared assigned_to in history
            }
        )
        
        # Return the serialized response
        serializer = self.get_serializer(workorder)
        return Response(serializer.data)


    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        workorder = self.get_object()
        user = request.user
        
        if not hasattr(user, 'profile') or not user.profile.is_utilities:
            return Response({"error": "Only utilities users can complete workorders"}, status=403)
            
        if workorder.work_status.work_status != 'In_Process':
            return Response({"error": "Only workorders in process can be completed"}, status=400)
        
        completed_status = get_object_or_404(Work_Status, work_status='Completed')
        
        # Update fields directly
        workorder.work_status = completed_status
        workorder.completion_date = timezone.now()
        workorder.save()
        
        # Create history record
        self.create_history_record(
            workorder=workorder,
            changed_by=user,
            action='completed',
            snapshot_data={
                'work_status': {
                    'id': completed_status.id, 
                    'work_status': completed_status.work_status
                },
                'completion_date': workorder.completion_date.isoformat()
            }
        )
        
        serializer = self.get_serializer(workorder)
        return Response(serializer.data)


    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        workorder = self.get_object()
        user = request.user
        
        # Debug print
        print(f"Attempting to close workorder {workorder.id} by user {user.username}")
        
        if not hasattr(user, 'profile') or not user.profile.is_production:
            print("User is not production user")
            return Response({"error": "Only production users can close workorders"}, status=403)
        
        if workorder.work_status.work_status != 'Completed':
            print(f"Work status is {workorder.work_status.work_status}, expected 'Completed'")
            return Response({"error": "Work must be completed before closing"}, status=400)
        
        try:
            closed_value = request.data.get('closed')
            print(f"Received closed value: {closed_value}")
            
            if closed_value is None:
                print("No closed value provided")
                return Response({"error": "closed field is required"}, status=400)
            
            # Get the Closed instance
            closed_status = 'Yes' if str(closed_value).lower() in ['true', 'yes', '1'] else 'No'
            print(f"Looking for Closed status: {closed_status}")
            
            closed_instance = get_object_or_404(Closed, closed=closed_status)
            print(f"Found Closed instance: {closed_instance}")
            
            # Update fields directly
            workorder.closed = closed_instance
            workorder.closing_remarks = request.data.get('closing_remarks', '')
            workorder.save()
            
            # Create history record
            self.create_history_record(
                workorder=workorder,
                changed_by=user,
                action='closed' if closed_instance.closed == 'Yes' else 'reopened',
                snapshot_data={
                    'closed': {
                        'id': closed_instance.id,
                        'closed': closed_instance.closed
                    },
                    'closing_remarks': workorder.closing_remarks
                }
            )
            
            serializer = self.get_serializer(workorder)
            print("Workorder closed successfully")
            return Response(serializer.data)
            
        except Exception as e:
            print(f"Error closing workorder: {str(e)}")
            return Response({"error": str(e)}, status=400)

    def perform_create(self, serializer):
        workorder = serializer.save()
        self.create_history_record(
            workorder=workorder,
            changed_by=self.request.user,
            action='created',
            full_snapshot=True
        )

    def perform_update(self, serializer):
        print("Incoming data:", self.request.data)  # Log incoming data
        
        old_instance = self.get_object()
        old_snapshot = self.create_complete_snapshot(old_instance)
        
        try:
            workorder = serializer.save()
            print("Update successful")
        except Exception as e:
            print("Serializer error:", str(e))
            raise
        
        new_snapshot = self.create_complete_snapshot(workorder)
        diff = self.get_changed_fields(old_snapshot, new_snapshot)
        
        action = self.determine_action(serializer.validated_data, diff['changed_fields'])
        self.create_history_record(
            workorder=workorder,
            changed_by=self.request.user,
            action=action,
            snapshot_data={field: new_snapshot[field] for field in diff['changed_fields']},
            full_snapshot=False
        )

    def create_history_record(self, workorder, changed_by, action, snapshot_data=None, full_snapshot=False):
        snapshot = self.create_complete_snapshot(workorder) if full_snapshot else (snapshot_data or {})
        snapshot['id'] = workorder.id
        
        WorkOrderHistory.objects.create(
            workorder=workorder,
            snapshot=snapshot,
            changed_by=changed_by,
            action=action,
            timestamp=timezone.now()
        )

    def create_complete_snapshot(self, workorder):
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
                'id': workorder.work_status.id,
                'work_status': workorder.work_status.work_status
            },
            'pending': workorder.pending.id if workorder.pending else None,
            'pr_number': workorder.pr_number,
            'pr_date': str(workorder.pr_date) if workorder.pr_date else None,
            'timestamp': str(workorder.timestamp) if workorder.timestamp else None
        }

    def get_changed_fields(self, previous, current):
        changed_fields = []
        action_hint = None
        
        for field in previous.keys():
            if field not in current or previous[field] != current[field]:
                changed_fields.append(field)
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

    def determine_action(self, validated_data, changed_fields):
        if 'accepted' in validated_data:
            return 'accepted' if validated_data['accepted'] else 'rejected'
        if 'work_status' in validated_data:
            if validated_data['work_status'].work_status == 'Completed':
                return 'completed'
        if 'closed' in validated_data:
            return 'closed' if validated_data['closed'].closed == 'Yes' else 'reopened'
        return 'updated'


class WorkOrderHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkOrderHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        workorder_id = self.kwargs['workorder_pk']
        return WorkOrderHistory.objects.filter(workorder_id=workorder_id).order_by('-timestamp')


class UserPromptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserPromptSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = UserPrompt.objects.all().order_by('-created_at')
        
        # If user is not admin/superuser, filter to only their prompts
        if not self.request.user.is_superuser and not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
            
        return queryset
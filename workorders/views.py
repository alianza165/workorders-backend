from rest_framework import viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework import status
from django.contrib.auth.models import User
from .models import (
    Location, Machine_Type, Part_Type, Type_of_Work, Work_Status,
    Pending, Closed, Equipment, Part, workorders, WorkOrderHistory
)
from .serializers import (
    LocationSerializer, MachineTypeSerializer, PartTypeSerializer,
    TypeOfWorkSerializer, WorkStatusSerializer, PendingSerializer,
    ClosedSerializer, EquipmentSerializer, PartSerializer, WorkOrderSerializer, 
    WorkOrderHistorySerializer, WorkOrderCreateSerializer, WorkOrderUpdateSerializer
)
from django.db.models import Q
from django.utils import timezone

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

class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.all()
    serializer_class = EquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]

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

class WorkOrderViewSet(viewsets.ModelViewSet):
    queryset = workorders.objects.all().order_by('-initiation_date')
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return WorkOrderCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return WorkOrderUpdateSerializer
        return WorkOrderSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        if not hasattr(user, 'profile'):
            return queryset.none()
        
        if user.profile.is_manager:
            return queryset
        
        elif user.profile.is_utilities:
            user_dept = user.profile.department.department
            dept_mapping = {
                'Electrical': 'Electrical',
                'Mechanical': 'Mechanical'
            }
            
            if user_dept in dept_mapping:
                return queryset.filter(
                    department=dept_mapping[user_dept],
                    work_status__work_status__in=['Pending', 'In_Process', 'Completed']
                )
            return queryset.none()
        
        elif user.profile.is_production:
            # Production can see their own created workorders and completed ones they need to close
            return queryset.filter(
                Q(initiated_by=user)
            )
        
        return queryset.none()

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        print(request)
        workorder = self.get_object()
        user = request.user
        
        # Verify utilities user
        if not hasattr(user, 'profile') or not user.profile.is_utilities:
            return Response({"error": "Only utilities users can accept workorders"}, status=403)
            
        # Verify workorder is in Pending state
        if workorder.work_status.work_status != 'Pending':
            return Response({"error": "Only pending workorders can be accepted"}, status=400)
        
        # Update workorder status
        workorder.accepted = True
        workorder.work_status = get_object_or_404(Work_Status, work_status='In_Process')
        workorder.assigned_to = f"{user.first_name} {user.last_name}"
        workorder.save()
        
        # Create history record
        WorkOrderHistory.objects.create(
            workorder=workorder,
            snapshot=WorkOrderSerializer(workorder).data,
            changed_by=user,
            action='accepted'
        )
        
        return Response(WorkOrderSerializer(workorder).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        workorder = self.get_object()
        user = request.user
        
        if not hasattr(user, 'profile') or not user.profile.is_utilities:
            return Response({"error": "Only utilities users can reject workorders"}, status=403)
            
        workorder.accepted = False
        workorder.work_status = get_object_or_404(Work_Status, work_status='Rejected')
        workorder.save()
        
        WorkOrderHistory.objects.create(
            workorder=workorder,
            snapshot=WorkOrderSerializer(workorder).data,
            changed_by=user,
            action='rejected'
        )
        
        return Response(WorkOrderSerializer(workorder).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        workorder = self.get_object()
        user = request.user
        
        if not hasattr(user, 'profile') or not user.profile.is_utilities:
            return Response({"error": "Only utilities users can complete workorders"}, status=403)
            
        if workorder.work_status.work_status != 'In_Process':
            return Response({"error": "Only workorders in process can be completed"}, status=400)
            
        workorder.work_status = get_object_or_404(Work_Status, work_status='Completed')
        workorder.completion_date = timezone.now()
        workorder.save()
        
        WorkOrderHistory.objects.create(
            workorder=workorder,
            snapshot=WorkOrderSerializer(workorder).data,
            changed_by=user,
            action='completed'
        )
        
        return Response(WorkOrderSerializer(workorder).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        workorder = self.get_object()
        user = request.user
        
        if not hasattr(user, 'profile') or not user.profile.is_production:
            return Response({"error": "Only production users can close workorders"}, status=403)
        
        if workorder.work_status.work_status != 'Completed':
            return Response({"error": "Work must be completed before closing"}, status=400)
        
        closed_value = request.data.get('closed')
        closing_remarks = request.data.get('closing_remarks', '')
        
        if closed_value is None:
            return Response({"error": "closed field is required"}, status=400)
        
        # Get the Closed instance based on the boolean value
        closed_status = 'Yes' if closed_value else 'No'
        closed_instance = get_object_or_404(Closed, closed=closed_status)
        
        workorder.closed = closed_instance
        workorder.closing_remarks = closing_remarks
        workorder.save()
        
        # Create history record
        WorkOrderHistory.objects.create(
            workorder=workorder,
            snapshot=WorkOrderSerializer(workorder).data,
            changed_by=user,
            action='closed' if closed_value else 'reopened'
        )
        
        return Response(WorkOrderSerializer(workorder).data)


class WorkOrderHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkOrderHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        workorder_id = self.kwargs['workorder_pk']
        return WorkOrderHistory.objects.filter(workorder_id=workorder_id).order_by('-timestamp')
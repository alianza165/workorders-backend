from rest_framework import serializers
from .models import (
    Location, Machine_Type, Part_Type, Type_of_Work, Work_Status,
    Pending, Closed, Equipment, Part, workorders, WorkOrderHistory
)
from django.contrib.auth.models import User
from django.utils import timezone


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        from accounts.models import Department
        model = Department
        fields = '__all__'

class LocationSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer()
    
    class Meta:
        model = Location
        fields = '__all__'

class MachineTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Machine_Type
        fields = '__all__'

class PartTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Part_Type
        fields = '__all__'

class TypeOfWorkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Type_of_Work
        fields = '__all__'

class WorkStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Work_Status
        fields = '__all__'

class PendingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pending
        fields = '__all__'

class ClosedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Closed
        fields = '__all__'

class EquipmentSerializer(serializers.ModelSerializer):
    machine_type = MachineTypeSerializer()
    location = LocationSerializer()
    
    class Meta:
        model = Equipment
        fields = '__all__'

class PartSerializer(serializers.ModelSerializer):
    part_type = PartTypeSerializer()
    equipment = EquipmentSerializer()
    
    class Meta:
        model = Part
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        from django.contrib.auth.models import User
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']


class WorkOrderSerializer(serializers.ModelSerializer):
    initiated_by = UserSerializer()
    equipment = EquipmentSerializer()
    part = PartSerializer(required=False)
    type_of_work = TypeOfWorkSerializer()
    closed = ClosedSerializer(required=False)
    work_status = WorkStatusSerializer(required=False)
    pending = PendingSerializer(required=False)
    
    class Meta:
        model = workorders
        fields = '__all__'
        read_only_fields = ['initiation_date', 'timestamp']


class WorkOrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = workorders
        fields = ['department', 'problem', 'equipment', 'type_of_work', 'part']
        extra_kwargs = {
            'part': {'required': False}
        }

    def to_representation(self, instance):
        # After creation, return full workorder details using the detail serializer
        return WorkOrderSerializer(instance, context=self.context).data

    def create(self, validated_data):
        user = self.context['request'].user
        if not user.profile.is_production:
            raise serializers.ValidationError("Only production users can create workorders")
        
        validated_data.update({
            'initiation_date': timezone.now(),
            'initiated_by': user,
            'work_status': Work_Status.objects.get(work_status='Pending')
        })
        
        workorder = super().create(validated_data)
        
        return workorder

class WorkOrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = workorders
        fields = ['accepted', 'assigned_to', 'target_date', 'remarks', 'work_status']
        
    def validate(self, data):
        user = self.context['request'].user
        instance = self.instance
        
        if user.profile.is_utilities:
            if 'accepted' in data:
                if data['accepted'] is False:
                    data['work_status'] = Work_Status.objects.get(work_status='Rejected')
                else:
                    data['work_status'] = Work_Status.objects.get(work_status='In_Process')
        
        elif user.profile.is_production and 'closed' in data:
            if instance.work_status.work_status != 'Completed':
                raise serializers.ValidationError("Work must be completed before closing")
        
        return data
    
    def update(self, instance, validated_data):
        user = self.context['request'].user
        old_status = instance.work_status
        
        # Perform the update
        instance = super().update(instance, validated_data)
        
        # Create history record if status changed or closed field updated
        if (old_status != instance.work_status) or ('closed' in validated_data):
            WorkOrderHistory.objects.create(
                workorder=instance,
                snapshot=WorkOrderSerializer(instance).data,
                changed_by=user,
                action='status_changed' if old_status != instance.work_status else 'closed_updated'
            )
        
        return instance


class UserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class WorkOrderHistorySerializer(serializers.ModelSerializer):
    changed_by = UserSimpleSerializer()
    
    class Meta:
        model = WorkOrderHistory
        fields = '__all__'
        read_only_fields = ['timestamp']
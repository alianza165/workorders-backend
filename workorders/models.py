from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from accounts.models import Profile, Department
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db.models.functions import Upper


class Location(models.Model):
	department = models.ForeignKey(Department, on_delete=models.CASCADE)
	area = models.CharField(max_length=50)

	def __str__(self):
		return self.area


class Machine_Type(models.Model):
	machine_type = models.CharField(max_length=50)

	def __str__(self):
		return self.machine_type


class Part_Type(models.Model):
	part_type = models.CharField(max_length=50)

	def __str__(self):
		return self.part_type


class Type_of_Work(models.Model):
	type_of_work = models.CharField(max_length=50)

	def __str__(self):
		return self.type_of_work


class Work_Status(models.Model):
	work_status = models.CharField(max_length=50)

	def __str__(self):
		return self.work_status


class Pending(models.Model):
	pending = models.CharField(max_length=100)

	def __str__(self):
		return self.pending


class Closed(models.Model):
	closed = models.CharField(max_length=100)

	def __str__(self):
		return self.closed


class Equipment(models.Model):
	machine = models.CharField(max_length=50)
	machine_type = models.ForeignKey(Machine_Type, on_delete=models.CASCADE)
	location = models.ForeignKey(Location, on_delete=models.CASCADE)

	def __str__(self):
		return self.machine


class Part(models.Model):
	name = models.CharField(max_length=50, default='none')
	part_type = models.ForeignKey(Part_Type, on_delete=models.CASCADE)
	equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE)

	def __str__(self):
		return self.name


class workorders(models.Model):
	DEPARTMENTS = (
    ('Electrical', 'ELECTRICAL'),
    ('Mechanical', 'MECHANICAL'),
    ('Miscellaneous', 'MISCELLANEOUS'),
)
	initiation_date = models.DateTimeField(default=timezone.now)
	department = models.CharField(max_length=20, choices=DEPARTMENTS, default='miscellaneous')
	problem = models.TextField()
	initiated_by = models.ForeignKey(User, on_delete=models.CASCADE)
	equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE)
	part = models.ForeignKey(Part, null=True, default=None, on_delete=models.CASCADE)
	type_of_work = models.ForeignKey(Type_of_Work, on_delete=models.CASCADE)
	closed = models.ForeignKey(Closed, on_delete=models.CASCADE, null=True, blank=True)
	closing_remarks = models.TextField(null=True, blank=True)

	accepted = models.BooleanField(null=True, default=None)
	assigned_to = models.CharField(max_length=100, null=True, blank=True)
	target_date = models.DateTimeField(null=True, blank=True)
	remarks = models.TextField(null=True, blank=True)
	replaced_part = models.CharField(max_length=50, default='none')
	completion_date = models.DateTimeField(default=timezone.now)
	work_status = models.ForeignKey(Work_Status, on_delete=models.CASCADE, null=True, blank=True)
	pending = models.ForeignKey(Pending, on_delete=models.CASCADE, null=True, blank=True)
	pr_number = models.CharField(max_length=50, default='none')
	pr_date = models.DateTimeField(null=True, blank=True)
	timestamp = models.DateTimeField(null=True, blank=True)

	class Meta:
		indexes = [
			models.Index(fields=['initiation_date'], name='workorders_init_date_idx'),
			models.Index(fields=['department'], name='workorders_dept_idx'),
			models.Index(fields=['equipment'], name='workorders_equip_idx'),
			models.Index(fields=['part'], name='workorders_part_idx'),
			models.Index(fields=['type_of_work'], name='workorders_work_type_idx'),
			models.Index(fields=['work_status'], name='workorders_status_idx'),
		]
		ordering = ['-initiation_date']

	def __str__(self):
		i = str(self.initiation_date)
		return i


class WorkOrderHistory(models.Model):
    workorder = models.ForeignKey('workorders', on_delete=models.CASCADE, related_name='history')
    snapshot = models.JSONField()  # Stores the complete workorder state at this point
    timestamp = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)  # e.g., "created", "accepted", "completed"

    class Meta:
        ordering = ['-timestamp']


class UserPrompt(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    prompt = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    response = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict)  # For storing additional context

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Prompt by {self.user.username if self.user else 'Anonymous'} at {self.created_at}"
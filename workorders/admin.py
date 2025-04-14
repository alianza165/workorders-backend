from django.contrib import admin
from .models import workorders, Equipment, Part, Location, Machine_Type, Part_Type, Type_of_Work, Work_Status, Pending, Closed

admin.site.register(workorders)
admin.site.register(Equipment)
admin.site.register(Part)
admin.site.register(Location)
admin.site.register(Machine_Type)
admin.site.register(Part_Type)
admin.site.register(Type_of_Work)
admin.site.register(Work_Status)
admin.site.register(Pending)
admin.site.register(Closed)

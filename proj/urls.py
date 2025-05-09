from django.contrib import admin
from django.urls import path, include
from rest_framework import routers
from rest_framework.authtoken.views import obtain_auth_token

from workorders import views as workorder_views
from accounts import views as account_views

router = routers.DefaultRouter()

# Workorder endpoints
router.register(r'locations', workorder_views.LocationViewSet)
router.register(r'machine-types', workorder_views.MachineTypeViewSet)
router.register(r'part-types', workorder_views.PartTypeViewSet)
router.register(r'work-types', workorder_views.TypeOfWorkViewSet)
router.register(r'work-statuses', workorder_views.WorkStatusViewSet)
router.register(r'pending-statuses', workorder_views.PendingViewSet)
router.register(r'closed-statuses', workorder_views.ClosedViewSet)
router.register(r'equipment', workorder_views.EquipmentViewSet)  # Fixed typo: EquipmentViewSet
router.register(r'parts', workorder_views.PartViewSet)
router.register(r'workorders', workorder_views.WorkOrderViewSet, basename='workorder')  # Added basename
router.register(
    r'workorders/(?P<workorder_pk>\d+)/history', 
    workorder_views.WorkOrderHistoryViewSet, 
    basename='workorder-history'
)

# Account endpoints
router.register(r'departments', account_views.DepartmentViewSet)
router.register(r'users', account_views.UserViewSet)
router.register(r'profiles', account_views.ProfileViewSet)
router.register(r'register', account_views.UserRegistrationViewSet, basename='register')

urlpatterns = [
    path('backend/admin/', admin.site.urls),
    path('backend/api/', include(router.urls)),
    path('backend/api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('backend/api-token-auth/', account_views.CustomAuthToken.as_view(), name='api_token_auth'),
    
    # Add custom endpoints for workflow actions
    path('backend/api/workorders/<int:pk>/check-access/', workorder_views.check_workorder_access, name='workorder-check-access'),
    path('backend/api/workorders/<int:pk>/accept/', workorder_views.WorkOrderViewSet.as_view({'post': 'accept'}), name='workorder-accept'),
    path('backend/api/workorders/<int:pk>/reject/', workorder_views.WorkOrderViewSet.as_view({'post': 'reject'}), name='workorder-reject'),
    path('backend/api/workorders/<int:pk>/complete/', workorder_views.WorkOrderViewSet.as_view({'post': 'complete'}), name='workorder-complete'),
    path('backend/api/workorders/<int:pk>/close/', workorder_views.WorkOrderViewSet.as_view({'post': 'close'}), name='workorder-close'),
]

#urlpatterns = [
#    path('admin/', admin.site.urls),
#    path('api/', include(router.urls)),
#    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
#    path('api-token-auth/', account_views.CustomAuthToken.as_view(), name='api_token_auth'),
#    
#    # Add custom endpoints for workflow actions
#    path('api/workorders/<int:pk>/check-access/', workorder_views.check_workorder_access, name='workorder-check-access'),
#    path('api/workorders/<int:pk>/accept/', workorder_views.WorkOrderViewSet.as_view({'post': 'accept'}), name='workorder-accept'),
#    path('api/workorders/<int:pk>/reject/', workorder_views.WorkOrderViewSet.as_view({'post': 'reject'}), name='workorder-reject'),
#    path('api/workorders/<int:pk>/complete/', workorder_views.WorkOrderViewSet.as_view({'post': 'complete'}), name='workorder-complete'),
#    path('api/workorders/<int:pk>/close/', workorder_views.WorkOrderViewSet.as_view({'post': 'close'}), name='workorder-close'),
#]

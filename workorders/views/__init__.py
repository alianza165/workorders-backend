# workorders/views/__init__.py
from .core_views import *  # Import your existing views
from .ai_views import AIAgentView  # Make the new view available
from .analytics_views import LocationAnalyticsView, EquipmentTypeAnalyticsView, StatusTrendView, EquipmentFaultAnalysisView  # Make the new view available

# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from ..models import workorders
from django.db.models import Q, Count, F, Avg
from collections import defaultdict
from rest_framework.permissions import IsAuthenticated
from datetime import datetime, timedelta

class LocationAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get filters from query params
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        department = request.query_params.get('department')
        
        # Base queryset
        queryset = workorders.objects.all()
        
        # Apply filters
        if date_from:
            queryset = queryset.filter(initiation_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(initiation_date__lte=date_to)
        if department:
            queryset = queryset.filter(equipment__location__department__department=department)
        
        # Aggregate data
        location_data = queryset.values(
            'equipment__location__department__department',
            'equipment__location__area'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Format response
        results = []
        for item in location_data:
            results.append({
                'department': item['equipment__location__department__department'] or 'Unknown',
                'area': item['equipment__location__area'] or 'Unknown',
                'count': item['count']
            })
        
        return Response({
            'results': results,
            'total': queryset.count()
        })


class EquipmentTypeAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        queryset = workorders.objects.all()
        
        # Apply filters (same pattern as LocationAnalytics)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        department = request.query_params.get('department')
        
        if date_from:
            queryset = queryset.filter(initiation_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(initiation_date__lte=date_to)
        if department:
            queryset = queryset.filter(equipment__location__department__department=department)
        
        # Aggregate by equipment type
        equipment_data = queryset.values(
            'equipment__machine_type__machine_type'
        ).annotate(
            count=Count('id'),
            avg_completion_time=Avg(F('completion_date') - F('initiation_date'))
        ).order_by('-count')
        
        results = []
        for item in equipment_data:
            results.append({
                'equipment_type': item['equipment__machine_type__machine_type'] or 'Unknown',
                'count': item['count'],
                'avg_completion_hours': item['avg_completion_time'].total_seconds() / 3600 
                    if item['avg_completion_time'] else None
            })
        
        return Response({'results': results})


class StatusTrendView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get timeframe (default: 30 days)
        timeframe = int(request.query_params.get('timeframe', 30))
        group_by = request.query_params.get('group_by', 'week')  # day/week/month
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=timeframe)
        
        # Generate date bins
        if group_by == 'day':
            date_format = '%Y-%m-%d'
            delta = timedelta(days=1)
        elif group_by == 'month':
            date_format = '%Y-%m'
            delta = timedelta(days=30)
        else:  # week
            date_format = '%Y-%W'
            delta = timedelta(weeks=1)
        
        # Initialize result structure
        statuses = ['Pending', 'In_Process', 'Completed', 'Rejected', 'Closed']
        dates = []
        current_date = start_date
        
        while current_date <= end_date:
            dates.append(current_date.strftime(date_format))
            current_date += delta
        
        # Query data
        results = []
        for status in statuses:
            status_data = []
            for date_str in dates:
                if group_by == 'day':
                    date_filter = Q(initiation_date__date=datetime.strptime(date_str, date_format).date())
                elif group_by == 'week':
                    year, week = map(int, date_str.split('-'))
                    date_filter = Q(initiation_date__year=year, initiation_date__week=week)
                else:  # month
                    year, month = map(int, date_str.split('-'))
                    date_filter = Q(initiation_date__year=year, initiation_date__month=month)
                
                count = workorders.objects.filter(
                    date_filter &
                    Q(work_status__work_status=status)
                ).count()
                
                status_data.append(count)
            
            results.append({
                'status': status,
                'data': status_data
            })
        
        return Response({
            'timeframe': timeframe,
            'group_by': group_by,
            'dates': dates,
            'results': results
        })
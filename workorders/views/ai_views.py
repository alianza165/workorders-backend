from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from ..utils.ai_utils import get_vector_store
from rest_framework.permissions import IsAuthenticated
from ..models import workorders, Equipment, Part, Type_of_Work, Work_Status, UserPrompt
from accounts.models import Department
from ..serializers import UserPromptSerializer 
from django.db.models import Q, Count, F
from django.db import connection
import re
import logging
from django.core.cache import cache
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def is_pure_total_count_query(prompt):
    """Check if this is purely asking for total count without filters"""
    pure_total_patterns = [
        r'\bhow many workorders? (in total|are there|total count|exist)\b',
        r'\b(total|number of|count of) workorders?\b(?!.*(last|past|previous))',
        r'\bworkorders? count\b(?!.*(last|past|previous))',
        r'\b(give|show|tell) me (the )?total number of workorders?\b(?!.*(last|past|previous))',
        r'\bwhat is the total workorders? count\b(?!.*(last|past|previous))'
    ]
    return any(re.search(pattern, prompt.lower()) for pattern in pure_total_patterns)

class AIAgentView(APIView):
    permission_classes = [IsAuthenticated]
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.llm = OpenAI(
            temperature=0.2,
            max_tokens=1000,
            model="gpt-3.5-turbo-instruct"
        )
        self.query_templates = {
            'count': "SELECT COUNT(*) FROM workorders_workorders wo JOIN workorders_equipment e ON wo.equipment_id = e.id JOIN workorders_location l ON e.location_id = l.id WHERE {conditions}",
            'summary': """
                SELECT 
                    wo.id, 
                    wo.problem, 
                    wo.initiation_date,
                    e.machine AS equipment, 
                    p.name AS part,
                    tow.type_of_work,
                    ws.work_status,
                    l.department_id AS department_id,
                    d.department AS department_name
                FROM workorders_workorders wo
                LEFT JOIN workorders_equipment e ON wo.equipment_id = e.id
                LEFT JOIN workorders_location l ON e.location_id = l.id
                LEFT JOIN accounts_department d ON l.department_id = d.id
                LEFT JOIN workorders_part p ON wo.part_id = p.id
                LEFT JOIN workorders_type_of_work tow ON wo.type_of_work_id = tow.id
                LEFT JOIN workorders_work_status ws ON wo.work_status_id = ws.id
                WHERE {conditions}
                ORDER BY wo.initiation_date DESC
                LIMIT {limit}
            """
        }

    def _generate_sql_conditions(self, keyword, filters=None):
        """Generate SQL conditions with proper table references"""
        conditions = []
        params = []
        
        # Keyword search
        if keyword:
            words = keyword.split()
            word_conditions = []
            for word in words:
                word_conditions.append("wo.problem ILIKE %s")
                params.append(f"%{word}%")
            conditions.append(f"({' OR '.join(word_conditions)})")

        # Date filters (exact match to frontend keys)
        filters = filters or {}
        for date_field in ['dateFrom', 'dateTo']:
            date_value = filters.get(date_field)
            if date_value:
                try:
                    date_obj = datetime.strptime(date_value, '%Y-%m-%d').date()
                    if date_field == 'dateFrom':
                        conditions.append("wo.initiation_date >= %s")
                    else:
                        conditions.append("wo.initiation_date <= %s")
                    params.append(date_obj)
                except ValueError:
                    logger.warning(f"Invalid {date_field} format: {date_value}")
        
        # Other filters
        filter_map = {
            'equipment': 'wo.equipment_id',
            'typeOfWork': 'wo.type_of_work_id',
            'workStatus': 'wo.work_status_id'
        }

        for frontend_key, db_field in filter_map.items():
            value = filters.get(frontend_key)
            if value:
                try:
                    conditions.append(f"{db_field} = %s")
                    params.append(int(value))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid {frontend_key} value: {value}")

        # Special handling for department (from equipment's location)
        department_value = filters.get('department')
        if department_value:
            try:
                conditions.append("l.department_id = %s")
                params.append(int(department_value))
            except (ValueError, TypeError):
                logger.warning(f"Invalid department value: {department_value}")

        return " AND ".join(conditions) if conditions else "1=1", params

    def execute_sql_query(self, query_type, keyword=None, filters=None, limit=75):
        """Execute optimized SQL queries directly"""
        conditions, params = self._generate_sql_conditions(keyword, filters)
        
        query = self.query_templates[query_type].format(
            conditions=conditions,
            limit=limit
        )
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            if query_type == 'count':
                return cursor.fetchone()[0]
            else:
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def extract_keywords(self, prompt):
        """Extract keywords from user prompt for database querying"""
        if not prompt:
            return None
            
        # Common patterns for work order queries
        patterns = [
            r'(?:workorders?|issues?|problems?)\s+(?:with|for|about)\s+([^\?]+)',
            r'(?:what|which|how many)\s+([^\?]+)\s+(?:workorders?|issues?|problems?)',
            r'([^\?]+)\s+(?:workorders?|issues?|problems?)'
        ]
        
        # Clean the prompt
        clean_prompt = re.sub(r'[^\w\s]', '', prompt.lower())
        
        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, clean_prompt)
            if match:
                keyword = match.group(1).strip()
                # Remove common stopwords
                stopwords = {'the', 'a', 'an', 'some', 'any', 'these', 'those', 'about', 'with', 'for'}
                keyword = ' '.join([word for word in keyword.split() if word not in stopwords])
                return keyword if keyword else None
        
        # Fallback: return the first few meaningful words
        words = [word for word in clean_prompt.split() if len(word) > 3][:3]
        return ' '.join(words) if words else None

    def extract_query_parameters(self, prompt):
        """Extract keywords and time frames from prompt"""
        # Time frame extraction (e.g., "last 6 months")
        time_frame = None
        time_matches = re.search(r'(last|past|previous)\s+(\d+)\s+(month|week|day)s?', prompt.lower())
        if time_matches:
            num, unit = int(time_matches.group(2)), time_matches.group(3)
            time_frame = num * (30 if unit == 'month' else 7 if unit == 'week' else 1)
        
        # Keyword extraction
        keyword = self.extract_keywords(prompt)
        
        return keyword, time_frame

    def post(self, request):
        print("Request data:", request.data)
        prompt = request.data.get('prompt', '')  # Default to empty string
        filters = request.data.get('filters', {})

        # Validate that either prompt or filters exist
        if not prompt and not any(filters.values()):
            return Response(
                {"error": "Either a prompt or at least one filter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Debug logging
            logger.info(
                "Processing request with filters:\n"
                f"dateFrom: {filters.get('dateFrom')}\n"
                f"dateTo: {filters.get('dateTo')}\n"
                f"department: {filters.get('department')}\n"
                f"equipment: {filters.get('equipment')}\n"
                f"typeOfWork: {filters.get('typeOfWork')}\n"
                f"workStatus: {filters.get('workStatus')}"
            )

            # Save prompt with filters (even if prompt is empty)
            prompt_record = UserPrompt.objects.create(
                user=request.user,
                prompt=prompt,
                metadata={
                    'filters': filters,
                    'filter_details': {
                        'date_range': f"{filters.get('dateFrom')} to {filters.get('dateTo')}",
                        'department': filters.get('department'),
                        'equipment': filters.get('equipment'),
                        'work_type': filters.get('typeOfWork'),
                        'work_status': filters.get('workStatus')
                    }
                }
            )

            # Process filters
            keyword = self.extract_keywords(prompt) if prompt else None
            conditions, params = self._generate_sql_conditions(keyword, filters)
            
            exact_count = self.execute_sql_query('count', keyword=keyword, filters=filters)
            sql_results = self.execute_sql_query('summary', keyword=keyword, filters=filters)
            
            # Prepare context
            context = "\n".join(
                f"WO#{res['id']} | {res['initiation_date'].strftime('%Y-%m-%d')} | "
                f"Department: {res.get('department_name', 'N/A')} | "
                f"Equipment: {res['equipment']} | "
                f"Problem: {res['problem'][:200]}"
                for res in sql_results
            ) if sql_results else "No matching work orders found"

            # Build filter description
            filter_description = self._build_filter_description(filters)
            
            # Enhanced prompt - different behavior when no prompt is provided
            if prompt:
                enhanced_prompt = f"""
                Analyze work orders regarding '{self.extract_keywords(prompt) or 'the query'}'{filter_description}:

                Statistics:
                - Total matching orders: {exact_count or len(sql_results)}
                - Date range: {self._get_date_range_description(filters)}

                Work Order Samples:
                {context}
                """ + ("""
                Provide analysis focusing on:
                1. Most common problem patterns
                2. Equipment/parts involved
                3. Frequency trends
                4. Recommended maintenance actions
                """ if sql_results else """
                Since no matching work orders were found, please:
                1. Suggest why there might be no records
                2. Recommend alternative search terms
                3. Provide general maintenance advice
                """) + f"\nOriginal question: {prompt}"
            else:
                # When no prompt is provided, generate a general analysis of the filtered data
                enhanced_prompt = f"""
                Analyze these filtered work orders{filter_description}:

                Statistics:
                - Total matching orders: {exact_count or len(sql_results)}
                - Date range: {self._get_date_range_description(filters)}

                Work Order Samples:
                {context}

                Provide a comprehensive analysis including:
                1. Breakdown of work order statuses
                2. Most common problems
                3. Frequency and patterns of issues
                4. Equipment maintenance insights
                5. Any notable trends or patterns
                """ + ("""
                """ if sql_results else """
                Since no matching work orders were found, please:
                1. Suggest why there might be no records
                2. Recommend alternative filters
                3. Provide general maintenance advice for this equipment/department
                """)
            
            # Get LLM response
            result = self.llm(enhanced_prompt)
            prompt_record.response = result
            prompt_record.save()

            return Response({
                "answer": result,
                "statistics": {
                    "exact_count": exact_count or len(sql_results),
                    "analyzed_samples": len(sql_results)
                },
                "sources": [
                    {
                        "work_order_id": res['id'],
                        "department": res.get('department_name', 'N/A'),
                        "equipment": res['equipment'],
                        "problem": res['problem'][:100]
                    } for res in sql_results
                ] if sql_results else []
            })
            
        except Exception as e:
            logger.error(f"AI Agent Error: {str(e)}", exc_info=True)
            return Response({
                "error": "Processing error",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _build_filter_description(self, filters):
        """Helper to build human-readable filter description"""
        if not filters:
            return ""
        
        parts = []
        if filters.get('department'):
            dept = Department.objects.filter(id=filters['department']).first()
            parts.append(f"department: {dept.department if dept else filters['department']}")
        
        if filters.get('equipment'):
            eq = Equipment.objects.filter(id=filters['equipment']).first()
            parts.append(f"equipment: {eq.machine if eq else filters['equipment']}")
        
        if filters.get('typeOfWork'):
            tow = Type_of_Work.objects.filter(id=filters['typeOfWork']).first()
            parts.append(f"type of work: {tow.type_of_work if tow else filters['typeOfWork']}")
        
        if filters.get('workStatus'):
            ws = Work_Status.objects.filter(id=filters['workStatus']).first()
            parts.append(f"status: {ws.work_status if ws else filters['workStatus']}")
        
        return f"\n\nApplied Filters: {', '.join(parts)}" if parts else ""

    def _get_date_range_description(self, filters):
        """Helper to format date range description"""
        if not filters.get('dateFrom') and not filters.get('dateTo'):
            return "all time"
        
        dates = []
        if filters.get('dateFrom'):
            dates.append(f"from {filters['dateFrom']}")
        if filters.get('dateTo'):
            dates.append(f"until {filters['dateTo']}")
        return ' '.join(dates)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from ..utils.ai_utils import get_vector_store
from rest_framework.permissions import IsAuthenticated
from workorders.models import workorders, Equipment, Part, Type_of_Work, Work_Status
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
            'count': "SELECT COUNT(*) FROM workorders_workorders WHERE {conditions}",
            'summary': """
                SELECT 
                    wo.id, wo.problem, wo.initiation_date,
                    e.machine AS equipment, 
                    p.name AS part,
                    tw.type_of_work,
                    ws.work_status
                FROM workorders_workorders wo
                LEFT JOIN workorders_equipment e ON wo.equipment_id = e.id
                LEFT JOIN workorders_part p ON wo.part_id = p.id
                LEFT JOIN workorders_type_of_work tw ON wo.type_of_work_id = tw.id
                LEFT JOIN workorders_work_status ws ON wo.work_status_id = ws.id
                WHERE {conditions}
                ORDER BY {order_by}
                LIMIT {limit}
            """
        }

    def generate_sql_conditions(self, keyword, time_frame=None):
        """Generate SQL WHERE conditions with more flexible search"""
        conditions = []
        params = []
        
        if keyword:
            # Split into individual words and search for each
            words = keyword.split()
            word_conditions = []
            for word in words:
                word_conditions.append("problem ILIKE %s")
                params.append(f"%{word}%")
            conditions.append(f"({' OR '.join(word_conditions)})")
        
        if time_frame:
            date_cutoff = datetime.now() - timedelta(days=time_frame)
            conditions.append("initiation_date >= %s")
            params.append(date_cutoff)
        
        return " AND ".join(conditions) if conditions else "1=1", params

    def execute_sql_query(self, query_type, keyword=None, time_frame=None, limit=75):
        """Execute optimized SQL queries directly"""
        conditions, params = self.generate_sql_conditions(keyword, time_frame)
        
        query = self.query_templates[query_type].format(
            conditions=conditions,
            order_by="wo.initiation_date DESC",
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
        prompt = request.data.get('prompt')
        if not prompt:
            return Response({"error": "Prompt is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Check if this is a pure total count request (no time filters)
            if is_pure_total_count_query(prompt):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM workorders_workorders")
                    total_count = cursor.fetchone()[0]
                
                return Response({
                    "answer": f"There are {total_count} work orders in total.",
                    "statistics": {
                        "exact_count": total_count,
                        "analyzed_samples": 0
                    },
                    "sources": []
                })
            
            # Extract time frame if present
            time_frame = None
            print(prompt)  # "total workorders in the past month"

            # Improved regex pattern that handles both "past X months" and "past month"
            time_matches = re.search(
                r'(last|past|previous)\s+(\d+)?\s*(month|week|day)s?', 
                prompt.lower()
            )
            print(time_matches)  # Should now match

            if time_matches:
                print('Match found')
                # Default to 1 if no number is specified (like "past month")
                num = int(time_matches.group(2)) if time_matches.group(2) else 1
                unit = time_matches.group(3)
                time_frame = num * (30 if unit == 'month' else 7 if unit == 'week' else 1)
                print(f"Time frame: {time_frame} days")  # Should print 30 for "past month"
            
            # If time frame exists but no keywords, it's a time-filtered count
            if time_frame and not self.extract_keywords(prompt):
                date_cutoff = datetime.now() - timedelta(days=time_frame)
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM workorders_workorders WHERE initiation_date >= %s",
                        [date_cutoff]
                    )
                    filtered_count = cursor.fetchone()[0]
                
                time_period = f"last {num} {unit}{'s' if num > 1 else ''}"
                return Response({
                    "answer": f"There are {filtered_count} work orders from the {time_period}.",
                    "statistics": {
                        "exact_count": filtered_count,
                        "analyzed_samples": 0
                    },
                    "sources": []
                })
            # Extract parameters
            keyword, time_frame = self.extract_query_parameters(prompt)
            
            # Get data
            exact_count = self.execute_sql_query('count', keyword, time_frame) if keyword else None
            sql_results = self.execute_sql_query('summary', keyword, time_frame)
            
            # If no results, try a broader search
            if exact_count == 0:
                # Try without time frame first
                if time_frame:
                    exact_count = self.execute_sql_query('count', keyword, None)
                    sql_results = self.execute_sql_query('summary', keyword, None)
                    
                # If still no results, try more general keyword
                if exact_count == 0 and keyword:
                    general_keyword = keyword.split()[0]  # Just use first word
                    exact_count = self.execute_sql_query('count', general_keyword, time_frame)
                    sql_results = self.execute_sql_query('summary', general_keyword, time_frame)
            
            # Prepare context
            context = "\n".join(
                f"WO#{res['id']} | {res['initiation_date'].strftime('%Y-%m-%d')} | "
                f"Equipment: {res['equipment']} | "
                f"Problem: {res['problem'][:200]}"
                for res in sql_results
            ) if sql_results else "No matching work orders found"
            
            # Enhanced prompt
            enhanced_prompt = f"""
            Analyze work orders regarding '{keyword or 'the query'}':

            Statistics:
            - Total matching orders: {exact_count or len(sql_results)}
            - Time frame: {f"last {time_frame} days" if time_frame else "all time"}
            
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
            3. Provide general maintenance advice for this equipment type
            """) + f"\nOriginal question: {prompt}"
            
            # Get LLM response
            result = self.llm(enhanced_prompt)
            
            return Response({
                "answer": result,
                "statistics": {
                    "exact_count": exact_count or len(sql_results),
                    "analyzed_samples": len(sql_results)
                },
                "sources": [
                    {
                        "work_order_id": res['id'],
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
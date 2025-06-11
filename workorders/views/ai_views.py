from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from ..utils.ai_utils import get_vector_store
from rest_framework.permissions import AllowAny
from workorders.models import workorders
import re
import logging
from django.core.cache import cache
from concurrent.futures import ThreadPoolExecutor
from django.db.models import Q

logger = logging.getLogger(__name__)

class AIAgentView(APIView):
    permission_classes = [AllowAny]
    
    def __init__(self):
        # Initialize components that can be reused
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.llm = OpenAI(
            temperature=0.2,
            max_tokens=1000,
            model="gpt-3.5-turbo-instruct"
        )

    def get_database_count(self, keyword):
        """Search across multiple fields with optimized queries"""
        if not keyword:
            return None
            
        cache_key = f"count_{keyword.lower().strip()}"
        if cached := cache.get(cache_key):
            return cached
            
        # Create a query that searches across multiple relevant fields
        query = Q(problem__icontains=keyword)
        query |= Q(equipment__machine__icontains=keyword)
        query |= Q(equipment__machine_type__machine_type__icontains=keyword)
        query |= Q(department__icontains=keyword)
        query |= Q(replaced_part__icontains=keyword)
        query |= Q(remarks__icontains=keyword)
        
        count = workorders.objects.filter(query).count()
        cache.set(cache_key, count, timeout=60*5)  # Cache for 5 minutes
        return count

    def extract_keywords(self, prompt):
        """Enhanced keyword extraction with field-specific patterns"""
        cache_key = f"keywords_{prompt.lower().strip()}"
        if cached := cache.get(cache_key):
            return cached
            
        # Field-specific patterns
        patterns = [
            # Equipment patterns
            r'(machine|equipment)\s+(?:named|called|number)?\s*([^\?\s]+)',
            r'(?:check|analyze|review)\s+([^\?\s]+)\s+(?:machine|equipment)',
            
            # Problem patterns
            r'(?:issue|problem|fault)\s+(?:with|in)?\s*([^\?\s]+)',
            r'what\'?s?\s+wrong\s+with\s+([^\?\s]+)',
            
            # Department patterns
            r'in\s+the\s+([^\?\s]+)\s+(?:department|area)',
            
            # General patterns (keep your existing ones)
            r'(?:workorders?|issues?|problems?)\s+(?:with|for|about)\s+([^\?]+)',
            r'(?:what|which|how many)\s+([^\?]+)\s+(?:workorders?|issues?|problems?)',
            r'([^\?]+)\s+(?:workorders?|issues?|problems?)'
        ]
        
        clean_prompt = re.sub(r'[^\w\s]', '', prompt.lower())
        for pattern in patterns:
            if match := re.search(pattern, clean_prompt):
                keyword = match.group(1).strip()
                # Remove stopwords
                stopwords = {'the', 'a', 'an', 'some', 'any', 'these', 'those', 'with', 'for', 'about'}
                keyword = ' '.join([word for word in keyword.split() if word not in stopwords])
                if keyword:
                    cache.set(cache_key, keyword, timeout=60*15)
                    return keyword
        return None

    def post(self, request):
        prompt = request.data.get('prompt')
        if not prompt:
            return Response({"error": "Prompt is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Parallelize the initial operations
            keyword_future = self.executor.submit(self.extract_keywords, prompt)
            keyword = keyword_future.result()
            
            count_future = self.executor.submit(self.get_database_count, keyword)
            exact_count = count_future.result() if keyword else None
            
            # Get pre-configured vector store
            vector_store = get_vector_store()
            
            # Optimized retriever configuration
            retriever_config = {
                "search_type": "similarity",
                "search_kwargs": {
                    "k": min(exact_count or 20, 20),  # Reduced from 35
                    "score_threshold": 0.65,  # Slightly lower threshold
                    "filter": {"problem": {"$ilike": f"%{keyword.lower()}%"}} if keyword else None
                }
            }
            
            # Streamlined prompt template
            enhanced_prompt = f"""Analyze these work orders regarding '{keyword or 'the query'}':

Key Data:
- Matching orders: {exact_count or 'N/A'}
- Focus areas:
  1. Problem patterns
  2. Equipment involved
  3. Frequency trends
  4. Recommended actions

Question: {prompt}"""
            
            # Use faster chain type
            qa = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",  # Faster than "refine"
                retriever=vector_store.as_retriever(**retriever_config),
                return_source_documents=True
            )
            
            # Execute the chain
            result = qa({"query": enhanced_prompt})
            
            # Format response
            return Response({
                "answer": result["result"],
                "statistics": {
                    "exact_count": exact_count,
                    "analyzed_samples": len(result["source_documents"])
                },
                "sources": [
                    {
                        "work_order_id": doc.metadata.get("id"),
                        "equipment": doc.metadata.get("equipment"),
                        "problem": doc.metadata.get("problem")[:100]  # Truncate
                    } for doc in result["source_documents"]
                ]
            })
            
        except Exception as e:
            logger.error(f"AI Agent Error: {str(e)}", exc_info=True)
            return Response({
                "error": "Processing error",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
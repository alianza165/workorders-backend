# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from ..utils.ai_utils import get_vector_store
from rest_framework.permissions import AllowAny
from workorders.models import workorders
import re

class AIAgentView(APIView):
    permission_classes = [AllowAny]
    
    def extract_keywords(self, prompt):
        """Enhanced keyword extraction that handles multiple question formats"""
        # Convert to lowercase and remove punctuation
        clean_prompt = re.sub(r'[^\w\s]', '', prompt.lower())
        
        # Patterns that capture the main subject of the question
        patterns = [
            r'how many workorders (?:have|with|for) (.*?) (?:problems|issues)',
            r'(?:what|which) (.*?) (?:problems|issues)',
            r'(?:summarize|describe) (.*?) (?:problems|issues)',
            r'(?:about|related to|involving|with|for) (.*?)(?:\?|$)',
            r'workorders (?:about|with|for) (.*?)(?:\?|$)'
        ]
        
        # Try each pattern in order
        for pattern in patterns:
            match = re.search(pattern, clean_prompt)
            if match:
                keyword = match.group(1).strip()
                # Remove common stopwords
                stopwords = {'the', 'a', 'an', 'some', 'any', 'these', 'those'}
                keyword = ' '.join([word for word in keyword.split() if word not in stopwords])
                return keyword if keyword else None
        
        # Fallback: look for nouns after question words
        question_words = {'how many', 'what', 'which', 'summarize', 'describe'}
        words = clean_prompt.split()
        for i, word in enumerate(words):
            if word in question_words and i+1 < len(words):
                return words[i+1]
        
        return None
    
    def get_database_count(self, keyword):
        """Get accurate count from database"""
        return workorders.objects.filter(problem__icontains=keyword).count()
    
    def post(self, request):
        prompt = request.data.get('prompt')
        if not prompt:
            return Response({"error": "Prompt is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            keyword = self.extract_keywords(prompt)
            exact_count = self.get_database_count(keyword) if keyword else None
            
            vector_store = get_vector_store()
            
            # Configure retriever to prioritize keyword matches
            retriever_config = {
                "search_type": "similarity_score_threshold",
                "search_kwargs": {
                    "k": min(exact_count, 35) if exact_count else 35,  # Don't exceed actual count
                    "score_threshold": 0.7,  # Higher threshold
                    "filter": {"problem": {"$contains": keyword.lower()}} if keyword else None
            }
            }
            
            # Enhanced prompt that knows about the exact count
            enhanced_prompt = f"""
            Analyze work orders related to: {keyword or 'the query'}
            Exact matching work orders: {exact_count or 'Not calculated'}
            
            Provide:
            1. Problem patterns
            2. Equipment involved
            3. Time trends
            4. Recommended actions
            
            Question: {prompt}
            """
            
            qa = RetrievalQA.from_chain_type(
                llm=OpenAI(temperature=0.2, max_tokens=1000),
                chain_type="refine",  # Better for combining information
                retriever=vector_store.as_retriever(**retriever_config),
                return_source_documents=True
            )
            
            result = qa({"query": enhanced_prompt})
            
            # Format response
            response = {
                "answer": result["result"],
                "statistics": {
                    "exact_count": exact_count,
                    "analyzed_samples": len(result["source_documents"])
                },
                "sources": [
                    {
                        "work_order_id": doc.metadata.get("id"),
                        "equipment": doc.metadata.get("equipment"),
                        "problem": doc.metadata.get("problem")
                    } for doc in result["source_documents"]]
            }
            
            return Response(response)
            
        except Exception as e:
            return Response({
                "error": str(e),
                "detail": "Error processing request"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
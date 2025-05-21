# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from ..utils.ai_utils import get_vector_store
from rest_framework.permissions import AllowAny

class AIAgentView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        prompt = request.data.get('prompt')
        if not prompt:
            return Response({"error": "Prompt is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            vector_store = get_vector_store()
            
            # Create a more specific prompt template
            enhanced_prompt = f"""
            You are a work order assistant for a manufacturing facility. 
            Answer questions based on the following work order context.
            
            Question: {prompt}
            
            Provide specific details from work orders when possible, including:
            - Equipment involved
            - Parts replaced
            - Problem descriptions
            - Timelines
            """
            
            qa = RetrievalQA.from_chain_type(
                llm=OpenAI(temperature=0.3),
                chain_type="stuff",
                retriever=vector_store.as_retriever(
                    search_type="similarity_score_threshold",
                    search_kwargs={
                        "k": 35,  # Number of documents to return
                        "score_threshold": 0.7  # Minimum similarity score
                    }
                ),
                return_source_documents=True
            )
            
            result = qa({"query": enhanced_prompt})
            
            # Format the response better
            if not result["source_documents"]:
                return Response({
                    "answer": "I couldn't find relevant work orders matching your query.",
                    "sources": []
                })
            
            return Response({
                "answer": result["result"],
                "sources": [
                    {
                        "work_order_id": doc.metadata.get("id"),
                        "equipment": doc.metadata.get("equipment"),
                        "problem_summary": doc.metadata.get("problem")
                    } 
                    for doc in result["source_documents"]
                ]
            })
            
        except Exception as e:
            return Response({
                "error": str(e),
                "detail": "Ensure work orders are loaded into vector store (run load_ai_data)"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
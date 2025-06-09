# workorders/utils/ai_utils.py
from langchain.docstore.document import Document
from langchain.vectorstores import PGVector
from langchain.embeddings import OpenAIEmbeddings
from django.conf import settings
from workorders.models import workorders, Equipment
import re

def generate_workorder_documents():
    """More compact document format with better metadata"""
    documents = []
    for wo in workorders.objects.all().select_related('equipment'):
        doc_text = (
            f"WO#{wo.id}|{wo.initiation_date.date()}|"
            f"{wo.equipment.machine if wo.equipment else 'None'}|"
            f"{wo.problem[:200]}"  # Truncate problem description
        )
        metadata = {
            "id": wo.id,
            "problem": wo.problem.lower(),  # Full problem in lowercase for case-insensitive search
            "equipment": wo.equipment.machine if wo.equipment else None,
            "date": str(wo.initiation_date.date()),
            "department": wo.department
        }
        documents.append(Document(page_content=doc_text, metadata=metadata))
    return documents

def get_vector_store():
    """Vector store with optimized configuration"""
    return PGVector(
        connection_string=f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
        embedding_function=OpenAIEmbeddings(),
        collection_name="workorder_embeddings",
        distance_strategy="cosine"
    )

def initialize_vector_store():
    """Initialize with progress tracking"""
    from tqdm import tqdm
    vector_store = get_vector_store()
    documents = generate_workorder_documents()
    
    # Batch insert for large datasets
    batch_size = 100
    for i in tqdm(range(0, len(documents), batch_size)):
        vector_store.add_documents(documents[i:i+batch_size])
    
    return vector_store
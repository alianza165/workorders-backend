# workorders/utils/ai_utils.py
from langchain.docstore.document import Document
from langchain.vectorstores import PGVector
from langchain.embeddings import OpenAIEmbeddings
from django.conf import settings
from workorders.models import workorders, Equipment, Part, Type_of_Work
import os

def generate_workorder_documents():
    documents = []
    for wo in workorders.objects.all().select_related('equipment', 'part', 'type_of_work'):
        doc_text = f"""
        Work Order ID: {wo.id}
        Initiation Date: {wo.initiation_date}
        Department: {wo.department}
        Problem: {wo.problem}
        Equipment: {wo.equipment.machine if wo.equipment else 'None'}
        Equipment Type: {wo.equipment.machine_type.machine_type if wo.equipment else 'None'}
        Part: {wo.part.name if wo.part else 'None'}
        Type of Work: {wo.type_of_work.type_of_work if wo.type_of_work else 'None'}
        Status: {wo.work_status.work_status if wo.work_status else 'None'}
        Closing Remarks: {wo.closing_remarks if wo.closing_remarks else 'None'}
        """
        metadata = {
            "id": wo.id,
            "department": wo.department,
            "equipment": wo.equipment.machine if wo.equipment else None,
            "problem": wo.problem[:100]  # Store first 100 chars of problem
        }
        documents.append(Document(page_content=doc_text, metadata=metadata))
    return documents

def get_vector_store():
    CONNECTION_STRING = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    return PGVector(
        connection_string=CONNECTION_STRING,
        embedding_function=OpenAIEmbeddings(),
        collection_name="workorder_embeddings"
    )

def initialize_vector_store():
    vector_store = get_vector_store()
    documents = generate_workorder_documents()
    vector_store.add_documents(documents)
    return vector_store
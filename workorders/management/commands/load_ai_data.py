from django.core.management.base import BaseCommand
from workorders.utils.ai_utils import initialize_vector_store

class Command(BaseCommand):
    help = 'Load work order data into AI vector store'

    def handle(self, *args, **options):
        self.stdout.write("Loading work orders into vector store...")
        initialize_vector_store()
        self.stdout.write(self.style.SUCCESS("Successfully loaded work orders"))
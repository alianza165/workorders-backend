# Generated by Django 5.2 on 2025-06-17 07:41

from django.db import migrations
from django.contrib.postgres.operations import CreateExtension


class Migration(migrations.Migration):

    dependencies = [
        ('workorders', '0004_auto_20250521_1310'),
    ]

    operations = [
        CreateExtension('pg_trgm'),
        migrations.RunSQL(
            "CREATE INDEX workorders_problem_gin_idx ON workorders_workorders USING gin (problem gin_trgm_ops);",
            "DROP INDEX IF EXISTS workorders_problem_gin_idx;"
        ),
    ]

# Generated by Django 5.2 on 2025-06-22 12:12

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workorders', '0004_auto_20250521_1310'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserPrompt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prompt', models.TextField()),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('response', models.TextField(blank=True, null=True)),
                ('metadata', models.JSONField(default=dict)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterModelOptions(
            name='workorders',
            options={'ordering': ['-initiation_date']},
        ),
        migrations.AddIndex(
            model_name='workorders',
            index=models.Index(fields=['initiation_date'], name='workorders_init_date_idx'),
        ),
        migrations.AddIndex(
            model_name='workorders',
            index=models.Index(fields=['department'], name='workorders_dept_idx'),
        ),
        migrations.AddIndex(
            model_name='workorders',
            index=models.Index(fields=['equipment'], name='workorders_equip_idx'),
        ),
        migrations.AddIndex(
            model_name='workorders',
            index=models.Index(fields=['part'], name='workorders_part_idx'),
        ),
        migrations.AddIndex(
            model_name='workorders',
            index=models.Index(fields=['type_of_work'], name='workorders_work_type_idx'),
        ),
        migrations.AddIndex(
            model_name='workorders',
            index=models.Index(fields=['work_status'], name='workorders_status_idx'),
        ),
        migrations.AddField(
            model_name='userprompt',
            name='user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
    ]

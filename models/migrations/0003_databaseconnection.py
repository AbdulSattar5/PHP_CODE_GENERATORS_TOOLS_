# Generated migration for DatabaseConnection model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('models', '0002_alter_generatedcode_code_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='DatabaseConnection',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('db_type', models.CharField(choices=[('mysql', 'MySQL'), ('postgresql', 'PostgreSQL'), ('sqlite', 'SQLite'), ('mssql', 'SQL Server')], max_length=20)),
                ('host', models.CharField(max_length=255)),
                ('port', models.IntegerField()),
                ('database', models.CharField(max_length=255)),
                ('username', models.CharField(max_length=255)),
                ('password', models.CharField(max_length=500)),
                ('is_connected', models.BooleanField(default=False)),
                ('last_tested', models.DateTimeField(blank=True, null=True)),
                ('connection_error', models.TextField(blank=True)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='database_connections', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'database_connections',
                'ordering': ['-created_at'],
            },
        ),
    ]

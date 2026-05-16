"""
Database models for GenCode AI project management
"""

from django.db import models
from django.contrib.auth.models import User
import uuid
import json


class Project(models.Model):
    """
    User projects for organizing generated code
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'projects'
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.name


class GeneratedCode(models.Model):
    """
    Stores generated code files
    """
    CODE_TYPES = [
        ('complete_php', 'Complete PHP'),
        # DEPRECATED: Removed separate file types - now only generating complete inline PHP
        # ('sql', 'SQL'),
        # ('php', 'PHP'),
        # ('html', 'HTML'),
        # ('css', 'CSS'),
        # ('js', 'JavaScript'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='generated_codes')
    code_type = models.CharField(max_length=15, choices=CODE_TYPES)
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    code_content = models.TextField()
    
    # Metadata
    intent_data = models.JSONField(default=dict, blank=True)
    patterns_used = models.JSONField(default=dict, blank=True)
    validation_score = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'generated_codes'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.project.name} - {self.file_name}"


class CompanyStandards(models.Model):
    """
    Stores company coding standards
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    content = models.TextField()
    
    # Parsed standards
    php_version = models.CharField(max_length=20, blank=True)
    framework = models.CharField(max_length=50, blank=True)
    css_framework = models.CharField(max_length=50, blank=True)
    db_engine = models.CharField(max_length=20, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'company_standards'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class CompanyCodebase(models.Model):
    """
    Stores uploaded company codebases for pattern learning
    """
    INDEX_STATUSES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    upload_path = models.CharField(max_length=500)
    
    # Indexing status
    is_indexed = models.BooleanField(default=False)
    index_status = models.CharField(max_length=20, choices=INDEX_STATUSES, default='pending')
    index_error = models.CharField(max_length=255, blank=True)
    total_files = models.IntegerField(default=0)
    indexed_files = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'company_codebases'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class PatternMemory(models.Model):
    """
    Persistent, entity-neutral pattern memory extracted from a company codebase.
    Retrieval is keyed by form type and requested features instead of filenames.
    """

    PATTERN_TYPES = [
        ('CRUD_PATTERN', 'CRUD Pattern'),
        ('MASTER_DETAIL_PATTERN', 'Master Detail Pattern'),
        ('AJAX_PATTERN', 'AJAX Pattern'),
        ('VALIDATION_PATTERN', 'Validation Pattern'),
        ('SELECT2_PATTERN', 'Select2 Pattern'),
        ('TEMPLATE_PATTERN', 'Template Pattern'),
        ('SESSION_PATTERN', 'Session Pattern'),
        ('SECURITY_PATTERN', 'Security Pattern'),
    ]

    FORM_TYPES = [
        ('ALL', 'All'),
        ('SIMPLE', 'Simple'),
        ('MASTER_DETAIL', 'Master Detail'),
        ('DEPENDENT', 'Dependent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pattern_memories')
    codebase = models.ForeignKey(CompanyCodebase, on_delete=models.CASCADE, related_name='pattern_memories')
    pattern_type = models.CharField(max_length=40, choices=PATTERN_TYPES)
    form_type = models.CharField(max_length=20, choices=FORM_TYPES, default='ALL')
    feature_signature = models.CharField(max_length=255, blank=True, default='base')
    payload = models.JSONField(default=dict, blank=True)
    required_functions = models.JSONField(default=list, blank=True)
    structure_skeleton = models.JSONField(default=dict, blank=True)
    constraints = models.JSONField(default=list, blank=True)
    examples = models.JSONField(default=list, blank=True)
    weight = models.FloatField(default=1.0)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)
    contamination_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pattern_memory'
        ordering = ['pattern_type', 'form_type', '-weight', '-updated_at']
        unique_together = ('codebase', 'pattern_type', 'form_type', 'feature_signature')

    def __str__(self):
        return f"{self.codebase.name} - {self.pattern_type} ({self.form_type})"


class PatternLearningEvent(models.Model):
    """
    Self-learning feedback record for strict ERP generation attempts.
    Stores observability snapshots for success and failure paths.
    """

    OUTCOME_TYPES = [
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('contamination', 'Contamination'),
        ('low_coverage', 'Low Coverage'),
        ('missing_memory', 'Missing Memory'),
        ('contract_reject', 'Contract Reject'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pattern_learning_events')
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pattern_learning_events'
    )
    codebase = models.ForeignKey(
        CompanyCodebase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pattern_learning_events'
    )
    pattern_combo_signature = models.CharField(max_length=255, blank=True)
    selected_patterns = models.JSONField(default=list, blank=True)
    outcome = models.CharField(max_length=20, choices=OUTCOME_TYPES)
    phase = models.CharField(max_length=50, blank=True)
    form_type = models.CharField(max_length=20, blank=True)
    feature_signature = models.CharField(max_length=255, blank=True)
    entity_name = models.CharField(max_length=255, blank=True)
    retrieval_quality = models.FloatField(default=0.0)
    pattern_coverage = models.FloatField(default=0.0)
    validator_errors = models.JSONField(default=list, blank=True)
    section_sizes = models.JSONField(default=dict, blank=True)
    top_candidates = models.JSONField(default=list, blank=True)
    failure_reason = models.TextField(blank=True)
    is_blacklisted_combo = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pattern_learning_events'
        ordering = ['-created_at']

    def __str__(self):
        target = self.entity_name or self.form_type or 'unknown'
        return f"{self.outcome} - {target}"


class ConversationHistory(models.Model):
    """
    Stores chat conversation history for each project
    """
    ROLES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='conversations')
    role = models.CharField(max_length=10, choices=ROLES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'conversation_history'
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.project.name} - {self.role} - {self.timestamp}"


class DatabaseConnection(models.Model):
    """
    Stores user's database connection credentials
    """
    DB_TYPES = [
        ('mysql', 'MySQL'),
        ('postgresql', 'PostgreSQL'),
        ('sqlite', 'SQLite'),
        ('mssql', 'SQL Server'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='database_connections')
    name = models.CharField(max_length=255)
    
    # Connection details
    db_type = models.CharField(max_length=20, choices=DB_TYPES)
    host = models.CharField(max_length=255)
    port = models.IntegerField()
    database = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=500)  # Encrypted in production
    
    # Status
    is_connected = models.BooleanField(default=False)
    last_tested = models.DateTimeField(null=True, blank=True)
    connection_error = models.TextField(blank=True)
    
    # Usage
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'database_connections'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.db_type})"

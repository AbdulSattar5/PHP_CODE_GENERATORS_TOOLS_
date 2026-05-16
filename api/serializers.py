# api/serializers.py

from rest_framework import serializers
from models.project import Project, GeneratedCode, CompanyStandards, CompanyCodebase, ConversationHistory, DatabaseConnection
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    """
    User serializer
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class ProjectSerializer(serializers.ModelSerializer):
    """
    Project serializer
    """
    user = UserSerializer(read_only=True)
    generated_codes_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Project
        fields = [
            'id', 'user', 'name', 'description',
            'created_at', 'updated_at', 'generated_codes_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_generated_codes_count(self, obj):
        return obj.generated_codes.count()


class GeneratedCodeSerializer(serializers.ModelSerializer):
    """
    Generated code serializer
    """
    class Meta:
        model = GeneratedCode
        fields = [
            'id', 'project', 'code_type', 'file_name', 'file_path',
            'code_content', 'intent_data', 'patterns_used',
            'validation_score', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CompanyStandardsSerializer(serializers.ModelSerializer):
    """
    Company standards serializer
    """
    class Meta:
        model = CompanyStandards
        fields = [
            'id', 'user', 'name', 'file_path', 'content',
            'php_version', 'framework', 'css_framework', 'db_engine',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CompanyCodebaseSerializer(serializers.ModelSerializer):
    """
    Company codebase serializer
    """
    indexing_progress = serializers.SerializerMethodField()
    
    class Meta:
        model = CompanyCodebase
        fields = [
            'id', 'user', 'name', 'upload_path',
            'is_indexed', 'index_status', 'index_error',
            'total_files', 'indexed_files',
            'indexing_progress', 'created_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'is_indexed',
            'index_status', 'index_error',
            'total_files', 'indexed_files',
        ]
    
    def get_indexing_progress(self, obj):
        if obj.total_files == 0:
            return 0
        return (obj.indexed_files / obj.total_files) * 100


class ConversationHistorySerializer(serializers.ModelSerializer):
    """
    Conversation history serializer
    """
    class Meta:
        model = ConversationHistory
        fields = ['id', 'project', 'role', 'content', 'timestamp']
        read_only_fields = ['id', 'timestamp']


class CodeGenerationRequestSerializer(serializers.Serializer):
    """
    Code generation request serializer
    """
    user_request = serializers.CharField(
        required=True,
        help_text="Natural language description of the code to generate"
    )
    project_id = serializers.UUIDField(
        required=True,
        help_text="Project ID to associate the generated code with"
    )
    codebase_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Codebase ID to use for pattern retrieval (if multiple codebases exist)"
    )
    use_company_patterns = serializers.BooleanField(
        default=True,
        help_text="Whether to use uploaded company code patterns"
    )
    use_standards = serializers.BooleanField(
        default=True,
        help_text="Whether to apply company coding standards"
    )
    auto_execute_sql = serializers.BooleanField(
        default=False,
        help_text="Whether to automatically execute generated SQL"
    )
    database_connection_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optional database connection ID for SQL generation"
    )


class CodeGenerationResponseSerializer(serializers.Serializer):
    """
    🆕 SIMPLIFIED: Code generation response serializer for complete PHP only
    """
    status = serializers.CharField()
    message = serializers.CharField()
    project_id = serializers.UUIDField()
    generated_files = serializers.DictField(child=serializers.CharField())  # Only 'complete_php' key
    generated_files_info = serializers.DictField(required=False)  # File size info
    file_structure = serializers.DictField()
    deployment_guide = serializers.CharField()
    validation_score = serializers.FloatField()
    validation_result = serializers.DictField()
    download_url = serializers.URLField(required=False)


class FileUploadSerializer(serializers.Serializer):
    """
    File upload serializer
    """
    file = serializers.FileField(
        required=True,
        help_text="File to upload (zip for codebase, md for standards)"
    )
    name = serializers.CharField(
        required=True,
        max_length=255,
        help_text="Name for the uploaded resource"
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional description"
    )


class DatabaseConnectionSerializer(serializers.ModelSerializer):
    """
    Database connection serializer
    """
    class Meta:
        model = DatabaseConnection
        fields = [
            'id', 'name', 'db_type', 'host', 'port', 'database',
            'username', 'password', 'is_connected', 'last_tested', 'connection_error',
            'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_connected', 'last_tested', 'connection_error']
        extra_kwargs = {
            'password': {'write_only': True}
        }


class DatabaseConnectionDetailSerializer(serializers.ModelSerializer):
    """
    Database connection detail serializer (includes password for updates)
    """
    class Meta:
        model = DatabaseConnection
        fields = [
            'id', 'name', 'db_type', 'host', 'port', 'database',
            'username', 'password', 'is_connected', 'last_tested',
            'connection_error', 'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_connected', 'last_tested', 'connection_error']

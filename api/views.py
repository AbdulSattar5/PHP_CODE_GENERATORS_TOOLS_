"""
API views for GenCode AI
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.files import File
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from asgiref.sync import async_to_sync
import threading
import tempfile

from models.project import (
    Project, GeneratedCode, CompanyStandards, 
    CompanyCodebase, ConversationHistory, DatabaseConnection
)
from .serializers import (
    ProjectSerializer, GeneratedCodeSerializer,
    CompanyStandardsSerializer, CompanyCodebaseSerializer,
    ConversationHistorySerializer, CodeGenerationRequestSerializer,
    CodeGenerationResponseSerializer, FileUploadSerializer,
    DatabaseConnectionSerializer
)
import logging
import os
import re
import glob
import zipfile
import shutil
from pathlib import Path
from agents.utils.runtime_config import get_csv_setting, get_int_setting
from .public_safety import (
    build_config_status,
    build_setup_status,
    safe_index_error_message,
    sanitize_public_metadata,
    sanitize_public_text,
)

logger = logging.getLogger(__name__)
DEMO_MODE_ENABLED = getattr(settings, 'DEMO_MODE', False)
SUPPORTED_CODE_EXTENSIONS = {'.php', '.html', '.htm', '.css', '.js', '.sql'}

try:
    from agents.graph.workflow import code_generation_workflow
    from agents.vectorstore.code_ingestion import (
        CodeIngestionPipeline,
        _to_windows_long_path,
        _from_windows_long_path,
    )
    from agents.utils.file_handler import StandardsFileHandler
    AGENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Agent modules not available: {e}")
    AGENTS_AVAILABLE = False
    _to_windows_long_path = lambda path: path
    _from_windows_long_path = lambda path: path


def _friendly_error_response(message, http_status=status.HTTP_422_UNPROCESSABLE_ENTITY, **extra):
    payload = {
        'status': 'error',
        'error': sanitize_public_text(message),
        'message': sanitize_public_text(message),
    }
    if extra:
        payload.update(extra)
    return Response(payload, status=http_status)


def _project_is_selected_for_user(user, selected_project_id):
    if not selected_project_id or not getattr(user, 'is_authenticated', False):
        return False
    return Project.objects.filter(user=user, id=selected_project_id).exists()


def _build_generation_setup_context(user, selected_project_id=None):
    setup_status = build_setup_status(user, selected_project_id=selected_project_id)
    setup_status['project_selected'] = _project_is_selected_for_user(user, selected_project_id)
    return setup_status


# ==================== 
# AUTHENTICATION VIEWS
# ==================== 

def home_view(request):
    """
    Landing page
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home.html')


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    User login
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'login.html')


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Public self-service registration for demo/public deployments.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        confirm_password = request.POST.get('confirm_password') or ''

        if not username or not password:
            messages.error(request, 'Username and password are required.')
        elif password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'That username is already in use.')
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account is ready.')
            return redirect('dashboard')

    return render(request, 'register.html')


@login_required
def logout_view(request):
    """
    User logout
    """
    logout(request)
    messages.success(request, 'You have been logged out successfully')
    return redirect('home')


# ==================== 
# MAIN VIEWS
# ==================== 

@login_required
def dashboard_view(request):
    """
    User dashboard
    """
    # Get user statistics
    projects_count = Project.objects.filter(user=request.user).count()
    codebases_count = CompanyCodebase.objects.filter(user=request.user).count()
    standards_count = CompanyStandards.objects.filter(user=request.user).count()
    
    # Get recent projects
    recent_projects = Project.objects.filter(user=request.user).order_by('-updated_at')[:5]
    
    # Get recent codebases
    recent_codebases = CompanyCodebase.objects.filter(user=request.user).order_by('-created_at')[:3]
    
    context = {
        'projects_count': projects_count,
        'codebases_count': codebases_count,
        'standards_count': standards_count,
        'recent_projects': recent_projects,
        'recent_codebases': recent_codebases,
    }
    
    return render(request, 'dashboard.html', context)


@login_required
def projects_view(request):
    """
    Projects list page
    """
    projects = Project.objects.filter(user=request.user).order_by('-updated_at')
    
    context = {
        'projects': projects
    }
    
    return render(request, 'projects.html', context)


@login_required
def code_generation_view(request):
    """
    Code generation page
    """
    projects = Project.objects.filter(user=request.user).order_by('-updated_at')
    selected_project_id = request.GET.get('project')

    context = {
        'projects': projects,
        'generation_setup': _build_generation_setup_context(
            request.user,
            selected_project_id=selected_project_id,
        ),
        'selected_project_id': selected_project_id if _project_is_selected_for_user(request.user, selected_project_id) else '',
    }
    
    return render(request, 'code_generation.html', context)


@login_required
def codebase_upload_view(request):
    """
    Company codebase upload page
    """
    codebases = CompanyCodebase.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'codebases': codebases
    }
    
    return render(request, 'codebase_upload.html', context)


@login_required
def standards_upload_view(request):
    """
    Coding standards upload page
    """
    standards = CompanyStandards.objects.filter(user=request.user).order_by('-created_at')
    active_standards = CompanyStandards.objects.filter(user=request.user, is_active=True).first()
    
    context = {
        'standards': standards,
        'active_standards': active_standards
    }
    
    return render(request, 'standards_upload.html', context)


@login_required
def database_connections_view(request):
    """
    Database connections management page
    """
    return render(request, 'database_connections.html')


@login_required
def settings_view(request):
    """
    User settings page
    """
    return render(request, 'settings.html', {
        'config_status': build_config_status(),
    })


@login_required
def profile_view(request):
    """
    User profile page
    """
    return render(request, 'profile.html')


# ==================== 
# API VIEWSETS
# ==================== 

class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing projects
    """
    serializer_class = ProjectSerializer
    permission_classes = [] if DEMO_MODE_ENABLED else [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.is_authenticated:
            return Project.objects.filter(user=self.request.user)
        if not DEMO_MODE_ENABLED:
            return Project.objects.none()

        # For demo mode, show projects of demo_user if exists
        from django.contrib.auth.models import User
        try:
            demo_user = User.objects.get(username='demo_user')
            return Project.objects.filter(user=demo_user)
        except User.DoesNotExist:
            return Project.objects.none()
    
    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
            return

        if not DEMO_MODE_ENABLED:
            raise PermissionDenied("Authentication required")

        # For demo purposes, create with a default user
        from django.contrib.auth.models import User
        default_user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={'email': 'demo@example.com'}
        )
        serializer.save(user=default_user)
    
    @action(detail=True, methods=['get'])
    def generated_codes(self, request, pk=None):
        """
        Get all generated codes for a project
        """
        project = self.get_object()
        codes = project.generated_codes.all()
        serializer = GeneratedCodeSerializer(codes, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def conversation_history(self, request, pk=None):
        """
        Get conversation history for a project
        """
        project = self.get_object()
        conversations = project.conversations.all()
        serializer = ConversationHistorySerializer(conversations, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['delete'])
    def clear_history(self, request, pk=None):
        """
        Clear conversation history for a project
        """
        project = self.get_object()
        deleted_count = project.conversations.all().delete()[0]
        return Response({
            'message': f'Deleted {deleted_count} conversation entries'
        })
    
    @action(detail=True, methods=['post'])
    def download_code(self, request, pk=None):
        """
        Download all generated code as zip
        """
        project = self.get_object()
        
        try:
            zip_path = self._create_project_zip(project)
            
            return Response({
                'download_url': f'/api/projects/{pk}/download-file/',
                'zip_path': zip_path,
                'message': 'Zip file created successfully'
            })
            
        except Exception as e:
            logger.error(f"Error creating zip: {str(e)}")
            return _friendly_error_response(
                'Failed to create zip file.',
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    def _create_project_zip(self, project):
        """
        Create a zip file of all generated code
        """
        from django.conf import settings
        
        # Create temp directory for zip
        temp_dir = os.path.join(settings.GENERATED_CODE_DIR, 'temp', str(project.id))
        os.makedirs(temp_dir, exist_ok=True)
        
        # Get all generated codes
        codes = project.generated_codes.all()
        
        # Create directory structure
        for code in codes:
            file_path = os.path.join(temp_dir, code.file_path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code.code_content)
        
        # Create zip
        zip_filename = f"{project.name.replace(' ', '_')}_{project.id}.zip"
        zip_path = os.path.join(settings.GENERATED_CODE_DIR, zip_filename)
        
        shutil.make_archive(
            zip_path.replace('.zip', ''),
            'zip',
            temp_dir
        )
        
        # Clean up temp directory
        shutil.rmtree(temp_dir)
        
        return zip_path


class CodeGenerationViewSet(viewsets.ViewSet):
    """
    ViewSet for code generation operations
    """
    permission_classes = [] if DEMO_MODE_ENABLED else [IsAuthenticated]
    parser_classes = [JSONParser]
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """
        Generate code based on user request
        ðŸ†• ISSUE #6 FIX: Added server-side lock to prevent concurrent requests
        """
        serializer = CodeGenerationRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = serializer.validated_data
        requested_codebase_id = str(validated_data.get('codebase_id')) if validated_data.get('codebase_id') else None
        selected_codebase_id = requested_codebase_id

        if not request.user.is_authenticated and not DEMO_MODE_ENABLED:
            return Response({
                'error': 'Authentication required'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get project
        try:
            if self.request.user.is_authenticated:
                project = Project.objects.get(
                    id=validated_data['project_id'],
                    user=self.request.user
                )
            else:
                # For demo purposes, use default user
                from django.contrib.auth.models import User
                default_user, created = User.objects.get_or_create(
                    username='demo_user',
                    defaults={'email': 'demo@example.com'}
                )
                project = Project.objects.get(
                    id=validated_data['project_id'],
                    user=default_user
                )
        except Project.DoesNotExist:
            return Response({
                'error': 'Project not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # ðŸ†• ISSUE #6 FIX: Server-side lock to prevent concurrent requests
        user_id = request.user.id if request.user.is_authenticated else 'demo'
        effective_user_id = str(request.user.id) if request.user.is_authenticated else str(project.user_id)
        setup_status = build_setup_status(request.user, selected_project_id=str(project.id))

        if not getattr(settings, 'OPENAI_API_KEY_CONFIGURED', False):
            return _friendly_error_response(
                settings.OPENAI_REQUIRED_MESSAGE,
                setup_status=setup_status,
            )

        user_codebases = CompanyCodebase.objects.filter(user_id=int(effective_user_id))
        indexed_codebases = user_codebases.filter(is_indexed=True, index_status='ready')
        failed_codebases = user_codebases.filter(index_status='failed')

        if validated_data.get('use_company_patterns', True):
            if not user_codebases.exists():
                return _friendly_error_response(
                    'Please upload your own company codebase first.',
                    setup_status=setup_status,
                )
            if failed_codebases.exists() and not indexed_codebases.exists():
                return _friendly_error_response(
                    settings.INDEXING_FAILED_MESSAGE,
                    setup_status=setup_status,
                )
            if not indexed_codebases.exists():
                return _friendly_error_response(
                    settings.CODEBASE_REQUIRED_MESSAGE,
                    setup_status=setup_status,
                )

        if (
            validated_data.get('use_standards', True)
            and not CompanyStandards.objects.filter(user_id=int(effective_user_id), is_active=True).exists()
        ):
            return _friendly_error_response(
                settings.STANDARDS_REQUIRED_MESSAGE,
                setup_status=setup_status,
            )

        # Auto-select strongest indexed codebase when caller did not pin one explicitly.
        if not selected_codebase_id and validated_data.get('use_company_patterns', True):
            try:
                auto_codebases = list(
                    CompanyCodebase.objects
                    .filter(user_id=int(effective_user_id), is_indexed=True)
                    .order_by('-indexed_files', '-created_at')
                )
                auto_codebase = None
                for candidate in auto_codebases:
                    if self._codebase_has_form_templates(
                        user_id=effective_user_id,
                        codebase_id=str(candidate.id)
                    ):
                        auto_codebase = candidate
                        break
                if not auto_codebase and auto_codebases:
                    auto_codebase = auto_codebases[0]

                if auto_codebase:
                    selected_codebase_id = str(auto_codebase.id)
                    logger.info(
                        f"🎯 Auto-selected indexed codebase for user {effective_user_id}: "
                        f"{selected_codebase_id} ({auto_codebase.indexed_files}/{auto_codebase.total_files} files)"
                    )
            except Exception as auto_codebase_error:
                logger.warning(f"Auto codebase selection skipped: {auto_codebase_error}")

        # Normalize explicitly supplied codebase ownership/indexing.
        if selected_codebase_id:
            try:
                selected_codebase = CompanyCodebase.objects.get(id=selected_codebase_id)
                if selected_codebase.user_id != int(effective_user_id):
                    logger.warning(
                        f"Codebase {selected_codebase_id} does not belong to user {effective_user_id}; ignoring selection"
                    )
                    selected_codebase_id = None
                elif not selected_codebase.is_indexed:
                    logger.warning(
                        f"Codebase {selected_codebase_id} is not indexed yet; proceeding without codebase-specific retrieval"
                    )
                    selected_codebase_id = None
            except CompanyCodebase.DoesNotExist:
                logger.warning(f"Requested codebase not found: {selected_codebase_id}")
                selected_codebase_id = None
            except Exception as codebase_validation_error:
                logger.warning(f"Codebase validation failed for {selected_codebase_id}: {codebase_validation_error}")
                selected_codebase_id = None

        strict_no_fallback = self._is_no_fallback_request(validated_data['user_request'])
        if strict_no_fallback:
            logger.info("🔒 Strict no-fallback mode enabled for this request")

        if selected_codebase_id and not self._codebase_has_form_templates(
            user_id=effective_user_id,
            codebase_id=selected_codebase_id
        ):
            if strict_no_fallback and requested_codebase_id:
                return Response(
                    self._build_strict_failure_result(
                        error_message=(
                            f"Selected codebase '{selected_codebase_id}' has no frm*.php template files; "
                            "strict no-fallback mode cannot proceed."
                        ),
                        validation_error=(
                            "Strict mode requires at least one frm*.php company template in the selected codebase."
                        ),
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY
                )
            logger.warning(
                "Codebase %s has no frm*.php files; skipping codebase-specific strict generation",
                selected_codebase_id
            )
            if requested_codebase_id:
                selected_codebase_id = None

        lock_key = f"generating_{user_id}_{project.id}"
        lock_timeout = get_int_setting(
            'CODEGEN_GENERATION_LOCK_TIMEOUT',
            'CODEGEN_GENERATION_LOCK_TIMEOUT',
            1800,
            min_value=300,
            max_value=10800
        )

        # Atomic lock to prevent race condition between parallel requests.
        lock_acquired = cache.add(lock_key, timezone.now().isoformat(), timeout=lock_timeout)
        if not lock_acquired:
            logger.warning(f"âš ï¸ Concurrent request blocked for user {user_id}, project {project.id}")
            return Response({
                'error': 'Code generation already in progress for this project. Please wait...'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        try:
            # Save user message to conversation history
            ConversationHistory.objects.create(
                project=project,
                role='user',
                content=validated_data['user_request']
            )
            
            # Execute workflow
            logger.info(f"Starting code generation for project {project.id}")
            
            if not AGENTS_AVAILABLE:
                if strict_no_fallback:
                    result = self._build_strict_failure_result(
                        error_message='Code generation failed: strict no-fallback mode forbids template fallback while agents are unavailable.',
                        validation_error='Agents are unavailable and fallback output is disabled by request'
                    )
                else:
                    # Provide simple fallback code generation
                    result = self._generate_fallback_code(
                        validated_data['user_request'],
                        user_id=effective_user_id,
                        codebase_id=selected_codebase_id
                    )
            else:
                try:
                    # Run async workflow in sync context with database connection
                    result = async_to_sync(code_generation_workflow.execute)(
                        user_request=validated_data['user_request'],
                        project_id=str(project.id),
                        user_id=effective_user_id,
                        codebase_id=selected_codebase_id,
                        database_connection_id=str(validated_data.get('database_connection_id')) if validated_data.get('database_connection_id') else None
                    )

                    strict_erp_meta = ((result.get('metadata') or {}).get('strict_erp') or {})
                    strict_hard_block = bool(
                        strict_erp_meta.get('hard_block')
                        or strict_erp_meta.get('block_generation')
                        or strict_erp_meta.get('block_save')
                    )
                    
                    # If AI generation failed, returned no code, or returned unusable tiny code, use fallback
                    code_map = result.get('code', {}) or {}
                    
                    # ✅ PROMPT 5 FIX: Add integrated_code fallback
                    complete_php = (code_map.get('complete_php') or '').strip()
                    if not complete_php:
                        complete_php = (code_map.get('integrated_code') or '').strip()
                    validation_score = result.get('validation_score', 0) or 0
                    
                    generated_any_code = bool(code_map and any(code_map.values()))

                    default_min_inline_chars = 8000 if selected_codebase_id else 3000
                    min_inline_chars = get_int_setting(
                        'CODEGEN_MIN_INLINE_CHARS',
                        'CODEGEN_MIN_INLINE_CHARS',
                        default_min_inline_chars,
                        min_value=2000,
                        max_value=120000
                    )
                    tiny_inline_output = bool(complete_php) and len(complete_php) < min_inline_chars

                    # FIX #1: Accept code if it was generated and is large enough
                    # Don't reject based on validation_score alone - pattern validator may show 99% but enterprise_validator shows 43%
                    if (not generated_any_code) or tiny_inline_output:
                        if strict_no_fallback or strict_hard_block:
                            logger.error(
                                "AI generation returned invalid output (generated_any=%s, tiny_inline=%s, validation_score=%s, min_inline_chars=%s); strict gating keeps this as hard failure",
                                generated_any_code,
                                tiny_inline_output,
                                validation_score,
                                min_inline_chars
                            )
                            result = self._build_strict_failure_result(
                                error_message=(
                                    result.get('error')
                                    or 'AI generation failed strict validation and no fallback output was returned.'
                                ),
                                validation_error=(
                                    'AI generation output failed strict ERP gating and fallback output is disabled'
                                    if strict_hard_block else
                                    'AI generation output failed strict validation and fallback output is disabled'
                                ),
                                upstream_result=result
                            )
                        else:
                            logger.warning(
                                "AI generation returned invalid output (generated_any=%s, tiny_inline=%s, validation_score=%s, min_inline_chars=%s); using fallback",
                                generated_any_code,
                                tiny_inline_output,
                                validation_score,
                                min_inline_chars
                            )
                            fallback_result = self._generate_fallback_code(
                                validated_data['user_request'],
                                user_id=effective_user_id,
                                codebase_id=selected_codebase_id
                            )
                            result = self._attach_fallback_diagnostics(
                                fallback_result,
                                upstream_result=result,
                                fallback_reason='invalid_ai_output'
                            )
                         
                except Exception as workflow_error:
                    logger.error(f"Workflow execution failed: {str(workflow_error)}")
                    if strict_no_fallback:
                        result = self._build_strict_failure_result(
                            error_message=f"Workflow execution failed in strict no-fallback mode: {workflow_error}",
                            validation_error='Workflow execution failed and fallback output is disabled by request',
                            upstream_result={
                                'error': str(workflow_error),
                                'details': str(workflow_error),
                                'metadata': self._infer_attempt_metadata_from_error(str(workflow_error))
                            }
                        )
                    else:
                        logger.info("Using fallback code generation due to workflow failure")
                        fallback_result = self._generate_fallback_code(
                            validated_data['user_request'],
                            user_id=effective_user_id,
                            codebase_id=selected_codebase_id
                        )
                        result = self._attach_fallback_diagnostics(
                            fallback_result,
                            upstream_result={
                                'error': str(workflow_error),
                                'metadata': {}
                            },
                            fallback_reason='workflow_exception'
                        )
            
            result_code = result.get('code', {}) or {}
            validated_complete_php = (result_code.get('complete_php') or '').strip()
            validation_result = result.get('validation_result', {}) or {}
            approval_status = str(validation_result.get('approval_status', '')).lower()
            validation_passed = bool(
                validation_result.get('validation_passed')
                if 'validation_passed' in validation_result
                else approval_status == 'approved'
            )
            strict_erp_meta = ((result.get('metadata') or {}).get('strict_erp') or {})
            strict_block_save = bool(
                strict_erp_meta.get('hard_block')
                or strict_erp_meta.get('block_save')
            )
            block_save = bool(
                result.get('block_save')
                or strict_block_save
                or validation_result.get('block_save')
                or validation_result.get('block_generation')
            )
            needs_revision = bool(
                strict_erp_meta.get('hard_block')
                or
                validation_result.get('block_generation')
                or validation_result.get('regeneration_required')
                or validation_result.get('needs_revision')
                or approval_status == 'needs_revision'
            )
            workflow_status = str(result.get('status') or '').lower()
            failed_status = workflow_status in {'failed', 'error', 'revision_required'}
            validation_reason = str(
                validation_result.get('validation_reason')
                or result.get('error')
                or ''
            ).strip()
            persistence_integrity_errors = []
            persistence_integrity_error = ''
            if validated_complete_php:
                persistence_integrity_errors = self._collect_persistence_integrity_errors(validated_complete_php)
                if persistence_integrity_errors:
                    persistence_integrity_error = (
                        "Generated code failed persistence integrity gate: "
                        + "; ".join(persistence_integrity_errors[:4])
                    )
                    validation_passed = False
                    block_save = True
                    needs_revision = True
                    validation_reason = "persistence_integrity_failed"
                    existing_errors = validation_result.get('errors')
                    if isinstance(existing_errors, list):
                        merged_errors = existing_errors
                    elif existing_errors:
                        merged_errors = [str(existing_errors)]
                    else:
                        merged_errors = []
                    for issue in persistence_integrity_errors:
                        if issue not in merged_errors:
                            merged_errors.append(issue)
                    validation_result['errors'] = merged_errors
                    validation_result['validation_passed'] = False
                    validation_result['block_save'] = True
                    validation_result['needs_revision'] = True
                    validation_result['approval_status'] = 'needs_revision'
                    validation_result['validation_reason'] = validation_reason
                    logger.error(
                        "❌ Persistence integrity gate blocked save: %s",
                        '; '.join(persistence_integrity_errors)
                    )

            # Auto-execute SQL if requested
            if validated_data.get('auto_execute_sql') and result.get('code', {}).get('sql'):
                sql_result = self._execute_sql(
                    result['code']['sql'],
                    database_connection_id=validated_data.get('database_connection_id')
                )
                result['sql_execution'] = sql_result
            
            generated_files = result.get('code', {}) or {}
            generated_any = bool(generated_files and any(generated_files.values()))
            validation_mode = str(validation_result.get('mode', '')).lower()
            generation_type = str((result.get('metadata', {}) or {}).get('generation_type', '')).lower()
            inline_generation_metadata = (result.get('metadata', {}) or {}).get('inline_generation_metadata', {}) or {}
            inline_fallback_mode = str(inline_generation_metadata.get('fallback_mode', '')).lower()
            result_error = str(result.get('error') or persistence_integrity_error or '').strip()
            strict_hard_block = bool(strict_erp_meta.get('hard_block'))
            # Determine if fallback was actually used (not just mentioned in error messages)
            # Only consider it fallback if:
            # 1. Validation mode explicitly says "fallback" (but NOT "strict_no_fallback" or "no_fallback")
            # 2. Generation type explicitly says "fallback"
            # 3. Inline generation metadata has a fallback_mode set
            # Do NOT consider error messages or modes that indicate fallback was NOT used
            fallback_used = (
                ('fallback' in validation_mode and 'no_fallback' not in validation_mode and 'no-fallback' not in validation_mode) or
                'fallback' in generation_type or
                bool(inline_fallback_mode)
            )

            save_allowed = bool(
                validated_complete_php
                and validation_passed
                and not block_save
                and not needs_revision
                and not failed_status
            )

            if not generated_any:
                response_status = 'error'
                if strict_hard_block:
                    base_message = result_error or 'code generation before output was produced'
                    response_message = f"Strict ERP gate blocked {base_message}".strip()
                else:
                    response_message = result_error or 'Code generation failed - no output produced.'
            elif not save_allowed:
                response_status = 'error'
                if strict_hard_block:
                    base_message = (
                        result_error
                        or validation_reason
                        or 'persistence and requires revision'
                    )
                    response_message = f"Strict ERP validation gate blocked {base_message}".strip()
                else:
                    response_message = (
                        result_error
                        or validation_reason
                        or 'Code generation failed authoritative validation and requires revision.'
                    )
            elif fallback_used:
                response_status = 'warning'
                response_message = result_error or 'Code generated in fallback mode. Review before production use.'
            elif result_error:
                response_status = 'error'
                response_message = result_error
            else:
                response_status = 'success'
                response_message = 'Code generated successfully'

            # Save generated code only when authoritative validation allows persistence.
            if save_allowed:
                self._save_generated_code(project, result)
            elif validated_complete_php and not save_allowed:
                logger.warning(
                    "Skipping persistence due to failed validation "
                    f"(approval_status={approval_status}, validation_passed={validation_passed}, "
                    f"block_save={block_save}, needs_revision={needs_revision}, failed_status={failed_status})"
                )

            # Prepare response
            response_data = {
                'status': response_status,
                'message': sanitize_public_text(response_message),
                'project_id': str(project.id),
                'generated_files': generated_files,  # Return actual code content
                # Backward-compatible alias used by older tooling/scripts.
                'code': generated_files,
                'generated_files_info': {
                    key: f"{len(value) if value else 0} characters"
                    for key, value in generated_files.items()
                },
                'file_structure': result.get('file_structure', {}),
                'deployment_guide': result.get('deployment_guide', ''),
                'validation_score': result.get('validation_score', 0),
                'validation_result': sanitize_public_metadata(validation_result),
                'validation_reason': sanitize_public_text(validation_reason),
                'fallback_used': fallback_used,
                'metadata': sanitize_public_metadata(result.get('metadata', {})),
                'setup_status': setup_status,
            }

            # Save assistant response to conversation history with truthful status.
            history_prefix = {
                'success': 'Generated code successfully',
                'warning': 'Generated code in fallback mode',
                'error': 'Code generation failed'
            }.get(response_status, 'Code generation update')
            files_text = ', '.join(generated_files.keys()) if generated_files else 'none'
            ConversationHistory.objects.create(
                project=project,
                role='assistant',
                content=(
                    f"{history_prefix}. Files: {files_text}. "
                    f"Message: {sanitize_public_text(response_message)}"
                )
            )

            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY if response_status == 'error' else status.HTTP_200_OK

            return Response(response_data, status=http_status)
            
        except Exception as e:
            logger.error(f"Code generation error: {str(e)}", exc_info=True)
            safe_message = sanitize_public_text(
                result.get('error') if 'result' in locals() and isinstance(result, dict) else ''
            ) or 'Code generation failed. Please review your setup and try again.'
            
            # Save error to conversation history
            ConversationHistory.objects.create(
                project=project,
                role='assistant',
                content=f"Error: {safe_message}"
            )
            
            return _friendly_error_response(
                safe_message,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                setup_status=setup_status if 'setup_status' in locals() else {},
            )
        finally:
            # ðŸ†• ISSUE #6 FIX: Always release the lock
            if lock_acquired:
                cache.delete(lock_key)
                logger.info(f"âœ… Released generation lock for user {user_id}, project {project.id}")
    
    def _save_generated_code(self, project, result):
        """
        ðŸ†• SIMPLIFIED: Save only complete PHP file to database
        """
        logger.info(f"=== SAVE COMPLETE PHP CODE ===")
        logger.info(f"Result type: {type(result)}")
        logger.info(f"Result keys: {result.keys() if isinstance(result, dict) else 'NOT A DICT'}")
        
        code_files = result.get('code', {})
        logger.info(f"code_files keys: {code_files.keys() if isinstance(code_files, dict) else 'NOT A DICT'}")
        
        if not code_files:
            logger.error("No complete PHP code to save!")
            return

        complete_php = (code_files.get('complete_php') or '').strip()
        if not complete_php:
            legacy_php = (code_files.get('php') or '').strip()
            if legacy_php:
                complete_php = legacy_php
                code_files['complete_php'] = legacy_php
                logger.warning("Missing complete_php key, using legacy php payload for persistence")
            else:
                logger.error("No complete PHP code to save!")
                return
        intent_data = result.get('intent', {})
        patterns_used = result.get('metadata', {}).get('patterns_used', 0)
        validation_score = result.get('validation_score', 0)
        
        # Get file name from file structure
        feature_name = intent_data.get('database', {}).get('table_name', 'form')
        default_file_name = f"frm{feature_name.title()}.php"
        file_path = result.get('file_structure', {}).get('files', {}).get('complete_php', {}).get('path', default_file_name)
        file_name = os.path.basename(file_path) if file_path else default_file_name
        
        try:
            GeneratedCode.objects.create(
                project=project,
                code_type='complete_php',
                file_name=file_name,
                file_path=file_path,
                code_content=complete_php,
                intent_data=intent_data,
                patterns_used={'count': patterns_used},
                validation_score=validation_score
            )
            logger.info(f"âœ… Saved complete PHP code: {file_name} ({len(complete_php)} chars)")
            logger.info(f"=== SAVED COMPLETE PHP FILE ===")
        except Exception as e:
            logger.error(f"âŒ Failed to save complete PHP: {str(e)}")
            logger.error(f"=== SAVE FAILED ===")

    
    def _execute_sql(self, sql_code, database_connection_id=None):
        """
        Execute SQL code using selected database connection
        """
        try:
            # Get database connection
            if database_connection_id:
                try:
                    db_connection = DatabaseConnection.objects.get(
                        id=database_connection_id,
                        user=self.request.user
                    )
                except DatabaseConnection.DoesNotExist:
                    return {
                        'status': 'error',
                        'message': 'Database connection not found'
                    }
            else:
                # Try to get default connection
                try:
                    db_connection = DatabaseConnection.objects.get(
                        user=self.request.user,
                        is_default=True
                    )
                except DatabaseConnection.DoesNotExist:
                    return {
                        'status': 'not_configured',
                        'message': 'No database connection configured'
                    }
            
            # Check if connection is valid
            if not db_connection.is_connected:
                return {
                    'status': 'error',
                    'message': f'Database connection "{db_connection.name}" is not connected. Please test the connection first.'
                }
            
            # Execute SQL using the database executor
            from agents.utils.database_executor import DatabaseExecutor
            
            executor = DatabaseExecutor(
                db_type=db_connection.db_type,
                host=db_connection.host,
                port=db_connection.port,
                database=db_connection.database,
                username=db_connection.username,
                password=db_connection.password
            )
            
            result = executor.execute(sql_code)
            logger.info(f"âœ… SQL executed on {db_connection.name}: {result.get('statements_executed', 0)} statements")
            return result
            
        except Exception as e:
            logger.error(f"SQL execution error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
            # result = executor.execute(sql_code)
    def _normalize_request_sections(self, user_request: str) -> str:
        """
        Normalize compact one-line prompts into section/bullet-friendly text so
        metadata and field extraction behave the same for single-line or
        multi-line requests.
        """
        request_text = (user_request or "").replace('\r\n', '\n').replace('\r', '\n').strip()
        if not request_text:
            return ''

        section_pattern = (
            r'(?:table|file\s*name|filename|file|title|case\s*type|casetype|'
            r'primary\s*key|master\s*fields|form\s*fields|detail\s*grid|'
            r'relationships?|dependencies?|business\s*validations?|validation\s*rules|'
            r'required\s*company\s*patterns|required\s*patterns|'
            r'operations|crud\s*operations)'
        )
        request_text = re.sub(
            rf'\s+(?={section_pattern}\s*:)',
            '\n',
            request_text,
            flags=re.IGNORECASE
        )
        request_text = re.sub(
            r'\s+(?=-\s*[A-Za-z_][A-Za-z0-9_]*)',
            '\n',
            request_text
        )
        request_text = re.sub(r'\n{3,}', '\n\n', request_text)
        return request_text.strip()

    def _extract_explicit_request_metadata(self, user_request: str):
        """
        Parse canonical metadata from the prompt. Explicit file/table metadata
        must override fuzzy entity guessing during fallback selection.
        """
        request_text = self._normalize_request_sections(user_request)
        lowered = request_text.lower()

        def _extract(pattern: str) -> str:
            match = re.search(pattern, request_text, re.IGNORECASE | re.MULTILINE)
            return match.group(1).strip() if match else ''

        table_name = _extract(r'^\s*(?:[-*]\s*)?table\s*:\s*([A-Za-z][A-Za-z0-9_]*)\s*$')
        file_name = os.path.basename(
            _extract(r'^\s*(?:[-*]\s*)?(?:file\s*name|filename|file)\s*:\s*([A-Za-z0-9_.()\-]+\.php)\s*$')
        )
        title = _extract(r'^\s*(?:[-*]\s*)?title\s*:\s*([A-Za-z][A-Za-z0-9_ \-]*)\s*$')
        case_type = _extract(r'^\s*(?:[-*]\s*)?(?:case\s*type|casetype)\s*:\s*([A-Za-z][A-Za-z0-9_ \-]*)\s*$')

        primary_key = ''
        primary_key_section = re.search(
            r'(?ims)^\s*primary\s*key\s*:\s*(.+?)(?:^\s*[A-Za-z][^:\n]*:\s*|\Z)',
            request_text
        )
        if primary_key_section:
            bullet_match = re.search(
                r'(?im)^\s*[-*]\s*([A-Za-z_][A-Za-z0-9_]*)',
                primary_key_section.group(1)
            )
            if bullet_match:
                primary_key = bullet_match.group(1).strip()
        if not primary_key:
            primary_key = _extract(
                r'^\s*(?:[-*]\s*)?(?:primary\s*key|primary_key)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$'
            )

        primary_entity = ''
        primary_patterns = [
            r'create\s+(?:a|an)?\s*(?:complete\s+)?([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'form\s+for\s+([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)',
            r'\bfrm([a-z][a-z0-9_]*)\b',
        ]
        for pattern in primary_patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                primary_entity = str(match.group(1) or '').strip()
                if primary_entity:
                    break

        module_entity = ''
        if file_name.lower().startswith('frm') and file_name.lower().endswith('.php'):
            module_entity = file_name[3:-4]
        elif table_name.lower().startswith('tbl'):
            module_entity = table_name[3:]
        elif table_name:
            module_entity = table_name
        elif case_type:
            module_entity = case_type
        elif title:
            module_entity = title

        effective_entity = module_entity or title or case_type or primary_entity
        effective_compact = re.sub(r'[^a-z0-9]', '', effective_entity.lower())
        if effective_compact.endswith('master') and len(effective_compact) > 6:
            effective_compact = effective_compact[:-6]

        return {
            'table_name': table_name,
            'file_name': file_name,
            'title': title,
            'case_type': case_type,
            'primary_key': primary_key,
            'primary_entity': primary_entity,
            'module_entity': module_entity,
            'effective_entity': effective_entity,
            'effective_entity_compact': effective_compact,
        }

    def _extract_entity_hints(self, user_request: str):
        request_text = self._normalize_request_sections(user_request).lower()
        if not request_text:
            return []

        hints = []
        request_metadata = self._extract_explicit_request_metadata(user_request)
        metadata_candidates = [
            request_metadata.get('effective_entity'),
            request_metadata.get('module_entity'),
            request_metadata.get('primary_entity'),
        ]
        if request_metadata.get('file_name', '').lower().startswith('frm'):
            metadata_candidates.append(request_metadata['file_name'][3:-4])
        if request_metadata.get('table_name', '').lower().startswith('tbl'):
            metadata_candidates.append(request_metadata['table_name'][3:])
        for candidate in metadata_candidates:
            cleaned = re.sub(r'[^a-z0-9_]', '', str(candidate or '').lower())
            if cleaned:
                hints.append(cleaned)

        patterns = [
            r'create\s+(?:a|an)?\s*(?:complete\s+)?([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'form\s+for\s+([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)',
            r'\bfrm([a-z][a-z0-9_]*)\b',
        ]
        for pattern in patterns:
            for match in re.findall(pattern, request_text, re.IGNORECASE):
                cleaned = re.sub(r'[^a-z0-9_]', '', match or '')
                if cleaned:
                    hints.append(cleaned)

        configured_hints = get_csv_setting(
            'CODEGEN_ENTITY_HINTS',
            'CODEGEN_ENTITY_HINTS',
            default=[]
        )
        for entity in configured_hints:
            if re.search(rf'\b{re.escape(entity.lower())}\b', request_text):
                hints.append(entity.lower())

        stopwords = set(
            word.lower() for word in get_csv_setting(
                'CODEGEN_ENTITY_STOPWORDS',
                'CODEGEN_ENTITY_STOPWORDS',
                default=[
                    'create', 'complete', 'master', 'form', 'with', 'all', 'crud',
                    'operations', 'following', 'fields', 'detail', 'grid', 'include',
                    'company', 'standard', 'patterns', 'generate', 'code', 'table',
                    'tables', 'required', 'and', 'for', 'the', 'from', 'via', 'ajax',
                    'handler'
                ]
            )
        )
        for token in re.findall(r'\b[a-z][a-z0-9_]{2,}\b', request_text):
            if token in stopwords:
                continue
            hints.append(token)

        unique = []
        seen = set()
        for hint in hints:
            lowered = hint.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(hint)
        return unique

    def _is_no_fallback_request(self, user_request: str) -> bool:
        """
        Strict generation is the default enterprise mode.
        Generic/template fallback is only allowed when explicitly opted in.
        """
        request_text = (user_request or '').lower()
        allow_fallback_by_config = str(
            getattr(settings, 'CODEGEN_ALLOW_FALLBACK_OUTPUT', os.getenv('CODEGEN_ALLOW_FALLBACK_OUTPUT', 'false'))
        ).strip().lower() in ('1', 'true', 'yes', 'on')
        if allow_fallback_by_config:
            return False

        allow_signals = [
            'allow fallback',
            'fallback allowed',
            'template fallback allowed',
            'non-strict mode',
            'dev fallback mode',
        ]
        if any(signal in request_text for signal in allow_signals):
            return False

        strict_signals = [
            'no generic fallback output',
            'no generic fallback',
            'fallback usage must be <= 1%',
            'fallback limit: <= 1%',
            'do not return code',
            'strict mode',
            'if any blocker exists',
            'required company patterns (mandatory)',
            'canonical names must match exactly',
            'do not add any extra fields',
        ]
        return True if not request_text else (True if any(signal in request_text for signal in strict_signals) else True)

    def _infer_attempt_metadata_from_error(self, error_text: str):
        metadata = {}
        text = str(error_text or '').strip()
        if not text:
            return metadata

        attempts_match = re.search(r'after\s+(\d+)\s+attempt', text, re.IGNORECASE)
        if attempts_match:
            attempts = int(attempts_match.group(1))
            metadata['attempts_made'] = attempts
            metadata['max_attempts'] = attempts
            metadata['llm_call_failures'] = 0
            metadata['refusal_count'] = attempts if 'refus' in text.lower() else 0
        return metadata

    def _build_strict_failure_result(self, error_message: str, validation_error: str, upstream_result=None):
        metadata = {}
        if isinstance(upstream_result, dict):
            upstream_metadata = upstream_result.get('metadata', {}) or {}
            if isinstance(upstream_metadata, dict):
                metadata.update(upstream_metadata)
            inferred_metadata = self._infer_attempt_metadata_from_error(
                " ".join(
                    part for part in [
                        str(upstream_result.get('error') or '').strip(),
                        str(upstream_result.get('details') or '').strip(),
                        str(error_message or '').strip(),
                    ] if part
                )
            )
            for key, value in inferred_metadata.items():
                metadata.setdefault(key, value)

        return {
            'code': {'complete_php': ''},
            'validation_score': 0,
            'validation_result': {
                'valid': False,
                'mode': 'strict_no_fallback',
                'errors': [validation_error]
            },
            'metadata': metadata,
            'error': error_message
        }

    def _extract_first_form_opening_tag(self, code: str):
        text = str(code or '')
        match = re.search(r'<form\b', text, re.IGNORECASE)
        if not match:
            return None

        start = match.start()
        idx = match.end()
        in_single = False
        in_double = False
        in_php = False
        escape_next = False

        while idx < len(text):
            ch = text[idx]
            nxt = text[idx + 1] if idx + 1 < len(text) else ''

            if in_php:
                if ch == '?' and nxt == '>':
                    in_php = False
                    idx += 2
                    continue
                idx += 1
                continue

            if in_single:
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == "'":
                    in_single = False
                idx += 1
                continue

            if in_double:
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == '"':
                    in_double = False
                idx += 1
                continue

            if ch == '<' and nxt == '?':
                in_php = True
                idx += 2
                continue

            if ch == "'":
                in_single = True
                idx += 1
                continue

            if ch == '"':
                in_double = True
                idx += 1
                continue

            if ch == '>':
                return text[start:idx + 1]

            idx += 1

        return None

    def _has_malformed_form_opening_suffix(self, code: str) -> bool:
        text = str(code or '')
        opening_tag = self._extract_first_form_opening_tag(text)
        if not opening_tag:
            return False

        start = text.lower().find(opening_tag.lower())
        if start < 0:
            start = text.find(opening_tag)
        if start < 0:
            return False

        idx = start + len(opening_tag)
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text) or text[idx] not in ("'", '"'):
            return False
        idx += 1
        while idx < len(text) and text[idx].isspace():
            idx += 1
        return idx < len(text) and text[idx] == '>'

    def _collect_persistence_integrity_errors(self, complete_php: str):
        """
        Final save gate for critical syntax/integrity corruption that can still
        slip through upstream scoring validators.
        """
        code = str(complete_php or '')
        if not code.strip():
            return ["Generated code is empty."]

        errors = []

        form_open_count = len(re.findall(r'<form\b', code, re.IGNORECASE))
        form_close_count = len(re.findall(r'</form>', code, re.IGNORECASE))
        has_form_markup = form_open_count > 0 or form_close_count > 0
        if has_form_markup and (form_open_count != 1 or form_close_count != 1):
            errors.append(
                f"Form boundary invalid (opens={form_open_count}, closes={form_close_count})."
            )

        if has_form_markup and self._has_malformed_form_opening_suffix(code):
            errors.append("Malformed form opening tag detected (stray quote after form tag).")

        script_open_count = len(re.findall(r'<script\b', code, re.IGNORECASE))
        script_close_count = len(re.findall(r'</script>', code, re.IGNORECASE))
        if script_close_count < script_open_count:
            errors.append(
                f"Unbalanced script tags detected (opens={script_open_count}, closes={script_close_count})."
            )

        if re.search(
            r'<script[^>]*\bsrc=["\'][^"\']+["\'][^>]*>\s*[^<\s]',
            code,
            re.IGNORECASE
        ):
            errors.append("Inline JavaScript detected inside external script tag.")

        if re.search(
            r'document\.onkeydown\s*=\s*checkKeycode\s*(?:\r?\n|\s)*\{',
            code,
            re.IGNORECASE
        ):
            errors.append("Malformed document.onkeydown assignment detected.")

        if re.search(
            r'form\.action\s*=\s*["\']\s*<\?php\s+echo\s+\$form2\s*,\s*ENT_QUOTES\)\s*;\s*\?>\s*["\']',
            code,
            re.IGNORECASE
        ):
            errors.append("Malformed form.action JavaScript assignment detected.")

        for maxid_match in re.finditer(r'function\s+maxid\s*\(\)\s*\{', code, re.IGNORECASE):
            maxid_window = code[maxid_match.start(): maxid_match.start() + 2500]
            if '$.ajax' in maxid_window and '});' not in maxid_window:
                errors.append("Malformed maxid() AJAX block detected (missing closure).")
                break
            if (
                '$.ajax' in maxid_window
                and re.search(r"data\s*:\s*\{[^}]*Action\s*:\s*['\"]GetMaxID['\"]", maxid_window, re.IGNORECASE)
                and 'success:' not in maxid_window
                and '.done(' not in maxid_window
            ):
                errors.append("maxid() AJAX block missing success callback.")
                break

        return errors

    def _normalize_identifier(self, text: str, fallback: str = "Field") -> str:
        cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', (text or '')).strip('_')
        if not cleaned:
            return fallback
        if re.match(r'^\d', cleaned):
            cleaned = f"{fallback}_{cleaned}"
        return cleaned

    def _extract_requested_fields_from_prompt(self, user_request: str):
        request_text = self._normalize_request_sections(user_request).strip()
        if not request_text:
            return []

        def normalize_heading(text: str) -> str:
            clean = (text or '').strip()
            clean = re.sub(r'^[#>\-\*\s]+', '', clean)
            clean = re.sub(r'^\d+[.)]\s*', '', clean)
            return clean.lower().rstrip(':').strip()

        section_starts = ('master fields', 'form fields', 'fields')
        section_breaks = (
            'primary key', 'operations', 'crud operations',
            'relationships', 'dependencies', 'business validations', 'validation rules',
            'detail grid', 'detail fields', 'detail table',
            'required company patterns', 'required patterns',
            'output rules', 'table', 'file name', 'title', 'case type', 'casetype'
        )
        non_field_tokens = {
            'create', 'read', 'update', 'delete', 'crud', 'operation', 'operations',
            'db_insert', 'db_update', 'db_delete', 'db_getrecord', 'getrows', 'getvalue',
            'funstarttran', 'funendtran', 'fun_log',
            'formvalidation', 'checkkeycode',
            'comp_code', 'user_id', 'login_id'
        }

        def extract_tokens(fragment: str):
            clean = re.sub(r'^\s*(?:[-*•]\s*|\d+[.)]\s*)', '', fragment or '').strip()
            if not clean:
                return []
            if '|' in clean:
                clean = clean.split('|', 1)[0].strip()
            tokens = []
            for part in re.split(r',|\band\b|/|→|->', clean, flags=re.IGNORECASE):
                piece = part.strip().strip('-').strip()
                if not piece:
                    continue
                id_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)', piece)
                if id_match:
                    tokens.append(id_match.group(1))
            return tokens

        def looks_like_field_line(line: str) -> bool:
            normalized = normalize_heading(line)
            if not normalized:
                return False
            if any(normalized.startswith(prefix) for prefix in section_breaks):
                return False
            tokens = extract_tokens(line)
            if not tokens:
                return False
            return tokens[0].lower() not in non_field_tokens

        field_candidates = []

        # 1) Direct prose pattern: "fields: a, b, c"
        for raw_line in request_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            fields_clause = re.search(r'(?:with\s+)?fields?\s*:\s*(.+)', line, re.IGNORECASE)
            if not fields_clause:
                continue
            for token in extract_tokens(fields_clause.group(1)):
                if token.lower() in non_field_tokens:
                    continue
                field_candidates.append(token)

        # 2) Structured sections with bullets/numbered lines
        capturing = False
        for raw_line in request_text.splitlines():
            line = raw_line.strip()
            normalized = normalize_heading(line)

            if any(normalized.startswith(prefix) for prefix in section_starts):
                capturing = True
                continue

            if not capturing:
                continue

            if any(normalized.startswith(prefix) for prefix in section_breaks):
                break

            if not line:
                continue

            if (re.match(r'^[-*•]\s+', line) or re.match(r'^\d+[.)]\s+', line)) and looks_like_field_line(line):
                field_candidates.extend(extract_tokens(line))
            elif looks_like_field_line(line):
                field_candidates.extend(extract_tokens(line))

        stopwords = set(
            word.lower() for word in get_csv_setting(
                'CODEGEN_FIELD_STOPWORDS',
                'CODEGEN_FIELD_STOPWORDS',
                default=[
                    'create', 'complete', 'master', 'form', 'fields', 'detail',
                    'grid', 'include', 'company', 'standard', 'patterns', 'generate',
                    'all', 'with', 'from', 'via', 'ajax', 'required', 'operations',
                    'crud', 'read', 'update', 'delete',
                    'db_insert', 'db_update', 'db_delete', 'db_getrecord', 'getrows', 'getvalue',
                    'funstarttran', 'funendtran', 'fun_log',
                    'formvalidation', 'checkkeycode', 'comp_code', 'user_id', 'login_id',
                    'output', 'rules', 'canonical', 'table', 'file', 'title', 'primary', 'key'
                ]
            )
        )
        unique_fields = []
        seen = set()
        for field in field_candidates:
            normalized = self._normalize_identifier(field, fallback="Field")
            lowered = normalized.lower()
            if lowered in seen or lowered in stopwords:
                continue
            seen.add(lowered)
            unique_fields.append(normalized)

        max_fields = get_int_setting(
            'CODEGEN_DYNAMIC_FALLBACK_MAX_FIELDS',
            'CODEGEN_DYNAMIC_FALLBACK_MAX_FIELDS',
            40,
            min_value=5,
            max_value=120
        )
        return unique_fields[:max_fields]

    def _generate_dynamic_request_fallback(self, user_request: str):
        """
        Build a generic-but-dynamic complete PHP form using fields inferred from prompt.
        """
        request_metadata = self._extract_explicit_request_metadata(user_request)
        entity_hints = self._extract_entity_hints(user_request)
        raw_entity = (
            request_metadata.get('module_entity')
            or request_metadata.get('effective_entity')
            or (entity_hints[0] if entity_hints else "Form")
        )
        feature_name = self._normalize_identifier(str(raw_entity).replace(' ', '_'), fallback="Form")
        title = request_metadata.get('title') or feature_name.replace('_', ' ')
        table_name = request_metadata.get('table_name') or f"tbl{re.sub(r'[^a-z0-9]', '', feature_name.lower()) or 'form'}"
        file_name = os.path.basename(request_metadata.get('file_name') or f"frm{feature_name}.php")

        fields = self._extract_requested_fields_from_prompt(user_request)
        if not fields:
            fields = ['Code', 'Name', 'Remarks', 'Status']

        primary_candidates = ['code', 'cust_code', 'acc_code', 'id']
        primary_field = request_metadata.get('primary_key') or fields[0]
        for field in fields:
            if field.lower() in primary_candidates:
                primary_field = field
                break

        normalized_fields = []
        seen_fields = set()
        for field in [primary_field] + fields:
            normalized = self._normalize_identifier(field, fallback="Field")
            lowered = normalized.lower()
            if lowered in seen_fields:
                continue
            seen_fields.add(lowered)
            normalized_fields.append(normalized)
        fields = normalized_fields

        def field_input_html(field_name: str) -> str:
            lowered = field_name.lower()
            label = field_name.replace('_', ' ')
            escaped = field_name
            value_expr = f"<?= htmlspecialchars($_REQUEST['{escaped}'] ?? '') ?>"
            if 'address' in lowered or 'remarks' in lowered:
                return (
                    f"<div class=\"form-group\"><label for=\"{escaped}\">{label}</label>"
                    f"<textarea class=\"form-control\" id=\"{escaped}\" name=\"{escaped}\" rows=\"3\">{value_expr}</textarea></div>"
                )
            input_type = 'text'
            if 'email' in lowered:
                input_type = 'email'
            elif 'date' in lowered:
                input_type = 'date'
            elif 'amount' in lowered or 'limit' in lowered or 'tax' in lowered or 'disc' in lowered:
                input_type = 'number'
            return (
                f"<div class=\"form-group\"><label for=\"{escaped}\">{label}</label>"
                f"<input class=\"form-control\" type=\"{input_type}\" id=\"{escaped}\" name=\"{escaped}\" value=\"{value_expr}\"></div>"
            )

        editable_fields = [f for f in fields if f.lower() != primary_field.lower()]
        column_lines = [
            f"    $columns['{field}'] = add_Slashes_new($_REQUEST['{field}'] ?? '');"
            for field in editable_fields
        ]
        column_lines.extend([
            "    $columns['Comp_Code'] = $_SESSION['comp_code'] ?? '';",
            "    $columns['Updated_By'] = $_SESSION['user_id'] ?? '';",
            "    $columns['Updated_Date'] = date('Y-m-d H:i:s');",
        ])

        input_blocks = "\n            ".join(field_input_html(field) for field in fields)
        focus_fields = "', '".join(fields)

        complete_php = f"""<?php
@session_start();
include("include/config.inc.php");

$form2 = "{file_name}";
$table = "{table_name}";
$title = "{title}";
$primaryField = "{primary_field}";

if (!function_exists('add_Slashes_new')) {{
    function add_Slashes_new($value) {{ return addslashes($value); }}
}}

if (($_REQUEST['Action'] ?? '') == 'Save') {{
    if (function_exists('funStartTran')) {{ funStartTran(); }}
    $primaryValue = $_REQUEST[$primaryField] ?? '';
    $columns = array();
{chr(10).join(column_lines)}

    if (function_exists('getrows') && getrows($table, $primaryField, $primaryValue) == '1') {{
        if (function_exists('db_update')) {{
            db_update($table, $columns, "$primaryField='".add_Slashes_new($primaryValue)."' AND Comp_Code='".$_SESSION['comp_code']."'");
        }}
        if (function_exists('fun_log')) {{ fun_log($table, $primaryValue, 'Update', $_SESSION['user_id'] ?? ''); }}
    }} else {{
        $columns[$primaryField] = add_Slashes_new($primaryValue);
        $columns['Created_By'] = $_SESSION['user_id'] ?? '';
        $columns['Created_Date'] = date('Y-m-d H:i:s');
        if (function_exists('db_insert')) {{
            db_insert($table, $columns);
        }}
        if (function_exists('fun_log')) {{ fun_log($table, $primaryValue, 'Save', $_SESSION['user_id'] ?? ''); }}
    }}

    if (function_exists('funEndTran')) {{ funEndTran(); }}
    header("Location: ".$form2."?msg=saved");
    exit;
}}
?>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title><?= $title ?></title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">
</head>
<body>
<div class="container mt-4">
    <h4><?= $title ?></h4>
    <form method="post" id="frmDynamic">
        <input type="hidden" name="Action" value="Save">
        <div class="row">
            <div class="col-md-8">
            {input_blocks}
            </div>
        </div>
        <button type="submit" class="btn btn-primary">Save</button>
    </form>
</div>

<script>
function checkKeycode(event) {{
    if (event.keyCode !== 13) return true;
    event.preventDefault();
    var order = ['{focus_fields}'];
    var active = document.activeElement ? document.activeElement.id : '';
    var idx = order.indexOf(active);
    if (idx >= 0 && idx < order.length - 1) {{
        var next = document.getElementById(order[idx + 1]);
        if (next) next.focus();
    }}
    return false;
}}
document.addEventListener('keydown', checkKeycode);
</script>
</body>
</html>
"""

        return {
            'code': {'complete_php': complete_php.strip()},
            'intent': {
                'feature_type': 'form',
                'form_title': title,
                'fields': [{'name': field, 'required': field == primary_field} for field in fields],
                'database': {
                    'table_name': table_name,
                    'primary_key': primary_field,
                    'indexes': [],
                    'relationships': []
                },
                'operations': ['create', 'read', 'update', 'delete'],
                'ui_layout': 'single-column'
            },
            'file_structure': {
                'root': f"{feature_name}_module",
                'files': {
                    'complete_php': {
                        'path': file_name,
                        'description': 'Dynamic fallback form generated from user request'
                    }
                }
            },
            'metadata': {
                'generation_type': 'dynamic_prompt_fallback',
                'inferred_fields': fields,
                'primary_field': primary_field
            },
            'validation_score': get_int_setting(
                'CODEGEN_DYNAMIC_FALLBACK_VALIDATION_SCORE',
                'CODEGEN_DYNAMIC_FALLBACK_VALIDATION_SCORE',
                55,
                min_value=1,
                max_value=100
            ),
            'validation_result': {
                'valid': True,
                'mode': 'dynamic_fallback',
                'warning': 'Generated from dynamic fallback template because AI was unavailable.'
            },
            'error': 'AI generation did not produce production-valid code; dynamic fallback output was returned.'
        }

    def _list_company_form_files(self, user_id=None, codebase_id=None):
        if not user_id or not codebase_id:
            return []

        codebase_root = os.path.join(
            getattr(settings, 'COMPANY_CODEBASE_DIR', 'company_codebases'),
            str(user_id),
            str(codebase_id)
        )
        codebase_root_fs = _to_windows_long_path(codebase_root)
        if not os.path.isdir(codebase_root_fs):
            return []

        form_files = []
        for root, _, files in os.walk(codebase_root_fs):
            readable_root = _from_windows_long_path(root)
            for filename in files:
                lowered = filename.lower()
                if lowered.startswith('frm') and lowered.endswith('.php'):
                    form_files.append(os.path.join(readable_root, filename))

        return form_files

    def _codebase_has_form_templates(self, user_id=None, codebase_id=None) -> bool:
        return bool(self._list_company_form_files(user_id=user_id, codebase_id=codebase_id))

    def _generate_company_template_fallback(self, user_request, user_id=None, codebase_id=None):
        """
        Deterministic fallback from uploaded company codebase (best effort).
        """
        if not user_id or not codebase_id:
            return None

        form_files = self._list_company_form_files(user_id=user_id, codebase_id=codebase_id)
        if not form_files:
            return None

        request_metadata = self._extract_explicit_request_metadata(user_request)
        explicit_file_name = os.path.basename(request_metadata.get('file_name') or '').lower()
        explicit_module = re.sub(r'[^a-z0-9_]', '', (request_metadata.get('module_entity') or '').lower())

        selected_file = None
        if explicit_file_name:
            exact_file_matches = [
                file_path for file_path in form_files
                if os.path.basename(file_path).lower() == explicit_file_name
            ]
            if exact_file_matches:
                selected_file = exact_file_matches[0]
                logger.info(
                    "Company template fallback honoring explicit file name: %s",
                    os.path.basename(selected_file)
                )
        if not selected_file and explicit_module:
            exact_entity_matches = [
                file_path for file_path in form_files
                if os.path.splitext(os.path.basename(file_path).lower())[0] == f"frm{explicit_module}"
            ]
            if exact_entity_matches:
                selected_file = exact_entity_matches[0]
                logger.info(
                    "Company template fallback honoring explicit module entity: %s",
                    os.path.basename(selected_file)
                )

        hints = self._extract_entity_hints(user_request)
        cleaned_hints = []
        for hint in hints:
            cleaned = re.sub(r'[^a-z0-9_]', '', (hint or '').lower())
            if cleaned and cleaned not in cleaned_hints:
                cleaned_hints.append(cleaned)

        score_exact_match = get_int_setting(
            'CODEGEN_TEMPLATE_SCORE_EXACT',
            'CODEGEN_TEMPLATE_SCORE_EXACT',
            300,
            min_value=50,
            max_value=1000
        )
        score_prefix_match = get_int_setting(
            'CODEGEN_TEMPLATE_SCORE_PREFIX',
            'CODEGEN_TEMPLATE_SCORE_PREFIX',
            220,
            min_value=30,
            max_value=1000
        )
        score_word_match = get_int_setting(
            'CODEGEN_TEMPLATE_SCORE_WORD',
            'CODEGEN_TEMPLATE_SCORE_WORD',
            170,
            min_value=20,
            max_value=1000
        )
        score_contains_match = get_int_setting(
            'CODEGEN_TEMPLATE_SCORE_CONTAINS',
            'CODEGEN_TEMPLATE_SCORE_CONTAINS',
            120,
            min_value=10,
            max_value=1000
        )
        hint_base_weight = get_int_setting(
            'CODEGEN_TEMPLATE_HINT_BASE_WEIGHT',
            'CODEGEN_TEMPLATE_HINT_BASE_WEIGHT',
            120,
            min_value=20,
            max_value=500
        )
        hint_step = get_int_setting(
            'CODEGEN_TEMPLATE_HINT_STEP',
            'CODEGEN_TEMPLATE_HINT_STEP',
            5,
            min_value=1,
            max_value=50
        )
        hint_floor = get_int_setting(
            'CODEGEN_TEMPLATE_HINT_FLOOR',
            'CODEGEN_TEMPLATE_HINT_FLOOR',
            5,
            min_value=1,
            max_value=100
        )
        confidence_threshold = get_int_setting(
            'CODEGEN_TEMPLATE_SCORE_THRESHOLD',
            'CODEGEN_TEMPLATE_SCORE_THRESHOLD',
            220,
            min_value=20,
            max_value=1000
        )

        best_match = None
        best_score = -1
        if not selected_file:
            for file_path in form_files:
                file_name = os.path.basename(file_path).lower()
                file_stem = os.path.splitext(file_name)[0]
                score = 0

                for index, hint in enumerate(cleaned_hints[:12]):
                    hint_weight = max(hint_floor, hint_base_weight - (index * hint_step))
                    if file_stem == f"frm{hint}":
                        score = max(score, score_exact_match + hint_weight)
                    elif file_stem.startswith(f"frm{hint}"):
                        score = max(score, score_prefix_match + hint_weight)
                    elif re.search(rf'(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])', file_stem):
                        score = max(score, score_word_match + hint_weight)
                    elif hint in file_stem:
                        score = max(score, score_contains_match + hint_weight)

                if score > best_score:
                    best_score = score
                    best_match = file_path

            selected_file = best_match if best_score >= confidence_threshold else None
        if not selected_file:
            logger.warning(
                "No confident company-template fallback match for request; "
                "switching to dynamic fallback instead."
            )
            return None

        # Safety gate: prevent unrelated template fallback (for example Student -> BusinessProfile).
        primary_hint = cleaned_hints[0] if cleaned_hints else ''
        selected_stem = os.path.splitext(os.path.basename(selected_file).lower())[0]
        if primary_hint:
            primary_match = (
                selected_stem == f"frm{primary_hint}" or
                selected_stem.startswith(f"frm{primary_hint}") or
                re.search(rf'(?<![a-z0-9]){re.escape(primary_hint)}(?![a-z0-9])', selected_stem)
            )
            if not primary_match:
                logger.warning(
                    "Selected template does not match primary entity hint "
                    f"('{primary_hint}' vs '{selected_stem}'); using dynamic fallback."
                )
                return None

        try:
            with open(_to_windows_long_path(selected_file), 'r', encoding='utf-8', errors='ignore') as f:
                complete_php = f.read().strip()
        except Exception as read_error:
            logger.warning(f"Company template fallback read failed: {read_error}")
            return None

        if not complete_php:
            return None

        file_name = os.path.basename(selected_file)
        feature_name = file_name[3:-4] if file_name.lower().startswith('frm') and file_name.lower().endswith('.php') else 'Form'
        title_match = re.search(r'\$title\s*=\s*["\']([^"\']+)["\']', complete_php, re.IGNORECASE)
        table_match = re.search(r'\$table\s*=\s*["\']([^"\']+)["\']', complete_php, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else feature_name.replace('_', ' ')
        table_name = table_match.group(1).strip() if table_match else f"tbl{feature_name.replace('_', '').lower()}"

        logger.warning(f"Using company-template fallback file: {file_name}")
        return {
            'code': {
                'complete_php': complete_php
            },
            'intent': {
                'feature_type': 'form',
                'form_title': title,
                'fields': [],
                'database': {
                    'table_name': table_name,
                    'primary_key': 'Code',
                    'indexes': [],
                    'relationships': []
                },
                'operations': ['create', 'read', 'update', 'delete'],
                'ui_layout': 'single-column'
            },
            'file_structure': {
                'root': f"{feature_name}_module",
                'files': {
                    'complete_php': {
                        'path': file_name,
                        'description': 'Deterministic company template fallback'
                    }
                }
            },
            'metadata': {
                'generation_type': 'company_template_fallback',
                'source_file': selected_file,
                'requested_file_name': request_metadata.get('file_name') or '',
                'requested_table_name': request_metadata.get('table_name') or ''
            },
            'validation_score': get_int_setting(
                'CODEGEN_TEMPLATE_FALLBACK_VALIDATION_SCORE',
                'CODEGEN_TEMPLATE_FALLBACK_VALIDATION_SCORE',
                70,
                min_value=1,
                max_value=100
            ),
            'validation_result': {
                'valid': True,
                'mode': 'company_template_fallback',
                'warning': 'Returned from deterministic company template due to AI workflow degradation.'
            },
            'error': 'AI generation did not produce production-valid code; company template fallback output was returned.'
        }

    def _generate_fallback_code(self, user_request, user_id=None, codebase_id=None):
        """
        Generate fallback code when AI is not available.
        Priority:
        1) Deterministic company template (if codebase exists)
        2) Dynamic prompt-driven generic fallback
        """
        logger.info("Generating fallback code for: " + user_request[:100])

        company_template_result = self._generate_company_template_fallback(
            user_request=user_request,
            user_id=user_id,
            codebase_id=codebase_id
        )
        if company_template_result:
            return self._normalize_fallback_result(company_template_result)

        result = self._generate_dynamic_request_fallback(user_request)
        return self._normalize_fallback_result(result)

    def _normalize_fallback_result(self, result):
        """
        Normalize legacy fallback payloads to the inline `complete_php` format.
        """
        if not isinstance(result, dict):
            return {
                'code': {'complete_php': ''},
                'validation_score': 0,
                'validation_result': {'valid': False, 'errors': ['Invalid fallback result format']}
            }

        code = result.get('code', {}) or {}
        if not isinstance(code, dict):
            code = {}

        complete_php = (code.get('complete_php') or '').strip()
        if not complete_php:
            php_part = (code.get('php') or '').strip()
            html_part = (code.get('html') or '').strip()
            css_part = (code.get('css') or '').strip()
            js_part = (code.get('js') or '').strip()

            stitched_parts = []
            if php_part:
                stitched_parts.append(php_part)
            else:
                stitched_parts.append("<?php\n// Fallback PHP generated due to AI unavailability\n?>")

            if html_part:
                stitched_parts.append(html_part)
            if css_part:
                stitched_parts.append(f"<style>\n{css_part}\n</style>")
            if js_part:
                stitched_parts.append(f"<script>\n{js_part}\n</script>")

            complete_php = "\n\n".join(stitched_parts).strip()
            code['complete_php'] = complete_php

        result['code'] = code
        result.setdefault('validation_score', 0)
        result.setdefault('validation_result', {
            'valid': bool(complete_php),
            'mode': 'fallback',
            'warning': 'Generated in fallback mode due to AI connectivity issue'
        })
        result.setdefault(
            'error',
            'AI generation did not produce production-valid code; fallback template output was returned.'
        )
        return result

    def _attach_fallback_diagnostics(self, fallback_result, upstream_result=None, fallback_reason=''):
        """
        Preserve upstream workflow diagnostics on fallback responses for UI/reporting transparency.
        """
        if not isinstance(fallback_result, dict):
            return fallback_result

        metadata = fallback_result.get('metadata', {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}

        upstream_result = upstream_result or {}
        upstream_metadata = (upstream_result.get('metadata', {}) or {}) if isinstance(upstream_result, dict) else {}
        inline_meta = (upstream_metadata.get('inline_generation_metadata', {}) or {}) if isinstance(upstream_metadata, dict) else {}

        attempts_made = upstream_metadata.get('attempts_made', inline_meta.get('attempts_made'))
        max_attempts = upstream_metadata.get('max_attempts', inline_meta.get('max_attempts'))
        refusal_count = upstream_metadata.get('refusal_count', inline_meta.get('refusal_count'))
        llm_call_failures = upstream_metadata.get('llm_call_failures', inline_meta.get('llm_call_failures'))
        attempt_models = inline_meta.get('attempt_models') if isinstance(inline_meta, dict) else None
        initial_prompt_mode = inline_meta.get('initial_prompt_mode') if isinstance(inline_meta, dict) else None
        if isinstance(upstream_result, dict):
            upstream_error_text = " ".join(
                part for part in [
                    str(upstream_result.get('error') or '').strip(),
                    str(upstream_result.get('details') or '').strip()
                ] if part
            )
        else:
            upstream_error_text = ''

        # Recover attempts/refusal telemetry when upstream failed before metadata was finalized.
        if attempts_made is None and upstream_error_text:
            attempts_match = re.search(r'after\s+(\d+)\s+attempt', upstream_error_text, re.IGNORECASE)
            if attempts_match:
                attempts_made = int(attempts_match.group(1))
                if max_attempts is None:
                    max_attempts = attempts_made
                if refusal_count is None and 'refus' in upstream_error_text.lower():
                    refusal_count = attempts_made

        if attempts_made is not None and refusal_count is None:
            refusal_count = 0
        if attempts_made is not None and llm_call_failures is None:
            llm_call_failures = 0

        if (not attempt_models) and attempts_made:
            enforce_flag = str(
                getattr(settings, 'CODEGEN_ENFORCE_GPT4O_MINI', os.getenv('CODEGEN_ENFORCE_GPT4O_MINI', 'true'))
            ).strip().lower() in ('1', 'true', 'yes', 'on')
            default_model = 'gpt-4o-mini' if enforce_flag else os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
            try:
                attempt_models = [default_model] * int(attempts_made)
            except Exception:
                attempt_models = [default_model]
            if not initial_prompt_mode:
                initial_prompt_mode = 'unknown'

        diagnostics = {
            'fallback_reason': fallback_reason or 'fallback_triggered',
            'upstream_attempts_made': attempts_made,
            'upstream_max_attempts': max_attempts,
            'upstream_refusal_count': refusal_count,
            'upstream_llm_call_failures': llm_call_failures,
            'upstream_attempt_models': attempt_models,
            'upstream_initial_prompt_mode': initial_prompt_mode,
            'upstream_validation_score': upstream_result.get('validation_score') if isinstance(upstream_result, dict) else None,
            'upstream_error': upstream_result.get('error') if isinstance(upstream_result, dict) else None
        }

        metadata['upstream_diagnostics'] = diagnostics
        if attempts_made is not None:
            metadata.setdefault('attempts_made', attempts_made)
        if max_attempts is not None:
            metadata.setdefault('max_attempts', max_attempts)
        if refusal_count is not None:
            metadata.setdefault('refusal_count', refusal_count)
        if llm_call_failures is not None:
            metadata.setdefault('llm_call_failures', llm_call_failures)

        # Preserve upstream inline-generation telemetry on fallback responses.
        if isinstance(inline_meta, dict) and inline_meta:
            fallback_inline_meta = metadata.get('inline_generation_metadata', {}) or {}
            if not isinstance(fallback_inline_meta, dict):
                fallback_inline_meta = {}
            for key in [
                'attempt_models',
                'initial_prompt_mode',
                'full_prompt_chars',
                'initial_prompt_chars',
                'attempt_prompt_chars',
                'attempts_made',
                'max_attempts',
                'refusal_count',
                'llm_call_failures',
                'fallback_usage',
                'generic_fallback_ratio_percent',
                'generic_fallback_budget_percent',
                'generic_fallback_budget_passed',
            ]:
                if key in inline_meta and key not in fallback_inline_meta:
                    fallback_inline_meta[key] = inline_meta.get(key)
            if fallback_inline_meta:
                metadata['inline_generation_metadata'] = fallback_inline_meta
        elif attempt_models:
            metadata['inline_generation_metadata'] = {
                'attempt_models': attempt_models,
                'initial_prompt_mode': initial_prompt_mode,
                'attempts_made': attempts_made,
                'max_attempts': max_attempts,
                'refusal_count': refusal_count,
                'llm_call_failures': llm_call_failures,
                'inferred_from_upstream_error': True,
            }

        fallback_result['metadata'] = metadata
        return fallback_result
    

class CompanyCodebaseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing company codebases
    """
    serializer_class = CompanyCodebaseSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        return CompanyCodebase.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        codebase = self.get_object()
        self._delete_codebase_record(codebase, request.user.id)
        return Response({
            'message': 'Codebase deleted successfully'
        })

    def _delete_codebase_record(self, codebase, user_id):
        codebase_dir = self._resolve_codebase_upload_path(codebase)

        if AGENTS_AVAILABLE:
            try:
                ingestion_pipeline = CodeIngestionPipeline(user_id=str(user_id))
                ingestion_pipeline.delete_codebase(
                    codebase_id=str(codebase.id),
                    user_id=str(user_id)
                )
            except Exception as vector_error:
                logger.warning(f"Could not delete vector data for codebase {codebase.id}: {vector_error}")

        if codebase_dir and os.path.exists(codebase_dir):
            try:
                shutil.rmtree(codebase_dir)
                logger.info(f"Deleted codebase files for {codebase.id}")
            except Exception as file_error:
                logger.warning(f"Could not delete codebase files for {codebase.id}: {file_error}")

        codebase.delete()

    def _extract_codebase_without_indexing(self, temp_file_path, codebase_id, user_id):
        storage_root = os.path.join(settings.COMPANY_CODEBASE_DIR, str(user_id), str(codebase_id))
        storage_root_fs = _to_windows_long_path(storage_root)

        if os.path.exists(storage_root_fs):
            shutil.rmtree(storage_root_fs)
        os.makedirs(storage_root_fs, exist_ok=True)

        if not zipfile.is_zipfile(temp_file_path):
            raise ValueError("Invalid ZIP file format")

        with zipfile.ZipFile(temp_file_path, 'r') as archive:
            file_list = archive.namelist()
            if len(file_list) > 10000:
                raise ValueError("ZIP contains too many files (max 10,000)")

            for file_name in file_list:
                if file_name.startswith('/') or file_name.startswith('\\'):
                    raise ValueError("Suspicious file path detected in ZIP archive")
                if '/../' in file_name or '\\..\\' in file_name or file_name.endswith('/..') or file_name.endswith('\\..'):
                    raise ValueError("Suspicious file path detected in ZIP archive")

            archive.extractall(storage_root_fs)

        total_files = 0
        for root, _, files in os.walk(storage_root_fs):
            for file_name in files:
                if Path(file_name).suffix.lower() in SUPPORTED_CODE_EXTENSIONS:
                    total_files += 1

        return {
            'storage_path': storage_root,
            'total_files': total_files,
            'indexed_files': 0,
            'total_chunks': 0,
            'skipped_files': [],
        }
    
    @action(detail=False, methods=['post'])
    def upload(self, request):
        """
        Upload company codebase (zip file) with BACKGROUND PROCESSING
        ðŸš€ OPTIMIZATION: Returns immediately, processes in background
        """
        serializer = FileUploadSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = serializer.validated_data['file']
        name = serializer.validated_data['name']
        
        # Validate file type
        if not uploaded_file.name.endswith('.zip'):
            return Response({
                'error': 'Only zip files are supported'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate file size (100MB limit)
        max_size = 100 * 1024 * 1024  # 100MB in bytes
        if uploaded_file.size > max_size:
            return Response({
                'error': f'File size exceeds maximum limit of 100MB. Your file is {uploaded_file.size / (1024*1024):.1f}MB'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for duplicate name
        if CompanyCodebase.objects.filter(user=request.user, name=name).exists():
            return Response({
                'error': f'A codebase named "{name}" already exists. Please use a different name.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Create codebase record immediately
            codebase = CompanyCodebase.objects.create(
                user=request.user,
                name=name,
                upload_path='',
                is_indexed=False
            )
            
            # Save uploaded file to temporary location
            temp_file_path = self._save_temp_file(uploaded_file, codebase.id)
            
            # Start background processing thread
            thread = threading.Thread(
                target=self._process_codebase_background,
                args=(codebase.id, temp_file_path, request.user.id),
                daemon=True
            )
            thread.start()
            
            logger.info(f"ðŸš€ Background processing started for codebase {codebase.id}")
            
            # Return immediately (user doesn't wait!)
            return Response({
                'message': 'Upload started! Processing in background...',
                'codebase_id': str(codebase.id),
                'name': name,
                'status': 'processing',
                'info': 'Check progress using the indexing_status endpoint'
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Upload initiation error: {str(e)}", exc_info=True)
            return _friendly_error_response(
                'Failed to initiate upload. Please try again with a valid ZIP file.',
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    def _save_temp_file(self, uploaded_file, codebase_id):
        """
        Save uploaded file to temporary location
        """
        try:
            # Create temp directory if it doesn't exist
            temp_dir = str(getattr(settings, 'TEMP_UPLOADS_DIR', Path(settings.MEDIA_ROOT) / 'temp_uploads'))
            os.makedirs(temp_dir, exist_ok=True)
            
            # Save file with unique name
            temp_file_path = os.path.join(temp_dir, f'codebase_{codebase_id}.zip')
            
            with open(temp_file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            logger.info(f"Temp file saved for codebase {codebase_id}")
            return temp_file_path
            
        except Exception as e:
            logger.error(f"Error saving temp file: {str(e)}")
            raise

    def _resolve_codebase_upload_path(self, codebase, persist: bool = True):
        """
        Resolve stale codebase upload paths into the current workspace storage root.
        """
        stored_path = os.path.normpath(str(codebase.upload_path or ''))
        current_root = os.path.join(settings.COMPANY_CODEBASE_DIR, str(codebase.user_id), str(codebase.id))

        candidates = [current_root]
        if stored_path:
            candidates.append(stored_path)

            normalized_stored = stored_path.replace('/', os.sep).replace('\\', os.sep)
            marker = f"{codebase.id}{os.sep}"
            marker_index = normalized_stored.lower().find(marker.lower())
            if marker_index != -1:
                relative_suffix = normalized_stored[marker_index + len(marker):].strip(os.sep)
                if relative_suffix:
                    candidates.append(os.path.join(current_root, relative_suffix))

            basename = os.path.basename(normalized_stored.rstrip(os.sep))
            if basename and basename != str(codebase.id):
                candidates.append(os.path.join(current_root, basename))

        if os.path.isdir(current_root):
            for child in Path(current_root).iterdir():
                if child.is_dir():
                    candidates.append(str(child))

        seen = set()
        for candidate in candidates:
            normalized_candidate = os.path.normpath(str(candidate))
            if normalized_candidate in seen:
                continue
            seen.add(normalized_candidate)

            if os.path.exists(normalized_candidate):
                if persist and normalized_candidate != stored_path:
                    codebase.upload_path = normalized_candidate
                    codebase.save(update_fields=['upload_path'])
                    logger.info(f"Normalized codebase upload_path for {codebase.id}: {normalized_candidate}")
                return normalized_candidate

        return stored_path
    
    def _process_codebase_background(self, codebase_id, temp_file_path, user_id):
        """
        Process codebase in background thread
        ðŸš€ OPTIMIZATION: User doesn't wait for this!
        """
        codebase = None
        codebase_dir = None
        
        try:
            logger.info(f"ðŸ“¦ Background processing started for codebase {codebase_id}")
            
            # Get codebase record
            codebase = CompanyCodebase.objects.get(id=codebase_id)
            codebase.index_status = 'processing'
            codebase.index_error = ''
            codebase.save(update_fields=['index_status', 'index_error'])
            
            # Open temp file
            with open(temp_file_path, 'rb') as f:
                uploaded_file = File(f, name=os.path.basename(temp_file_path))
                
                # Process with ingestion pipeline
                if AGENTS_AVAILABLE and getattr(settings, 'OPENAI_API_KEY_CONFIGURED', False):
                    ingestion_pipeline = CodeIngestionPipeline(user_id=str(user_id))
                    result = ingestion_pipeline.process_uploaded_file(
                        uploaded_file=uploaded_file,
                        codebase_id=str(codebase_id),
                        user_id=str(user_id)
                    )
                    codebase_dir = result.get('storage_path')
                else:
                    result = self._extract_codebase_without_indexing(
                        temp_file_path=temp_file_path,
                        codebase_id=codebase_id,
                        user_id=user_id,
                    )
                    if not AGENTS_AVAILABLE:
                        result['index_error'] = 'Indexing service is not available in this environment.'
                    else:
                        result['index_error'] = 'OpenAI API key not configured. Codebase files were stored, but indexing was skipped.'
                    codebase_dir = result.get('storage_path')
            
            # Update codebase record with results
            codebase.upload_path = result['storage_path']
            codebase.total_files = result['total_files']
            codebase.indexed_files = result['indexed_files']
            codebase.index_error = sanitize_public_text(result.get('index_error', ''))
            codebase.is_indexed = not bool(codebase.index_error)
            codebase.index_status = 'ready' if codebase.is_indexed else 'failed'
            codebase.save()
            
            logger.info(f"âœ… Background processing complete for codebase {codebase_id}: {result['indexed_files']}/{result['total_files']} files indexed")
            
            # Delete temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.info(f"Temp upload deleted for codebase {codebase_id}")
            
        except Exception as e:
            logger.error(f"âŒ Background processing error for codebase {codebase_id}: {str(e)}", exc_info=True)
            
            # Mark as failed
            try:
                if codebase:
                    codebase.is_indexed = False
                    codebase.index_status = 'failed'
                    codebase.index_error = safe_index_error_message(str(e))
                    codebase.save(update_fields=['is_indexed', 'index_status', 'index_error'])
                    
                    # Cleanup on failure
                    if AGENTS_AVAILABLE:
                        try:
                            ingestion_pipeline = CodeIngestionPipeline(user_id=str(user_id))
                            ingestion_pipeline.delete_codebase(
                                codebase_id=str(codebase_id),
                                user_id=str(user_id)
                            )
                        except Exception as cleanup_error:
                            logger.error(f"Cleanup error: {str(cleanup_error)}")
                    
                    # Delete files if they were created
                    if codebase_dir and os.path.exists(codebase_dir):
                        try:
                            shutil.rmtree(codebase_dir)
                            logger.info(f"Cleaned up directory for failed codebase {codebase_id}")
                        except Exception as file_error:
                            logger.error(f"File cleanup error: {str(file_error)}")
                    
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {str(cleanup_error)}")
            
            # Delete temp file
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass
    
    def delete_codebase(self, request, pk=None):
        """
        Delete codebase and remove from vector store
        """
        codebase = self.get_object()
        self._delete_codebase_record(codebase, request.user.id)
        return Response({
            'message': 'Codebase deleted successfully'
        })
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get overall codebase statistics for the user
        """
        user_codebases = CompanyCodebase.objects.filter(user=request.user)
        
        total_codebases = user_codebases.count()
        total_files = sum(cb.total_files for cb in user_codebases)
        indexed_files = sum(cb.indexed_files for cb in user_codebases)
        
        # Get pattern statistics from vector store
        pattern_stats = {
            'total_patterns': 0,
            'languages': {},
            'categories': {}
        }
        
        if AGENTS_AVAILABLE:
            try:
                from agents.vectorstore.retriever import CodePatternRetriever
                retriever = CodePatternRetriever()
                import asyncio
                pattern_stats = asyncio.run(retriever.get_collection_stats(str(request.user.id)))
            except Exception as e:
                logger.warning(f"Could not get pattern stats: {e}")
        
        # Build codebase list for frontend selector
        codebases = []
        for cb in user_codebases:
            codebases.append({
                'id': str(cb.id),
                'name': cb.name,
                'file_count': cb.total_files,
                'indexed_files': cb.indexed_files,
                'is_indexed': cb.is_indexed,
                'index_status': cb.index_status,
                'index_error': sanitize_public_text(cb.index_error),
            })
        
        return Response({
            'total_codebases': total_codebases,
            'total_files': total_files,
            'indexed_files': indexed_files,
            'indexing_progress': (indexed_files / total_files * 100) if total_files > 0 else 0,
            'pattern_stats': pattern_stats,
            'codebases': codebases,
            'has_indexed_codebase': any(cb['is_indexed'] for cb in codebases),
            'has_failed_codebase': any(cb['index_status'] == 'failed' for cb in codebases),
        })
    
    @action(detail=True, methods=['post'])
    def reindex(self, request, pk=None):
        """
        Re-index a codebase (useful if indexing failed or needs update)
        """
        codebase = self.get_object()
        codebase_dir = self._resolve_codebase_upload_path(codebase)
        
        if not codebase_dir or not os.path.exists(codebase_dir):
            return Response({
                'error': 'Codebase files not found. Please re-upload.'
            }, status=status.HTTP_404_NOT_FOUND)

        if not getattr(settings, 'OPENAI_API_KEY_CONFIGURED', False):
            codebase.is_indexed = False
            codebase.index_status = 'failed'
            codebase.index_error = 'OpenAI API key not configured. Codebase files are available, but re-indexing is disabled until a key is configured.'
            codebase.save(update_fields=['is_indexed', 'index_status', 'index_error'])
            return _friendly_error_response(settings.OPENAI_REQUIRED_MESSAGE)
        
        try:
            logger.info(f"Re-indexing codebase {codebase.id}")
            
            # Delete old embeddings from vector store
            if AGENTS_AVAILABLE:
                ingestion_pipeline = CodeIngestionPipeline(user_id=str(request.user.id))
                try:
                    deleted_chunks = ingestion_pipeline.clear_codebase_embeddings(
                        codebase_id=str(codebase.id),
                        user_id=str(request.user.id)
                    )
                    logger.info(f"Old embeddings deleted: {deleted_chunks} chunks")
                except Exception as e:
                    logger.warning(f"Could not delete old embeddings: {e}")
            
            # Reset indexing status
            codebase.is_indexed = False
            codebase.index_status = 'processing'
            codebase.index_error = ''
            codebase.indexed_files = 0
            codebase.save(update_fields=['is_indexed', 'index_status', 'index_error', 'indexed_files'])
            
            # Re-index files
            if AGENTS_AVAILABLE:
                ingestion_pipeline = CodeIngestionPipeline(user_id=str(request.user.id))
                
                # Find all code files
                code_files = ingestion_pipeline._find_code_files(codebase_dir)
                
                # Re-index each file
                total_chunks = 0
                indexed_files = 0
                skipped_files = []
                
                for file_path in code_files:
                    try:
                        with open(_to_windows_long_path(file_path), 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        if not content or not content.strip():
                            skipped_files.append({
                                'file': str(file_path),
                                'reason': 'Empty file'
                            })
                            continue
                        
                        metadata = {
                            'codebase_id': str(codebase.id),
                            'user_id': str(request.user.id),
                            'file_type': 'company_code'
                        }
                        
                        chunks = ingestion_pipeline.embedding_manager.add_code_file(
                            file_path=str(file_path),
                            code_content=content,
                            metadata=metadata
                        )
                        
                        total_chunks += chunks
                        indexed_files += 1
                        
                    except UnicodeDecodeError:
                        skipped_files.append({
                            'file': str(file_path),
                            'reason': 'Invalid encoding'
                        })
                    except Exception as e:
                        skipped_files.append({
                            'file': str(file_path),
                            'reason': str(e)
                        })
                
                # Update codebase
                codebase.total_files = len(code_files)
                codebase.indexed_files = indexed_files
                codebase.is_indexed = True
                codebase.index_status = 'ready'
                codebase.index_error = ''
                codebase.save(update_fields=['total_files', 'indexed_files', 'is_indexed', 'index_status', 'index_error'])
                
                logger.info(f"Re-indexing complete: {indexed_files}/{len(code_files)} files")
                
                response_data = {
                    'message': 'Codebase re-indexed successfully',
                    'total_files': len(code_files),
                    'indexed_files': indexed_files,
                    'total_chunks': total_chunks
                }
                
                if skipped_files:
                    response_data['skipped_files'] = skipped_files
                    response_data['warning'] = f'{len(skipped_files)} file(s) were skipped'
                
                return Response(response_data)
            else:
                codebase.index_status = 'failed'
                codebase.index_error = 'Indexing service is not available in this environment.'
                codebase.save(update_fields=['index_status', 'index_error'])
                return _friendly_error_response(
                    'Indexing service is not available in this environment.',
                    http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
                
        except Exception as e:
            logger.error(f"Re-indexing error: {str(e)}", exc_info=True)
            codebase.is_indexed = False
            codebase.index_status = 'failed'
            codebase.index_error = safe_index_error_message(str(e))
            codebase.save(update_fields=['is_indexed', 'index_status', 'index_error'])
            return _friendly_error_response(
                codebase.index_error,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    @action(detail=True, methods=['get'])
    def indexing_status(self, request, pk=None):
        """
        Get indexing status with file type breakdown
        """
        codebase = self.get_object()
        
        # Get file type statistics from vector store
        file_types = {}
        if AGENTS_AVAILABLE and codebase.is_indexed:
            try:
                from agents.vectorstore.retriever import CodePatternRetriever
                retriever = CodePatternRetriever()
                
                # Get stats for this codebase
                import asyncio
                stats = asyncio.run(retriever.get_collection_stats(str(request.user.id)))
                
                # Count by language for this codebase
                # This is a simplified version - you can enhance it
                file_types = {
                    'php': 0,
                    'html': 0,
                    'css': 0,
                    'js': 0,
                    'sql': 0
                }
                
                # Estimate based on total patterns
                if stats.get('languages'):
                    file_types = stats['languages']
                    
            except Exception as e:
                logger.warning(f"Could not get file type stats: {e}")
        
        return Response({
            'codebase_id': str(codebase.id),
            'name': codebase.name,
            'is_indexed': codebase.is_indexed,
            'index_status': codebase.index_status,
            'index_error': sanitize_public_text(codebase.index_error),
            'total_files': codebase.total_files,
            'indexed_files': codebase.indexed_files,
            'progress': (codebase.indexed_files / codebase.total_files * 100) if codebase.total_files > 0 else 0,
            'file_types': file_types
        })


class CompanyStandardsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing company coding standards
    """
    serializer_class = CompanyStandardsSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        return CompanyStandards.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def upload(self, request):
        """
        Upload company coding standards (MD file)
        """
        serializer = FileUploadSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = serializer.validated_data['file']
        name = serializer.validated_data['name']
        
        # Validate file type
        if not uploaded_file.name.endswith('.md'):
            return Response({
                'error': 'Only markdown (.md) files are supported'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Create standards record
            standards = CompanyStandards.objects.create(
                user=request.user,
                name=name,
                file_path='',
                content='',
                is_active=True
            )
            
            # Process upload
            if not AGENTS_AVAILABLE:
                content = uploaded_file.read().decode('utf-8')
                result = {
                    'file_path': f'standards/{request.user.id}/{standards.id}.md',
                    'content': content,
                    'metadata': {
                        'php_version': '8.0',
                        'framework': '',
                        'css_framework': '',
                        'db_engine': 'InnoDB'
                    }
                }
            else:
                file_handler = StandardsFileHandler()
                result = file_handler.save_standards_file(
                    uploaded_file=uploaded_file,
                    standards_id=str(standards.id),
                    user_id=str(request.user.id)
                )
            
            # Update record
            standards.file_path = result['file_path']
            standards.content = result['content']
            standards.php_version = result['metadata'].get('php_version', '')
            standards.framework = result['metadata'].get('framework', '')
            standards.css_framework = result['metadata'].get('css_framework', '')
            standards.db_engine = result['metadata'].get('db_engine', '')
            standards.save()
            
            # Deactivate other standards
            CompanyStandards.objects.filter(
                user=request.user
            ).exclude(id=standards.id).update(is_active=False)
            
            # Clear old cache and warm up with new standards
            if AGENTS_AVAILABLE:
                try:
                    from django.core.cache import cache
                    from agents.utils.cache_helper import set_cached_standards, cache_key
                    
                    # Clear old standards cache
                    old_key = cache_key('standards', request.user.id)
                    cache.delete(old_key)
                    logger.info(f"ðŸ—‘ï¸ Old standards cache cleared for user {request.user.id}")
                    
                    # Warm up with new standards
                    set_cached_standards(request.user.id, result)
                    logger.info(f"âœ… New standards cached for user {request.user.id}")
                    
                except Exception as cache_error:
                    logger.warning(f"Cache refresh failed: {cache_error}")
            
            logger.info(f"Standards uploaded for user {request.user.id}")
            
            return Response({
                'message': 'Standards uploaded successfully. Cache refreshed automatically.',
                'standards_id': str(standards.id),
                'metadata': result['metadata']
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Standards upload error: {str(e)}")
            
            if 'standards' in locals():
                standards.delete()
            
            return _friendly_error_response(
                'Failed to upload standards.',
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Set standards as active
        """
        standards = self.get_object()
        
        # Deactivate all other standards
        CompanyStandards.objects.filter(
            user=request.user
        ).update(is_active=False)
        
        # Activate this one
        standards.is_active = True
        standards.save()
        
        return Response({
            'message': f'Standards "{standards.name}" activated'
        })
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """
        Get currently active standards
        """
        try:
            standards = CompanyStandards.objects.get(
                user=request.user,
                is_active=True
            )
            serializer = self.get_serializer(standards)
            return Response(serializer.data)
            
        except CompanyStandards.DoesNotExist:
            return Response({
                'message': 'No active standards found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'])
    def refresh_cache(self, request):
        """
        Clear and refresh cache for current user
        """
        try:
            from django.core.cache import cache
            from agents.utils.cache_helper import cache_key, set_cached_standards
            from agents.utils.file_handler import StandardsFileHandler
            
            user_id = request.user.id
            
            # Clear old cache
            old_key = cache_key('standards', user_id)
            cache.delete(old_key)
            
            # Clear patterns cache
            for lang in ['php', 'html', 'css', 'js', 'sql']:
                # Clear all pattern variations for this user
                cache.delete_pattern(f'*patterns*{user_id}*{lang}*')
            
            logger.info(f"ðŸ—‘ï¸ Cache cleared for user {user_id}")
            
            # Re-warm standards cache
            file_handler = StandardsFileHandler()
            standards_data = file_handler.get_standards_for_user(user_id)
            
            if standards_data['content']:
                set_cached_standards(user_id, standards_data)
                logger.info(f"âœ… Cache refreshed for user {user_id}")
                
                return Response({
                    'message': 'Cache refreshed successfully! Your next code generation will use fresh data.',
                    'status': 'success'
                })
            else:
                return Response({
                    'message': 'Cache cleared but no standards found to refresh',
                    'status': 'warning'
                })
            
        except Exception as e:
            logger.error(f"Cache refresh error: {str(e)}")
            return _friendly_error_response(
                'Failed to refresh cache.',
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



class DatabaseConnectionViewSet(viewsets.ModelViewSet):
    """
    API endpoints for managing database connections
    """
    serializer_class = DatabaseConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # Disable pagination for this endpoint
    
    def list(self, request, *args, **kwargs):
        """List all database connections"""
        logger.debug("DatabaseConnectionViewSet.list called")
        return super().list(request, *args, **kwargs)
    
    def get_queryset(self):
        """
        Return database connections for current user
        """
        try:
            queryset = DatabaseConnection.objects.filter(user=self.request.user)
            return queryset
        except Exception as e:
            logger.warning(f"DatabaseConnection queryset failed: {e}")
            return DatabaseConnection.objects.none()
    
    def perform_create(self, serializer):
        """
        Create database connection for current user
        """
        try:
            serializer.save(user=self.request.user)
        except Exception as e:
            logger.warning(f"DatabaseConnection create failed: {e}")
            raise
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """
        Test database connection
        """
        try:
            db_connection = self.get_object()
            
            from agents.utils.database_executor import DatabaseExecutor
            
            executor = DatabaseExecutor(
                db_type=db_connection.db_type,
                host=db_connection.host,
                port=db_connection.port,
                database=db_connection.database,
                username=db_connection.username,
                password=db_connection.password
            )
            
            result = executor.test_connection()
            
            # Update connection status
            if result.get('connected'):
                db_connection.is_connected = True
                db_connection.connection_error = ''
                db_connection.last_tested = timezone.now()
                db_connection.save()
                
                logger.info(f"âœ… Database connection tested successfully: {db_connection.name}")
                
                return Response({
                    'status': 'success',
                    'message': 'Connection successful',
                    'server_version': result.get('server_version', 'Unknown')
                })
            else:
                db_connection.is_connected = False
                db_connection.connection_error = result.get('error', 'Unknown error')
                db_connection.last_tested = timezone.now()
                db_connection.save()
                
                logger.warning(f"âŒ Database connection failed: {db_connection.name} - {result.get('error')}")
                
                return Response({
                    'status': 'error',
                    'message': 'Connection failed',
                    'error': result.get('error', 'Unknown error')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except DatabaseConnection.DoesNotExist:
            return Response({
                'error': 'Database connection not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Database connection test error: {str(e)}")
            return _friendly_error_response(
                'Failed to test connection.',
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """
        Set database connection as default
        """
        try:
            db_connection = self.get_object()
            
            # Clear previous default
            DatabaseConnection.objects.filter(
                user=request.user,
                is_default=True
            ).update(is_default=False)
            
            # Set new default
            db_connection.is_default = True
            db_connection.save()
            
            logger.info(f"âœ… Default database connection set: {db_connection.name}")
            
            return Response({
                'status': 'success',
                'message': f'{db_connection.name} set as default'
            })
            
        except DatabaseConnection.DoesNotExist:
            return Response({
                'error': 'Database connection not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Set default error: {str(e)}")
            return _friendly_error_response(
                'Failed to set default database connection.',
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    @action(detail=False, methods=['get'])
    def default(self, request):
        """
        Get default database connection
        """
        try:
            db_connection = DatabaseConnection.objects.get(
                user=request.user,
                is_default=True
            )
            serializer = self.get_serializer(db_connection)
            return Response(serializer.data)
        except DatabaseConnection.DoesNotExist:
            return Response({
                'message': 'No default database connection set'
            }, status=status.HTTP_404_NOT_FOUND)

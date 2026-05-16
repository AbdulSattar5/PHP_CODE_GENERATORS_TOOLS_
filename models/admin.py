"""
Django admin configuration for GenCode AI models
"""

from django.contrib import admin
from .project import (
    Project, GeneratedCode, CompanyStandards,
    CompanyCodebase, ConversationHistory, DatabaseConnection
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at', 'updated_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-updated_at']


@admin.register(GeneratedCode)
class GeneratedCodeAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'project', 'code_type', 'validation_score', 'created_at']
    list_filter = ['code_type', 'created_at']
    search_fields = ['file_name', 'project__name']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']


@admin.register(CompanyStandards)
class CompanyStandardsAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_active', 'php_version', 'framework', 'created_at']
    list_filter = ['is_active', 'framework', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(CompanyCodebase)
class CompanyCodebaseAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_indexed', 'indexed_files', 'total_files', 'created_at']
    list_filter = ['is_indexed', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']


@admin.register(ConversationHistory)
class ConversationHistoryAdmin(admin.ModelAdmin):
    list_display = ['project', 'role', 'timestamp']
    list_filter = ['role', 'timestamp']
    search_fields = ['project__name', 'content']
    readonly_fields = ['id', 'timestamp']
    ordering = ['-timestamp']


@admin.register(DatabaseConnection)
class DatabaseConnectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'db_type', 'host', 'is_connected', 'is_default', 'created_at']
    list_filter = ['db_type', 'is_connected', 'is_default', 'created_at']
    search_fields = ['name', 'user__username', 'host', 'database']
    readonly_fields = ['id', 'created_at', 'updated_at', 'is_connected', 'last_tested', 'connection_error', 'user']
    ordering = ['-created_at']
    fieldsets = (
        ('Connection Info', {
            'fields': ('name', 'user', 'db_type', 'host', 'port', 'database', 'username', 'password')
        }),
        ('Status', {
            'fields': ('is_connected', 'last_tested', 'connection_error', 'is_default')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Automatically set the user to the current admin user"""
        if not change:  # Only set user on creation, not on edit
            obj.user = request.user
        super().save_model(request, obj, form, change)
"""
Management command to clear and refresh cache
Use this when standards or codebase are updated
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.cache import cache
from agents.vectorstore.embeddings import CodeEmbeddingManager
from agents.utils.file_handler import StandardsFileHandler
from agents.utils.cache_helper import set_cached_patterns, set_cached_standards
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clear and refresh cache (use after updating standards/codebase)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Specific user ID to refresh cache for (optional)',
        )
        parser.add_argument(
            '--clear-only',
            action='store_true',
            help='Only clear cache without re-warming',
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        clear_only = options.get('clear_only')
        
        # Step 1: Clear existing cache
        self.stdout.write(self.style.WARNING('\n🗑️  Clearing cache...'))
        cache.clear()
        self.stdout.write(self.style.SUCCESS('✅ Cache cleared!'))
        
        if clear_only:
            self.stdout.write(self.style.SUCCESS('\n✅ Done! Cache cleared.'))
            return
        
        # Step 2: Re-warm cache
        if user_id:
            users = User.objects.filter(id=user_id)
        else:
            users = User.objects.all()
        
        self.stdout.write(self.style.SUCCESS(f'\n🔥 Re-warming cache for {users.count()} user(s)...'))
        
        for user in users:
            self.stdout.write(f'\n📦 Processing user: {user.username} (ID: {user.id})')
            
            # Warm up patterns cache
            self._warmup_patterns(user.id)
            
            # Warm up standards cache
            self._warmup_standards(user.id)
        
        self.stdout.write(self.style.SUCCESS('\n✅ Cache refresh completed!'))
        self.stdout.write(self.style.SUCCESS('🚀 Your agent is now using fresh data!\n'))
    
    def _warmup_patterns(self, user_id):
        """Pre-cache patterns for common queries"""
        self.stdout.write('  📦 Warming up patterns cache...')
        
        embedding_manager = CodeEmbeddingManager()
        
        # Common search queries
        common_queries = [
            'form with validation',
            'CRUD operations',
            'invoice transaction',
            'grid with calculations',
            'master detail form'
        ]
        
        languages = ['php', 'html', 'css', 'js', 'sql']
        
        cached_count = 0
        
        for query in common_queries:
            for lang in languages:
                try:
                    # Search and cache
                    results = embedding_manager.search_similar_code(
                        query=query,
                        k=3,
                        filter_dict={
                            'language': lang,
                            'user_id': str(user_id)
                        }
                    )
                    
                    if results:
                        set_cached_patterns(user_id, query, lang, results)
                        cached_count += 1
                        self.stdout.write(f'    ✅ Cached: {lang} patterns for "{query}"')
                
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'    ⚠️  Failed to cache {lang} for "{query}": {str(e)}')
                    )
        
        self.stdout.write(self.style.SUCCESS(f'  ✅ Cached {cached_count} pattern sets'))
    
    def _warmup_standards(self, user_id):
        """Pre-cache standards"""
        self.stdout.write('  📋 Warming up standards cache...')
        
        try:
            file_handler = StandardsFileHandler()
            standards_data = file_handler.get_standards_for_user(user_id)
            
            if standards_data['content']:
                set_cached_standards(user_id, standards_data)
                self.stdout.write(self.style.SUCCESS('  ✅ Standards cached'))
            else:
                self.stdout.write(self.style.WARNING('  ⚠️  No standards found for user'))
        
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'  ⚠️  Failed to cache standards: {str(e)}')
            )

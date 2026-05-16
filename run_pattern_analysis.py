"""
Pattern Analysis Script
Analyzes company codebase and caches patterns for code generation

Usage:
    python run_pattern_analysis.py <user_id>
    
Example:
    python run_pattern_analysis.py 1
"""

import os
import django
import sys

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gencode_project.settings')
django.setup()

from agents.utils.pattern_analyzer import CodebasePatternAnalyzer
from agents.utils.cache_helper import set_cached_analyzed_patterns
from models.project import CompanyCodebase
import asyncio
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def analyze_codebase(user_id: str):
    """Analyze all codebases for a user"""
    logger.info(f"🔍 Analyzing codebases for user {user_id}...")
    
    # Get all codebases for user - use sync_to_async for Django ORM
    from asgiref.sync import sync_to_async
    
    @sync_to_async
    def get_codebases():
        return list(CompanyCodebase.objects.filter(user_id=user_id))
    
    codebases = await get_codebases()
    
    if not codebases:
        logger.error(f"❌ No codebases found for user {user_id}")
        logger.info(f"💡 Please upload a codebase first")
        return
    
    logger.info(f"📦 Found {len(codebases)} codebase(s)")
    
    analyzer = CodebasePatternAnalyzer(user_id=user_id)
    
    for codebase in codebases:
        logger.info(f"\n{'='*80}")
        logger.info(f"📦 Analyzing codebase: {codebase.id}")
        logger.info(f"   Name: {codebase.name}")
        logger.info(f"   Created: {codebase.created_at}")
        logger.info(f"{'='*80}")
        
        try:
            # Analyze patterns - use SYNC version to avoid event loop issues
            logger.info(f"⏳ Starting pattern analysis...")
            patterns = analyzer.analyze_codebase_patterns_sync(str(codebase.id))
            
            # Cache results
            set_cached_analyzed_patterns(user_id, str(codebase.id), patterns)
            
            # Show summary
            php = patterns.get('php', {})
            html = patterns.get('html', {})
            js = patterns.get('js', {})
            sql = patterns.get('sql', {})
            
            logger.info(f"\n✅ Analysis complete for codebase {codebase.id}:")
            logger.info(f"\n📊 PHP Patterns:")
            logger.info(f"   - Functions: {len(php.get('functions', []))}")
            logger.info(f"   - Tables: {len(php.get('table_names', []))}")
            logger.info(f"   - Fields: {len(php.get('field_names', []))}")
            logger.info(f"   - AJAX Functions: {len(php.get('ajax_functions', []))}")
            logger.info(f"   - AJAX Auto-ID: {len(php.get('ajax_auto_id', []))}")
            logger.info(f"   - Dynamic Dropdowns: {len(php.get('dynamic_dropdowns', []))}")
            logger.info(f"   - Delete Checks: {len(php.get('delete_checks', []))}")
            logger.info(f"   - Chart Integration: {len(php.get('chart_integration', []))}")
            logger.info(f"   - FormValidation: {'Yes' if php.get('formvalidation', {}).get('has_formvalidation') else 'No'}")
            logger.info(f"   - Keyboard Navigation: {'Yes' if php.get('keyboard_navigation', {}).get('has_keyboard_nav') else 'No'}")
            
            logger.info(f"\n📊 HTML Patterns:")
            logger.info(f"   - CSS Classes: {len(html.get('css_classes', []))}")
            logger.info(f"   - Bootstrap: {'Yes' if html.get('uses_bootstrap') else 'No'}")
            
            logger.info(f"\n📊 JavaScript Patterns:")
            logger.info(f"   - Functions: {len(js.get('function_names', []))}")
            logger.info(f"   - jQuery: {'Yes' if js.get('uses_jquery') else 'No'}")
            
            logger.info(f"\n📊 SQL Patterns:")
            logger.info(f"   - Engine: {sql.get('engine', 'N/A')}")
            logger.info(f"   - Charset: {sql.get('charset', 'N/A')}")
            
            logger.info(f"\n💾 Patterns cached successfully!")
            
        except Exception as e:
            logger.error(f"❌ Error analyzing codebase {codebase.id}: {str(e)}")
            logger.exception(e)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"✅ Pattern analysis complete for user {user_id}")
    logger.info(f"{'='*80}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("❌ Error: Missing user_id argument")
        print("\nUsage: python run_pattern_analysis.py <user_id>")
        print("\nExample:")
        print("  python run_pattern_analysis.py 1")
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    try:
        asyncio.run(analyze_codebase(user_id))
    except KeyboardInterrupt:
        print("\n\n⚠️ Analysis interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
